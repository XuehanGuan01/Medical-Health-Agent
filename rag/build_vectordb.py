#!/usr/bin/env python3
"""
构建华佗医疗 RAG 向量库

数据源: C:/Users/Lenovo/Desktop/huatuo_data/
  - HuatuoGPT2_sft_instruct_GPT4_sharegpt.jsonl  (50,000, GPT-4 蒸馏, 优先)
  - HuatuoGPT_sft_data_v1_sharegpt.jsonl         (226,042)

处理流程:
  1. 合并两个 JSONL (v2 在前 → 去重时优先保留)
  2. 格式校验 (conversations 含 human+gpt)
  3. 质量过滤 (回答 < 10 字符丢弃)
  4. 去重 (问题 MD5, v2 优先)
  5. DashScope text-embedding-v4 批量嵌入
  6. ChromaDB 持久化 (断点续传)

预计: ~26 万条有效, 嵌入 ~40 分钟, ~6 元 API 费用
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import chromadb
from langchain_community.embeddings import DashScopeEmbeddings
from tqdm import tqdm

# ── 配置 ──────────────────────────────────────────────────────────
DATA_DIR = Path("C:/Users/Lenovo/Desktop/huatuo_data")
FILES = [
    # (文件名, 来源标签, 格式) — 顺序决定去重优先级
    ("HuatuoGPT2_sft_instruct_GPT4_sharegpt.jsonl", "huatuo_v2"),
    ("HuatuoGPT_sft_data_v1_sharegpt.jsonl", "huatuo_v1"),
]

CHROMA_DIR = "./data/chroma"
COLLECTION_NAME = "huatuo_medical_qa"
CHECKPOINT_FILE = "./data/chroma/build_checkpoint.json"

BATCH_SIZE = 20          # DashScope 单次最多 25 条, 留余量
CHECKPOINT_EVERY = 50    # 每 50 批 (1,000 条) 存一次进度
MIN_ANSWER_LEN = 10      # 回答最少字符数
MAX_API_RETRIES = 5      # API 调用最大重试次数


# ── 工具 ──────────────────────────────────────────────────────────

def load_checkpoint() -> int:
    """加载断点: 返回已完成的记录索引, 0 表示从头开始"""
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            cp = json.load(f)
        idx = cp.get("next_index", 0)
        print(f"[checkpoint] 从索引 {idx:,} 恢复 ({idx/260000*100:.1f}% 已完成)")
        return idx
    except FileNotFoundError:
        return 0


def save_checkpoint(next_index: int):
    """保存断点"""
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"next_index": next_index, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, f)


def clear_checkpoint():
    """任务完成后清除断点"""
    try:
        os.remove(CHECKPOINT_FILE)
    except FileNotFoundError:
        pass


# ── Step 1 & 2 & 3 & 4: 加载 + 校验 + 过滤 + 去重 ────────────────────

def load_all_records() -> list[dict]:
    """
    按顺序读取 JSONL 文件, 合并、校验、过滤、去重。
    v2 文件先处理, 同问题去重时 v2 覆盖 v1。
    """
    all_records: list[dict] = []
    seen_hashes: set[str] = set()

    for filename, source_label in FILES:
        file_path = DATA_DIR / filename
        if not file_path.exists():
            print(f"[warn] 文件不存在, 跳过: {file_path}")
            continue

        file_records = 0
        skipped_format = 0
        skipped_quality = 0
        skipped_dup = 0

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line_num, line in enumerate(tqdm(lines, desc=f"Loading {filename}", unit="ln"), 1):
            # ── 解析 JSON ──
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                skipped_format += 1
                continue

            # ── 格式校验 ──
            convs = item.get("conversations")
            if not convs or not isinstance(convs, list) or len(convs) < 2:
                skipped_format += 1
                continue

            human_val = (convs[0].get("value", "") or "").strip()
            gpt_val = (convs[1].get("value", "") or "").strip()

            if not human_val or not gpt_val:
                skipped_format += 1
                continue

            # ── 质量过滤 ──
            if len(gpt_val) < MIN_ANSWER_LEN:
                skipped_quality += 1
                continue

            # ── 严重非中文过滤 ──
            cn_count = sum(1 for c in gpt_val if '一' <= c <= '鿿')
            if len(gpt_val) > 20 and cn_count / len(gpt_val) < 0.3:
                skipped_quality += 1
                continue

            # ── 去重 ──
            q_hash = hashlib.md5(human_val.encode("utf-8")).hexdigest()
            if q_hash in seen_hashes:
                skipped_dup += 1
                continue
            seen_hashes.add(q_hash)

            all_records.append({
                "question": human_val,
                "answer": gpt_val,
                "source": source_label,
            })
            file_records += 1

        print(f"  [{source_label}] 有效: {file_records:,}"
              f" | 格式跳过: {skipped_format}"
              f" | 质量跳过: {skipped_quality}"
              f" | 去重跳过: {skipped_dup}")

    print(f"\n  合并有效总计: {len(all_records):,} 条")
    return all_records


# ── Step 5 & 6: Embedding + ChromaDB 入库 ──────────────────────────

def build_vectordb(records: list[dict]):
    """批量嵌入 + ChromaDB 持久化"""
    os.makedirs(CHROMA_DIR, exist_ok=True)

    embedder = DashScopeEmbeddings(model="text-embedding-v4")

    # ChromaDB client
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # 如果 collection 已存在, 删除重建 (幂等)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"[chroma] 已删除旧 collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "华佗医疗对话知识库 (HuatuoGPT v1 + v2)",
            "embedding_model": "text-embedding-v4",
            "dimension": 1024,
            "hnsw:space": "cosine",
        },
    )

    # 断点恢复
    start_idx = load_checkpoint()
    total_batches = (len(records) - start_idx + BATCH_SIZE - 1) // BATCH_SIZE

    pbar = tqdm(total=len(records), initial=start_idx, desc="Embedding", unit="rec")

    idx = start_idx
    batch_count = 0
    consecutive_failures = 0

    while idx < len(records):
        batch = records[idx:idx + BATCH_SIZE]
        questions = [r["question"] for r in batch]

        # ── API 调用 (带指数退避重试) ──
        embeddings = None
        for attempt in range(MAX_API_RETRIES):
            try:
                embeddings = embedder.embed_documents(questions)
                consecutive_failures = 0
                break
            except Exception as e:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                if attempt < MAX_API_RETRIES - 1:
                    tqdm.write(f"  [retry] batch {idx:,} attempt {attempt+1}: {e} (wait {wait}s)")
                    time.sleep(wait)
                else:
                    tqdm.write(f"  [fail] batch {idx:,} after {MAX_API_RETRIES} retries: {e}")
                    consecutive_failures += 1

        if embeddings is None:
            idx += BATCH_SIZE
            pbar.update(len(batch))
            if consecutive_failures >= 3:
                save_checkpoint(idx)
                print(f"\n[error] 连续 {consecutive_failures} 批失败, 进度已保存。修复后重新运行。")
                sys.exit(1)
            continue

        # ── ChromaDB 写入 ──
        batch_size_actual = len(batch)
        ids = [f"huatuo_{j:06d}" for j in range(idx, idx + batch_size_actual)]
        documents = [
            f"问：{r['question']}\n答：{r['answer']}"
            for r in batch
        ]
        metadatas = [
            {
                "question": r["question"],
                "answer_length": len(r["answer"]),
                "source": r["source"],
            }
            for r in batch
        ]

        collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )

        idx += batch_size_actual
        batch_count += 1
        pbar.update(batch_size_actual)

        # 定期存 checkpoint
        if batch_count % CHECKPOINT_EVERY == 0:
            save_checkpoint(idx)

    pbar.close()

    # 最终验证
    actual_count = collection.count()
    print(f"\n[chroma] collection.count() = {actual_count:,}")
    if actual_count != len(records):
        print(f"[warn] 预期 {len(records):,} 条, 实际 {actual_count:,} 条 (差 {len(records) - actual_count:,})")

    clear_checkpoint()
    print("[done] 向量库构建完成")


# ── 入口 ──────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Medical-Health-Agent — RAG 向量库构建")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  输出目录: {CHROMA_DIR}")
    print(f"  Embedding 模型: DashScope text-embedding-v4")
    print("=" * 60)

    # 检查 API Key
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("\n[error] 环境变量 DASHSCOPE_API_KEY 未设置")
        print("  请执行: export DASHSCOPE_API_KEY=sk-xxx")
        sys.exit(1)

    # Step 1-4: 合并 + 清洗
    print("\n── Step 1-4: 加载 & 清洗 ──")
    records = load_all_records()

    if not records:
        print("[error] 无有效数据, 退出")
        sys.exit(1)

    # 统计
    v1_count = sum(1 for r in records if r["source"] == "huatuo_v1")
    v2_count = sum(1 for r in records if r["source"] == "huatuo_v2")
    avg_q = sum(len(r["question"]) for r in records) / len(records)
    avg_a = sum(len(r["answer"]) for r in records) / len(records)
    print(f"\n  来源: v2={v2_count:,}, v1={v1_count:,}")
    print(f"  平均问题: {avg_q:.0f} 字符, 平均回答: {avg_a:.0f} 字符")

    # 估算
    est_tokens = sum(len(r["question"]) / 1.5 for r in records)
    est_cost = est_tokens / 1000 * 0.0005
    est_time = len(records) / BATCH_SIZE * 0.15 / 60
    print(f"  预估 API tokens: ~{est_tokens/1e6:.1f}M")
    print(f"  预估 API 费用: ~¥{est_cost:.1f}")
    print(f"  预估耗时: ~{est_time:.0f} 分钟 ({est_time/60:.1f} 小时)")

    # 确认
    print(f"\n  将创建 ChromaDB collection '{COLLECTION_NAME}'")
    response = input("  继续? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        print("  已取消")
        sys.exit(0)

    # Step 5-6: 嵌入 + 入库
    print("\n── Step 5-6: Embedding + ChromaDB ──")
    build_vectordb(records)


if __name__ == "__main__":
    main()
