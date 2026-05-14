# 🖥️ 本地 RAG + 混合 Agent 方案：硬件适配分析

---

## 一、硬件实测数据

| 组件 | 规格 | 对 ML 部署的影响 |
|------|------|------------------|
| **GPU** | RTX 3060 Laptop 6GB (6144 MiB) | Compute Capability 8.6，支持 FlashAttention、BF16、Tensor Core |
| **GPU 空闲显存** | ~4.7 GB（系统 idle 时实测） | 实际可用 ≈ 4.5GB，需预留 0.5-1GB 余量 |
| **CPU** | AMD Ryzen 7 5800H (8C/16T, Zen 3) | 单核强、多核够，embedding 计算用 CPU 完全够 |
| **RAM** | 16GB DDR4，idle 时空闲 ~6.5GB | 向量库 + Ollama 常驻 ≈ 4-5GB，余量充足 |
| **磁盘** | 932GB，空闲 206GB | 数据集 + 模型 + 向量库 ≈ 20-30GB，绰绰有余 |

### 关键结论

> **6GB 显存是唯一瓶颈，但可以通过「GPU 只跑 LLM 推理 + CPU 跑 Embedding + 向量检索」的分工策略完美绕过。**

---

## 二、核心架构：DeepSeek V4 Flash 主 Agent + 本地 RAG + 本地微模型兜底

### 2.1 架构全景图

```
                          ┌─────────────────────────┐
                          │      LangGraph 调度层      │
                          │    Router + StateGraph    │
                          └─────────────┬─────────────┘
                                        │
                     ┌──────────────────┼──────────────────┐
                     │                  │                  │
                     ▼                  ▼                  ▼
              ┌────────────┐   ┌──────────────┐   ┌──────────────┐
              │  感知 Agent  │   │  分析 Agent   │   │  行动 Agent   │
              │ 数据聚合     │   │ 医疗问答       │   │ 对话/建议     │
              │ DeepSeek    │   │ DeepSeek      │   │ DeepSeek     │
              │ V4 Flash    │   │ V4 Flash      │   │ V4 Flash     │
              └──────┬──────┘   └──────┬───────┘   └──────┬───────┘
                     │                 │                   │
                     │          ┌──────┴───────┐           │
                     │          │              │           │
                     │          ▼              ▼           │
                     │   ┌────────────┐ ┌───────────┐     │
                     │   │   RAG 检索  │ │ 路由判断   │     │
                     │   │  ChromaDB  │ │ 离线/隐私   │     │
                     │   │  (本地)    │ │ /高频检测   │     │
                     │   └─────┬──────┘ └─────┬─────┘     │
                     │         │              │           │
                     │         │         ┌────┴────┐      │
                     │         │         ▼         ▼      │
                     │         │   ┌──────────┐ ┌───────┐ │
                     │         │   │ 在线模式  │ │离线    │ │
                     │         │   │ DeepSeek │ │模式    │ │
                     │         │   │ API      │ │本地LLM │ │
                     │         │   └──────────┘ └───┬───┘ │
                     │         │                    │     │
                     │         └───────┬────────────┘     │
                     │                 │                  │
                     ▼                 ▼                  ▼
              ┌──────────────────────────────────────────────┐
              │              共享 RAG 知识库 (ChromaDB)        │
              │   shibing624/huatuo_medical_qa_sharegpt       │
              │              22万条 医疗 QA                    │
              └──────────────────────────────────────────────┘
```

### 2.2 路由策略：何时触发本地模型

```python
# 路由判断逻辑（LangGraph conditional edge）
def route_to_model(state: AgentState) -> str:
    # 1. 离线检测：API 不可达
    if not api_available():
        return "local_model"

    # 2. 隐私模式：用户主动开启 或 检测到敏感数据
    if state.privacy_mode or contains_phi(state.query):
        return "local_model"

    # 3. 高频场景：过去 1 小时内 > 20 次请求（省 API 费用）
    if request_counter.last_hour() > 20:
        return "local_model"

    # 4. 默认走云端强模型
    return "cloud_model"
```

**三种触发场景的合理性：**

| 场景 | 触发条件 | 本地模型角色 |
|------|----------|-------------|
| 🚫 离线 | 网络断开 / API 故障 | 唯一推理引擎 |
| 🔒 隐私 | 用户开启隐私模式 / PHI 数据 | 确保数据不出本地 |
| 📈 高频 | 短时间内大量查询（节省成本） | 分担 API 负载 |

---

## 三、显存精算 & 模型选型

### 3.1 VRAM 预算表（总 6GB，可用 ~4.7GB）

