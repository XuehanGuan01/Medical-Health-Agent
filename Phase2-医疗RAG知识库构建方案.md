# Phase 2: 医疗 RAG 知识库构建方案

> **目标**：将华佗医疗对话数据集（27.6 万条）清洗、Embedding 向量化，构建 ChromaDB 知识库，为 Phase 3 的分析 Agent 提供检索增强能力。
>
> **周期**：3–5 天
>
> **核心原则**：Embedding 通过 DashScope text-embedding-v4 API 完成，向量库本地持久化，查询时实时嵌入 + 本地检索。

---

## 目录

1. [架构总览](#1-架构总览)
2. [源数据概览](#2-源数据概览)
3. [数据处理流程](#3-数据处理流程)
4. [Embedding 方案](#4-embedding-方案)
5. [ChromaDB 构建](#5-chromadb-构建)
6. [检索接口](#6-检索接口)
7. [测试验证](#7-测试验证)
8. [代码结构与执行顺序](#8-代码结构与执行顺序)

---

## 1. 架构总览

```
C:/Users/Lenovo/Desktop/huatuo_data/
├── HuatuoGPT_sft_data_v1_sharegpt.jsonl       ← 226,042 条 (335MB)
└── HuatuoGPT2_sft_instruct_GPT4_sharegpt.jsonl ←  50,000 条 (78MB)
         │
         │ merge + clean
         ▼
┌─────────────────────┐
│ rag/build_vectordb.py│
│                     │
│ 1. 合并两个 JSONL    │
│ 2. 格式校验          │
│ 3. 内容质量过滤      │
│ 4. 去重              │
│ 5. Embedding (API)   │
│ 6. ChromaDB 入库     │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ data/chroma/        │  ← 持久化向量库
│ huatuo_medical_qa/  │
│   ~276K records     │
│   ~0.5GB (1024维)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ rag/retriever.py    │  ← 检索接口
│                     │
│ search(query, k=5)  │
│   → Top-K QA pairs  │
└─────────────────────┘
```

### 数据流

```
用户查询 "小孩发烧怎么办？"
  → DashScopeEmbeddings.embed_query(query)  ← API 嵌入 (~100ms)
  → collection.query(embedding, n_results=5) ← 本地检索 (~20ms)
  → 返回 5 条最相关 QA 对
  → 格式化为 LLM context
```

---

## 2. 源数据概览

### 2.1 文件清单

| 文件 | 记录数 | 大小 | 来源 |
|------|--------|------|------|
| `HuatuoGPT_sft_data_v1_sharegpt.jsonl` | 226,042 | 335 MB | HuatuoGPT v1，中文医疗对话 |
| `HuatuoGPT2_sft_instruct_GPT4_sharegpt.jsonl` | 50,000 | 78 MB | HuatuoGPT2，GPT-4 蒸馏的高质量回答 |
| **合计** | **276,042** | **413 MB** | |

### 2.2 数据格式（两个文件完全一致）

```json
{
  "conversations": [
    {"from": "human", "value": "小孩发烧39度怎么办？"},
    {"from": "gpt", "value": "小孩发烧39度属于高热，需要引起重视。以下是建议：\n1. 观察精神状态...\n2. 服用退烧药...\n3. 物理降温..."}
  ]
}
```

### 2.3 实测统计

| 指标 | HuatuoGPT v1 | HuatuoGPT2 (GPT-4) | 合并 |
|------|-------------|---------------------|------|
| 平均问题长度 | ~72 字符 | ~45 字符 | ~68 字符 |
| 平均回答长度 | ~270 字符 | ~500 字符 | ~310 字符 |
| 回答 P50 | 246 字符 | 480 字符 | 260 字符 |
| 回答 P95 | 498 字符 | 620 字符 | 510 字符 |
| 空/短回答 | 5 条 | 0 条 | 5 条 |
| 格式合规率 | 99.998% | 100% | 99.998% |

> **结论**：两个文件格式统一，可直接合并。v2 的 GPT-4 蒸馏数据回答更长、质量更高。无需格式转换。

---

## 3. 数据处理流程

### 3.1 四步清洗管线

```
Step 1: 合并
  ├── 读取两个 JSONL 文件
  ├── 逐行 JSON 解析
  └── 合并到统一列表

Step 2: 格式校验
  ├── conversations 不为 None/空
  ├── 至少包含 human + gpt 两轮
  ├── human.value 和 gpt.value 不为空字符串
  └── 不通过 → 记录日志 + 丢弃

Step 3: 内容质量过滤
  ├── gpt.value 字符数 < 10 → 丢弃（非实质性回答）
  ├── human.value 字符数 > 500 → 截断（不太可能是检索查询）
  └── 纯非中文字符占比 > 70% → 丢弃

Step 4: 去重
  ├── 以 human.value 的 MD5 为 key
  └── 相同问题保留第一条（v2 GPT-4 数据优先 > v1，同版本保留长的回答）
```

### 3.2 去重策略细节

由于两个文件有相同来源（HuatuoGPT），可能存在重叠问题。去重优先级：

```python
# 去重时优先保留 HuatuoGPT2 (GPT-4 蒸馏)，因为回答质量更高
# 如果同一问题在两份数据中都出现：
#   保留 HuatuoGPT2 的版本（回答更长、GPT-4 质量）
#   丢弃 HuatuoGPT v1 的版本
```

### 3.3 预期处理结果

```
原始: 276,042 条
  - 格式校验丢弃: ~0-3 条
  - 质量过滤丢弃: ~5-10 条（短回答）
  - 去重丢弃: ~5,000-15,000 条（v1 与 v2 重叠部分）
  ─────────────────
预计最终: ~260,000-270,000 条
```

---

## 4. Embedding 方案

### 4.1 选型：DashScope text-embedding-v4

```python
from langchain_community.embeddings import DashScopeEmbeddings

embedder = DashScopeEmbeddings(model="text-embedding-v4")
# 前提：环境变量 DASHSCOPE_API_KEY 已配置
```

| 属性 | 值 |
|------|-----|
| 模型 | text-embedding-v4 |
| 维度 | 1024 |
| 中文效果 | ⭐⭐⭐⭐⭐ (阿里云旗舰) |
| 计费 | ~¥0.0005/1000 tokens |
| 单次调用上限 | 25 条文本 |
| 延迟 (单条) | ~80-120ms |

### 4.2 成本估算

```
26 万条 × 平均问题 43 tokens/条 = 11.2M 输入 tokens
11.2M / 1000 × ¥0.0005 ≈ ¥5.6

加上查询时嵌入（开发+测试 ~5,000 次查询）:
5,000 × 10 tokens × ¥0.0005 ≈ ¥0.025

总费用: ~¥6
```

### 4.3 批量嵌入策略

```python
def batch_embed(questions: list[str], batch_size: int = 20) -> list[list[float]]:
    """
    批量调用 DashScope text-embedding-v4。

    batch_size=20: 留 25 上限的余量，避免单条过长导致超出 token 限制。
    带指数退避重试（API 限流时自动等待）。
    """
    embeddings = []
    for i in range(0, len(questions), batch_size):
        batch = questions[i:i+batch_size]
        result = embed_with_retry(embedder, batch, max_retries=3)
        embeddings.extend(result)
    return embeddings
```

### 4.4 入库时间估算

```
26 万条 ÷ 20 条/批次 = 13,000 次 API 调用
每次 ~150ms (含网络往返 + API 处理) × 13,000 ≈ 1,950s ≈ 33 分钟

建议: 加 tqdm 进度条 + 断点续传 (每 50 批存一次 checkpoint)
```

### 4.5 查询时嵌入

```python
# 每条用户查询仅需 1 次 API 调用
query_embedding = embedder.embed_query("小孩发烧怎么办？")
# → 1024 维向量，~100ms
# 然后走本地 ChromaDB 检索 (~20ms)
# 总查询延迟: ~120ms
```

---

## 5. ChromaDB 构建

### 5.1 Collection Schema

```python
collection = chroma_client.create_collection(
    name="huatuo_medical_qa",
    metadata={
        "description": "华佗医疗对话知识库",
        "embedding_model": "text-embedding-v4",
        "dimension": 1024,
        "total_records": 260000,
    }
)

# 每条记录
{
    "id": "huatuo_v2_000001",       # 唯一 ID，含来源标识
    "embedding": [0.123, ...],       # 1024 维 float32
    "document": "问：小孩发烧39度怎么办？\n答：小孩发烧39度属于高热...",
    "metadata": {
        "question": "小孩发烧39度怎么办？",
        "answer_length": 350,
        "source": "huatuo_v2",       # "huatuo_v1" | "huatuo_v2"
        "token_count": 213,
    }
}
```

### 5.2 存储预估

```
向量: 260,000 × 1024 维 × 4 bytes = 1.02 GB
文档: 260,000 × 400 字符 × 3 bytes = 312 MB
HNSW 索引: 1.02 GB × 0.3          = 306 MB
ChromaDB 元数据开销                 ≈ 100 MB
─────────────────────────────────────────
磁盘总计                            ≈ 1.8 GB
运行时内存 (索引加载)               ≈ 1.5 GB
```

> **16GB RAM + 206GB 磁盘空闲完全够用。**

### 5.3 断点续传设计

```python
# 每 50 批 (1000 条) 存一次 progress checkpoint
# 如果中断，下次运行直接从 checkpoint 恢复
# 避免 API 调用中断导致重头再来

checkpoint = {
    "last_index": 15000,     # 已处理到的索引
    "total_embedded": 15000,
}
```

---

## 6. 检索接口

### 6.1 `rag/retriever.py` 接口

```python
from langchain_community.embeddings import DashScopeEmbeddings
import chromadb

class MedicalRetriever:
    def __init__(self, persist_dir: str = "./data/chroma"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection("huatuo_medical_qa")
        self.embedder = DashScopeEmbeddings(model="text-embedding-v4")

    def search(self, query: str, k: int = 5) -> list[dict]:
        """检索 Top-K 相关医疗 QA"""
        embedding = self.embedder.embed_query(query)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)

    def _format_results(self, results) -> list[dict]:
        """将 ChromaDB 原始结果格式化为统一结构"""
        docs = []
        for i in range(len(results["ids"][0])):
            docs.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "question": results["metadatas"][0][i]["question"],
                "source": results["metadatas"][0][i]["source"],
                "score": 1 - results["distances"][0][i],  # distance → similarity
            })
        return docs

    def format_context(self, docs: list[dict]) -> str:
        """将检索结果格式化为 LLM context 文本"""
        parts = []
        for i, doc in enumerate(docs, 1):
            parts.append(f"[参考知识 {i}] (相关度: {doc['score']:.2f})\n{doc['content']}")
        return "\n\n".join(parts)
```

### 6.2 使用示例

```python
retriever = MedicalRetriever()

# 用户查询
docs = retriever.search("小孩发烧39度怎么办？", k=5)

# 格式化为 LLM prompt context
context = retriever.format_context(docs)

# 送入 LLM
response = llm.invoke(f"参考以下医学知识回答用户问题：\n{context}\n\n用户问题：小孩发烧39度怎么办？")
```

---

## 7. 测试验证

### 7.1 验证清单

| # | 检查项 | 方法 | 通过标准 |
|---|--------|------|---------|
| 1 | 清洗后记录数 | `collection.count()` | 260,000-270,000 |
| 2 | 检索命中率 | 20 条测试问题，人工评估 Top-5 相关性 | ≥90% 至少有 1 条相关 |
| 3 | 检索延迟 | `time.perf_counter()` 测 100 次取均值 | < 150ms (含 API 嵌入) |
| 4 | 断点续传 | 模拟中断 → 重新运行 | 从中断处继续，不重复嵌入 |
| 5 | 边界问题拒答 | 测试 "我今天头疼是不是脑瘤" | 返回知识不包含诊断结论 |

### 7.2 测试问题样本

```python
TEST_QUERIES = [
    # 常见症状
    "小孩发烧39度怎么办？",
    "咳嗽一个月了不见好，是什么原因？",
    "皮肤上长了红色的小疙瘩，很痒",
    # 慢性病
    "高血压患者饮食需要注意什么？",
    "2型糖尿病可以治愈吗？",
    # 药物
    "布洛芬和阿莫西林可以一起吃吗？",
    # 妇幼
    "产后脱发正常吗？会持续多久？",
    # 中医
    "上火有哪些症状？怎么降火？",
    # 边缘（应拒答）
    "我头疼是不是长了脑瘤？",  # ← 诊断类 → 拒答模板
]
```

### 7.3 RAG 质量评分

对 20 条测试问题，每条评估：

| 指标 | 评分标准 |
|------|----------|
| 检索相关性 (0-3) | 0=全不相关, 1=弱相关, 2=相关, 3=精准匹配 |
| 回答可用性 (0-3) | Top-1 检索结果能否作为 LLM 回答的有用素材 |
| 覆盖度 (0-3) | Top-5 是否覆盖了问题的不同侧面 |

---

## 8. 代码结构与执行顺序

### 8.1 文件清单

```
Medical-Health-Agent/
└── rag/
    ├── __init__.py
    ├── build_vectordb.py       # ★ 数据清洗 + ChromaDB 构建（一次性）
    ├── retriever.py            # ★ 检索接口（Phase 3 调用）
    └── test_retrieval.py       # 检索质量测试
```

### 8.2 执行顺序

```
Step 1: python rag/build_vectordb.py
        ↓ 一次性执行，耗时约 40 分钟
        ↓ 产出: data/chroma/huatuo_medical_qa/

Step 2: python rag/test_retrieval.py
        ↓ 验证检索质量
        ↓ 通过 → 进入 Phase 3

Step 3: Phase 3 Agent 中 import
        from rag.retriever import MedicalRetriever
```

### 8.3 `rag/build_vectordb.py` 伪代码

```python
#!/usr/bin/env python3
"""
构建华佗医疗 RAG 向量库
- 合并两个 JSONL 文件
- 清洗 + 去重
- DashScope text-embedding-v4 嵌入
- ChromaDB 持久化
"""
import json
import hashlib
import time
from pathlib import Path
from tqdm import tqdm
from langchain_community.embeddings import DashScopeEmbeddings
import chromadb

# ── 配置 ──────────────────────────────────────────────
DATA_DIR = Path("C:/Users/Lenovo/Desktop/huatuo_data")
FILES = [
    DATA_DIR / "HuatuoGPT2_sft_instruct_GPT4_sharegpt.jsonl",  # v2 优先
    DATA_DIR / "HuatuoGPT_sft_data_v1_sharegpt.jsonl",         # v1
]
CHROMA_DIR = "./data/chroma"
COLLECTION_NAME = "huatuo_medical_qa"
BATCH_SIZE = 20          # DashScope 单次最多 25 条
CHECKPOINT_EVERY = 50    # 每 50 批 (1000 条) 存一次进度

# ── Step 1: 合并 + 校验 ──────────────────────────────
def load_and_validate(file_path, seen_questions):
    """读取 JSONL，校验格式，去重"""
    records = []
    skipped = 0

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            convs = item.get("conversations", [])
            if not convs or len(convs) < 2:
                skipped += 1
                continue

            question = convs[0].get("value", "").strip()
            answer = convs[1].get("value", "").strip()

            if not question or not answer:
                skipped += 1
                continue

            # 质量过滤
            if len(answer) < 10:
                skipped += 1
                continue

            # 去重
            q_hash = hashlib.md5(question.encode()).hexdigest()
            if q_hash in seen_questions:
                skipped += 1
                continue
            seen_questions.add(q_hash)

            records.append({
                "question": question,
                "answer": answer,
                "source": "huatuo_v2" if "GPT4" in str(file_path) else "huatuo_v1",
            })

    print(f"  {file_path.name}: {len(records)} valid, {skipped} skipped")
    return records

# ── Step 2: 构建 ChromaDB ─────────────────────────────
def build_vectordb(records):
    embedder = DashScopeEmbeddings(model="text-embedding-v4")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"embedding_model": "text-embedding-v4", "dimension": 1024},
    )

    # 断点恢复
    start_idx = load_checkpoint()

    for i in tqdm(range(start_idx, len(records), BATCH_SIZE)):
        batch = records[i:i+BATCH_SIZE]
        questions = [r["question"] for r in batch]

        try:
            embeddings = embedder.embed_documents(questions)
        except Exception as e:
            print(f"  Batch {i} failed: {e}, retrying...")
            time.sleep(2)
            embeddings = embedder.embed_documents(questions)

        collection.add(
            embeddings=embeddings,
            documents=[f"问：{r['question']}\n答：{r['answer']}" for r in batch],
            metadatas=[{
                "question": r["question"],
                "answer_length": len(r["answer"]),
                "source": r["source"],
            } for r in batch],
            ids=[f"huatuo_{j:06d}" for j in range(i, i+len(batch))],
        )

        # 定期存 checkpoint
        if (i // BATCH_SIZE) % CHECKPOINT_EVERY == 0:
            save_checkpoint(i + len(batch))

    print(f"Done: {len(records)} records in ChromaDB at {CHROMA_DIR}")

# ── Main ──────────────────────────────────────────────
if __name__ == "__main__":
    all_records = []
    seen = set()

    for f in FILES:
        if f.exists():
            records = load_and_validate(f, seen)
            all_records.extend(records)
        else:
            print(f"  WARNING: {f} not found, skipping")

    print(f"\nTotal valid: {len(all_records)}")
    build_vectordb(all_records)
```

### 8.4 `rag/retriever.py` 完整代码

见 §6.1，文件创建时直接写入。

### 8.5 `rag/test_retrieval.py`

```python
"""检索质量测试"""
from retriever import MedicalRetriever
import time

TEST_QUERIES = [
    # (见 §7.2 完整列表)
]

def test_retrieval():
    retriever = MedicalRetriever()

    for query in TEST_QUERIES:
        t0 = time.perf_counter()
        docs = retriever.search(query, k=5)
        elapsed = (time.perf_counter() - t0) * 1000

        print(f"\nQ: {query}")
        print(f"  延迟: {elapsed:.0f}ms")
        for i, doc in enumerate(docs):
            print(f"  [{i+1}] score={doc['score']:.3f} | {doc['question'][:60]}...")

if __name__ == "__main__":
    test_retrieval()
```

---

## 附录 A：嵌入成本明细

```
入库:
  260,000 条 × 43 tokens/条 = 11.2M tokens
  11.2M / 1000 × ¥0.0005 = ¥5.6

查询 (开发期 + 月运营):
  开发测试: 5,000 次 × 10 tokens × ¥0.0005 ≈ ¥0.025
  月运营: 100次/天 × 30天 × 10 tokens × ¥0.0005 ≈ ¥0.15/月

总计: < ¥10
```

## 附录 B：常见问题

| 问题 | 原因 | 处理 |
|------|------|------|
| API Key 未配置 | 环境变量 DASHSCOPE_API_KEY 缺失 | `export DASHSCOPE_API_KEY=sk-xxx` |
| API 限流 (429) | 调用频率过高 | 指数退避重试，加 `time.sleep()` |
| 嵌入失败 (某条) | 文本过长或含特殊字符 | 跳过单条，记录日志，不阻塞全量 |
| ChromaDB OOM | 批次过大 | BATCH_SIZE 降到 10 |
| 进度丢失 | 未正常退出 | load_checkpoint() 自动恢复 |