| 策略 | LLM 模型 | LLM 显存 | KV Cache (4k ctx) | Embedding | 总占用 | 余量 | 判定 |
|------|----------|----------|-------------------|-----------|--------|------|------|
| **A（推荐）** | Qwen3-4B Q4_K_M | 2.5GB | 0.8GB | CPU运行 | **3.3GB** | 1.4GB | ✅ 最优 |
| B | Qwen3-1.7B Q8_0 | 1.8GB | 0.4GB | CPU运行 | **2.2GB** | 2.5GB | ✅ 更宽松 |
| C | Qwen3-8B Q4_K_M | 5.0GB | 1.0GB | CPU运行 | **6.0GB** | -1.3GB | ❌ 爆显存 |
| D | Qwen2.5-4B Q4_K_M | 2.5GB | 0.8GB | CPU运行 | **3.3GB** | 1.4GB | ✅ 备选 |
| E | Qwen3.5-4B Q4_K_M | 2.5GB | 0.8GB | CPU运行 | **3.3GB** | 1.4GB | ✅ 最新 |

### 3.2 最终推荐：Qwen3-4B Q4_K_M

**理由：**
- MedicalGPT 全流程适配 Qwen3 系列（Qwen3 和 Qwen3.5 均支持）
- 4B 参数量在 4bit 下仅占 2.5GB，留给 KV Cache 1.4GB → 可支撑 8k token 上下文
- 中文能力在 4B 级别模型中是最强的
- Compute Capability 8.6 支持 FlashAttention-2，推理速度有保障

### 3.3 Embedding 模型：CPU 运行，零显存占用

| 模型 | 大小 | 维度 | 中文效果 |
|------|------|------|----------|
| **BAAI/bge-small-zh-v1.5** | 24MB | 512 | ⭐⭐⭐⭐⭐ |
| shibing624/text2vec-base-chinese | 400MB | 768 | ⭐⭐⭐⭐ |
| BAAI/bge-base-zh-v1.5 | 400MB | 768 | ⭐⭐⭐⭐⭐ |

**推荐 `BAAI/bge-small-zh-v1.5`**：24MB 极小，CPU 单次查询嵌入 < 50ms，512 维节省存储。

---

## 四、RAG 知识库：数据集下载与构建

### 4.1 数据集选择

MedicalGPT 项目提供了两个可直接用于 RAG 的数据集：

```bash
# 1. 华佗医疗对话（推荐用于 RAG）—— 22万条中文医疗 QA
# HuggingFace: shibing624/huatuo_medical_qa_sharegpt
# 格式：ShareGPT 多轮对话，问题+回答结构清晰

# 2. 完整医疗数据集 —— 240万条（预训练+SFT+奖励数据）
# HuggingFace: shibing624/medical
# 太大，建议只取 SFT 子集用于 RAG
```

**推荐使用 `shibing624/huatuo_medical_qa_sharegpt`**：
- 22 万条，质量高、格式统一
- 每条都是明确的「问题 → 回答」结构
- 嵌入后向量库约 500MB，检索 < 50ms

### 4.2 数据下载脚本

```python
# scripts/download_medical_dataset.py
from datasets import load_dataset

# 下载华佗医疗对话数据集
dataset = load_dataset("shibing624/huatuo_medical_qa_sharegpt", split="train")
print(f"数据集大小: {len(dataset)} 条")

# 保存为本地 JSONL（防止重复下载）
dataset.to_json("data/huatuo_medical_qa.jsonl", force_ascii=False)
```

### 4.3 RAG 文档构建策略

每条 QA 对构建为两种文档类型（双索引策略）：

```python
# 类型 1：仅用问题做 embedding（检索更精准）
doc_question = {
    "id": "qa_001",
    "embedding_text": "小孩发烧怎么办？",       # ← 用于向量检索
    "content": "问：小孩发烧怎么办？\n答：发烧是身体对感染...",  # ← 完整内容喂给 LLM
    "metadata": {"type": "qa", "source": "huatuo"}
}

# 类型 2：问题+回答拼接做 embedding（召回更全）
doc_full = {
    "id": "qa_001",
    "embedding_text": "小孩发烧怎么办？发烧是身体对感染的自然反应...",
    "content": "问：小孩发烧怎么办？\n答：...",
    "metadata": {"type": "qa_full", "source": "huatuo"}
}
```

**推荐类型 1**：用问题检索问题，匹配更精准，避免答案中的噪声干扰 embedding。

### 4.4 向量库存储评估

```
22万条 QA × 512维 × 4字节(float32) = 450MB （向量数据）
22万条 × 平均500字符 × 3字节/字符  = 330MB （原始文本）
ChromaDB HNSW 索引开销              ≈ 150MB
─────────────────────────────────────────
总计（磁盘）                         ≈ 1GB
运行时内存占用                       ≈ 600-800MB
```

**16GB 系统内存完全够用**，还剩 5GB+ 给 Ollama 和其他进程。

---

## 五、本地模型：两条路径

### 路径 A：快速启动（1-2 天可上线）

用 **未经微调** 的 Qwen3-4B 通用模型 + 医疗 RAG。

```
通用 Qwen3-4B (Ollama)
    +
医疗 RAG (ChromaDB + huatuo 22万条)
    =
具备医疗知识的健康 Agent（靠 RAG 注入领域知识）
```

**优点**：
- 立即可用，无需训练
- Qwen3-4B 本身中文能力很强，加上 RAG 后医疗问答质量不差
- 快速验证整体架构

**缺点**：
- 缺少医学专业术语的深层理解
- 医患对话风格不够自然

### 路径 B：深度定制（2-3 周，简历亮点 ⭐）

用 **MedicalGPT 训练管线微调** 后的 Qwen3-4B-Medical + 医疗 RAG。

1、SFT（Supervised Fine-tuning  监督式微调）
2、DPO蒸馏（On-Policy Distillation  政策提炼）
3、合并Lora
4、量化

```bash
# 云端训练（租用 AutoDL / 恒源云，A100 约 5元/小时）
git clone https://github.com/shibing624/MedicalGPT
cd MedicalGPT

# Step 1: SFT 微调（约 4-6 小时，A100 40GB）
需要【指令微调数据集】
bash scripts/run_sft.sh  \
    --base_model Qwen/Qwen3-4B-Instruct \
    --train_file_dir data/sft/ \
    --dataset shibing624/medical \
    --output_dir ./output/qwen3-4b-medical-sft

# Step 2: DPO 对齐（约 2-3 小时）
bash scripts/run_dpo.sh \
    --base_model ./output/qwen3-4b-medical-sft \
    --train_file_dir data/reward/ \
    --output_dir ./output/qwen3-4b-medical-dpo

# Step 3: 合并 LoRA 权重
python tools/merge_peft_adapter.py \
    --base_model Qwen/Qwen3-4B-Instruct \
    --lora_model ./output/qwen3-4b-medical-dpo \
    --output_dir ./output/qwen3-4b-medical-merged

# Step 4: 量化为 GGUF Q4_K_M（本地执行）
# 用 llama.cpp 的 convert-hf-to-gguf.py + quantize
python llama.cpp/convert-hf-to-gguf.py ./output/qwen3-4b-medical-merged \
    --outtype f16 --outfile medical-qwen3-4b-f16.gguf
./llama.cpp/quantize medical-qwen3-4b-f16.gguf \
    medical-qwen3-4b-Q4_K_M.gguf Q4_K_M
```

**云端训练成本估算：**
- AutoDL A100 40GB：约 5 元/小时
- SFT (6h) + DPO (3h) ≈ 9 小时 ≈ **45 元人民币**
- 模型下载+上传：约 2 小时 ≈ 10 元
- **总成本：约 55-70 元**

### 路径 B 在简历上的展示价值

> **项目经验：本地医疗大模型部署**
> - 使用 MedicalGPT 训练管线（SFT + DPO）在云端完成 Qwen3-4B 的医疗领域微调
> - 采用 QLoRA 4bit 量化技术，将模型从 7.5GB 压缩至 2.5GB，适配 RTX 3060 6GB 边缘设备
> - 基于 ChromaDB + BGE 构建 22 万条医疗知识 RAG 系统，检索延迟 < 50ms
> - 设计 LangGraph 混合路由架构，实现云端 DeepSeek + 本地微模型的智能调度

---

## 六、系统资源运行时全景图

### 6.1 稳定运行态（所有服务启动后）

```
┌────────────────────────────────────────────────────────┐
│                    RTX 3060 6GB VRAM                    │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Ollama: Qwen3-4B Q4_K_M (2.5GB)                 │  │
│  │  + KV Cache 4k ctx (0.8GB)                       │  │
│  │  + CUDA Context (0.3GB)                          │  │
│  │  ─────────────────────────────                   │  │
│  │  GPU 占用: 3.6GB / 6GB (60%)                      │  │
│  │  空闲: 2.4GB                                      │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                    16GB System RAM                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │  ChromaDB (向量索引 + 缓存): 800MB                │  │
│  │  Ollama (模型部分 offload 到系统内存): 200MB       │  │
│  │  FastAPI 服务: 150MB                              │  │
│  │  LangGraph + Python runtime: 300MB                │  │
│  │  ─────────────────────────────                   │  │
│  │  应用占用: ~1.5GB / 16GB                          │  │
│  │  空闲: ~8GB（idle 6.5GB + 释放缓存后更多）         │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

> **结论：6GB VRAM + 16GB RAM 的配置，跑「本地 4B 模型 + RAG + Web 服务」稳定可行，且留有约 40% GPU 余量。**

---

## 七、完整技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| Agent 编排 | **LangGraph** | StateGraph + conditional edges 实现路由 |
| 主推理引擎 | **DeepSeek V4 Flash (API)** | 日常健康分析、医疗问答（主力） |
| 本地推理引擎 | **Ollama + Qwen3-4B Q4_K_M** | 离线/隐私/高频场景兜底 |
| RAG 向量库 | **ChromaDB** (persistent) | 22 万条医疗 QA 检索 |
| Embedding | **BGE-small-zh-v1.5** (CPU) | 查询 + 文档向量化 |
| 后端 | **FastAPI** | API 服务 + Webhook 接收 Apple Health |
| 数据存储 | **SQLite** (初期) | 健康数据 + 对话历史 |
| 前端 | **Gradio** 或 **Telegram Bot** | 用户交互 |
| 模型训练 | **MedicalGPT** (云端 A100) | SFT + DPO 微调 |
| 模型量化 | **llama.cpp quantize** | GGUF Q4_K_M 量化 |

---

## 八、实施步骤（更新版）

### Phase 1：RAG 基础设施（第 1 周）

```bash
# 1. 安装依赖
pip install chromadb sentence-transformers datasets langgraph fastapi ollama

# 2. 下载医疗数据集
python scripts/download_medical_dataset.py

# 3. 构建向量库
python scripts/build_vectordb.py

# 4. 验证检索效果
python scripts/test_retrieval.py
```

### Phase 2：本地模型部署（第 1-2 周）

```bash
# 方案 A：快速启动 —— 直接用 Ollama 拉通用模型
ollama pull qwen2.5:4b-instruct-q4_K_M  # 或 qwen3:4b

# 方案 B：深度定制 —— 云端 MedicalGPT 训练（同步进行）
# 在 AutoDL / 恒源云租 A100，按上面「路径 B」步骤执行
```

### Phase 3：LangGraph Agent 搭建（第 2-3 周）

核心文件结构：
```python
# agents/graph.py
from langgraph.graph import StateGraph, END

# 定义状态
class AgentState(TypedDict):
    query: str
    privacy_mode: bool
    route: str              # "cloud" | "local"
    retrieved_docs: list
    response: str

# 构建图
graph = StateGraph(AgentState)

graph.add_node("router", router_node)         # 路由判断
graph.add_node("retrieve", retrieve_node)     # RAG 检索
graph.add_node("cloud_llm", cloud_llm_node)   # DeepSeek API
graph.add_node("local_llm", local_llm_node)   # Ollama 本地模型

graph.set_entry_point("router")
graph.add_conditional_edges("router", route_to_model, {
    "cloud": "retrieve",
    "local": "retrieve",     # 两种模式都先走 RAG
})
graph.add_edge("retrieve", "cloud_llm")       # 但实际走哪个 LLM 由 router 决定
# ... 更精细的条件边
```

### Phase 4：Apple Health 接入 + 前端（第 3-4 周）

同原方案 Phase 1 & 4。

---

## 九、风险与应对

| 风险 | 概率 | 应对 |
|------|------|------|
| 6GB 显存不够跑 4B + 长上下文 | 低 | 降级到 Qwen3-1.7B，或限制 ctx 到 2k |
| ChromaDB 22万条检索变慢 | 低 | HNSW 索引保证 < 50ms；如超 100ms 可降采样到 10 万条 |
| 本地模型医疗回答质量差 | 中 | 用「自我怀疑机制」：本地出初稿 → 云端（如可用）做 sanity check |
| Ollama 在 Windows 上不稳定 | 中 | Ollama 有原生 Windows 版本，或用 Docker 运行 |
| 云端训练 OOM | 低 | MedicalGPT 支持 QLoRA 4bit，7B 仅需 6GB；4B 更轻松 |

---

## 十、总结

```
┌─────────────────────────────────────────────────────────────────┐
│                     推荐最终方案                                  │
│                                                                  │
│  主 Agent:  DeepSeek V4 Flash (API) ← 主力推理                   │
│  本地兜底: Qwen3-4B Q4_K_M (Ollama) ← 离线/隐私/高频              │
│  知识库:   ChromaDB + huatuo 22万条医疗 QA ← 共享 RAG             │
│  Embed:    BGE-small-zh-v1.5 (CPU) ← 零显存                      │
│  编排:     LangGraph StateGraph ← 路由 + 多节点编排               │
│                                                                  │
│  VRAM:     3.6GB / 6GB (60%) ✅                                  │
│  RAM:      1.5GB / 16GB (9%)  ✅                                 │
│  训练成本:  ~55 元 (A100, 9h)                                     │
│  上线周期:  快速版 1 周 / 完整版 4 周                              │
└─────────────────────────────────────────────────────────────────┘
```
