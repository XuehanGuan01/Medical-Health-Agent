# 🏥 MedicalGPT 云训练 + 本地部署 全流程方案

> 基于 MedicalGPT v2.7 源码分析 | 目标模型：Qwen3.5-4B | 本地部署：RTX 3060 6GB

---

## 一、模型选型决策

### 1.1 MedicalGPT 已适配的 Qwen 系列

从仓库 `training/template.py` 和 `README.md` 中确认的模板支持：

| 系列 | 可用尺寸 | 模板名 | 特点 |
|------|---------|--------|------|
| Qwen3 | 0.6B / 1.7B / 4B / 8B / 14B / 32B / 235B | `qwen3` / `qwen3_nothink` | 成熟稳定，有 Instruct 版本 |
| **Qwen3.5** | **0.8B / 2B / 4B** / 9B / 27B / 35B / 122B | `qwen3_5` / `qwen3_5_nothink` | **最新一代，推理能力更强** |

### 1.2 最终选择：Qwen3.5-4B

```
模型: Qwen/Qwen3.5-4B
模板: qwen3_5_nothink  ← 禁用 thinking mode，减少医疗场景的冗余 token
参数量: 4B
BF16 大小: ~8GB
4bit (Q4_K_M): ~2.5GB ← 部署在 RTX 3060 6GB 上
```

**为什么选 Qwen3.5-4B 而不是 Qwen3-4B-Instruct？**

| 维度 | Qwen3.5-4B | Qwen3-4B-Instruct |
|------|-----------|-------------------|
| 发布时间 | 2025 Q4 | 2024 Q4 |
| 推理能力 | 更强（原生 thinking） | 标准 |
| 中文表现 | 优于 Qwen3 | 良好 |
| MedicalGPT 适配 | ✅ 完整（v2.5+） | ✅ 完整 |
| 本地 6GB 部署 | ✅ ~2.5GB | ✅ ~2.5GB |
| Instruct 版本 | Base（需 SFT 注入指令能力） | 已有 Instruct |

> **风险提示**：Qwen3.5-4B 截至写稿时可能只有 Base 版本。如果 HuggingFace 上没有 `Qwen/Qwen3.5-4B` 或下载失败，**一键切换为 `Qwen/Qwen3-4B-Instruct` + 模板 `qwen3_nothink`**，所有后续步骤完全兼容。

### 1.3 备选方案（一键切换）

```bash
# 方案 A（主推荐）
BASE_MODEL="Qwen/Qwen3.5-4B"
TEMPLATE="qwen3_5_nothink"

# 方案 B（如果 Qwen3.5-4B 不可用）
BASE_MODEL="Qwen/Qwen3-4B-Instruct"
TEMPLATE="qwen3_nothink"

# 方案 C（如果 4B 训练 OOM，降到 2B）
BASE_MODEL="Qwen/Qwen3.5-2B"
TEMPLATE="qwen3_5_nothink"
```

---

## 二、GPU 算力选择

### 2.1 云 GPU 选项

| GPU | 显存 | 单价 | 适用场景 |
|-----|------|------|----------|
| **RTX 4090** | 24 GB | **1.88 元/小时** | 4B LoRA SFT + OPD，性价比最高 |
| RTX 5090 | 32 GB | 2.78 元/小时 | 更大 batch size，适合 8B+ 模型 |

### 2.2 VRAM 精算（训练时）

#### SFT（监督微调）

```
Qwen3.5-4B BF16 权重:           ~8.0 GB
LoRA 参数 (rank=16):            ~0.1 GB
LoRA 优化器状态 (AdamW):         ~0.2 GB
中间激活 (batch=4, seq=2048):    ~3.0 GB  (with gradient checkpointing)
CUDA context + 其他:             ~1.0 GB
─────────────────────────────────────────
总计:                           ~12.3 GB  → 4090 24GB ✅ 充足
```

#### OPD（策略蒸馏，可选）

```
Student (4B BF16 + LoRA):       ~8.5 GB
Teacher (8B, 4bit 加载):        ~5.0 GB
中间激活 + TRL 框架开销:          ~4.0 GB
─────────────────────────────────────────
总计:                           ~17.5 GB  → 4090 24GB ✅ 可行
```

### 2.3 结论：选 RTX 4090 24GB @ 1.88 元/小时

**理由**：
- 4B 模型 LoRA 训练不需要 32GB 显存，5090 的额外 8GB 用不上
- 价格便宜 32%，同样预算可以跑更久
- 如果未来要训练 8B+ 模型，再切到 5090

### 2.4 云平台选择

| 平台 | 4090 价格 | 特点 |
|------|----------|------|
| **AutoDL** | ~1.88 元/h | 国内首选，社区活跃，预装 CUDA/PyTorch |
| 恒源云 | ~2.0 元/h | 有新人优惠 |
| 矩池云 | ~1.90 元/h | 支持按量计费 |

> **推荐 AutoDL**：选「北京/上海」区域的 4090 实例，基础镜像选「PyTorch 2.3.0 + CUDA 12.1 + Python 3.10」。

---

## 三、完整训练流程（Linux 云端）

### 3.1 环境初始化

```bash
# ========== 1. 基础环境（AutoDL 镜像已预装 CUDA/PyTorch，跳过） ==========

# 2. 克隆 MedicalGPT
cd /root/autodl-tmp
git clone https://github.com/shibing624/MedicalGPT.git
cd MedicalGPT

# 3. 安装依赖
pip install -r requirements.txt --upgrade
pip install flash-attn --no-build-isolation
pip install ninja
# 4. OPD 需要 TRL >= 0.29.0（注意引号）
pip install "trl>=0.29.0"

# 5. 安装数据下载辅助库
pip install requests

# 6. 设置 HF 镜像（国内加速）
export HF_ENDPOINT=https://hf-mirror.com

# 7. 验证 GPU 和 FlashAttention
python -c "
import torch
print(f'CUDA: {torch.cuda.is_available()}')
print(f'GPU: {torch.cuda.get_device_name(0)}')
print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
"
python -c "import flash_attn; print('FlashAttention-2 OK')"
```

### 3.2 数据准备

> **为什么不用 `datasets` 库直接加载？** `shibing624/medical` 依赖自定义脚本 `medical.py`，新版 `datasets>=3.0` 已不支持。改用 HTTP 直接下载原始 JSON + 格式转换。

```bash
# ========== 用 prepare_data.py 一键完成所有数据准备 ==========
# 将本地的 prepare_data.py 上传到云服务器后执行
python prepare_data.py
```

**`prepare_data.py` 做了什么：**

| 步骤 | 操作 | 产出 |
|------|------|------|
| 1 | `datasets` 加载华佗 QA（这个没问题） | `huatuo_medical_qa.jsonl`（27.6万条） |
| 2 | HTTP 下载 `finetune/train_zh_0.json` + `train_en_1.json` + `valid_zh_0.json` | 下载的原始 JSONL |
| 3 | Alpaca → ShareGPT 格式转换 | 统一 `conversations` 格式 |
| 4 | 写入 `medical_sft_finetune.jsonl` | ~70万条有效数据 |
| 5 | 可选：下载 pretrain 数据 | `medical_pretrain.jsonl` |

**背后的数据格式转换逻辑：**

```python
# 源格式 (Alpaca)
{"instruction": "血热的临床表现是什么?", "input": "", "output": "初发或复发病不久..."}

# → 目标格式 (ShareGPT)
{"conversations": [
    {"from": "human", "value": "血热的临床表现是什么?"},
    {"from": "gpt", "value": "初发或复发病不久..."}
]}
```

**执行后的 `data/sft/` 目录：**

```
data/sft/
├── huatuo_medical_qa.jsonl          ← 27.6万条 华佗对话 (ShareGPT)
├── medical_sft_finetune.jsonl       ← ~70万条 医疗指令 (ShareGPT)
├── medical_pretrain.jsonl           ← 20万条 预训练文本 (可选)
├── medical_sft_1K_format.jsonl      ← 项目自带 1000条 医疗SFT
├── glaive_toolcall_zh_demo.jsonl    ← 项目自带 300条 Tool Call
└── sharegpt_zh_1K_format.jsonl      ← 项目自带 1000条 通用对话
```

> **注意**：`medical_sft_finetune.jsonl` 下载失败的话，检查 `prepare_data.py` 中的 `HF_BASE` 变量（应使用 `hf-mirror.com`）。

### 3.3 第一阶段：SFT 监督微调

```
# 1. 开启 AutoDL 学术加速（必须执行，否则下载极慢） 
source /etc/network_turbo
# 确保已设置镜像 
export HF_ENDPOINT=https://hf-mirror.com

```

> **源码依据**：所有参数均来自 `training/supervised_finetuning.py` 的 `ModelArguments` + `DataArguments` + `ScriptArguments` + HuggingFace `Seq2SeqTrainingArguments`。

```bash
# ========== SFT 训练脚本 ==========
# 数据目录 ./data/sft/ 下所有 .jsonl 文件自动合并训练
# 等效 batch = per_device_train_batch_size × gradient_accumulation_steps × GPU数 = 2 × 8 × 2 = 32
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export CUDA_VISIBLE_DEVICES=0,1
torchrun --nproc_per_node 2 training/supervised_finetuning.py \
    --model_name_or_path Qwen/Qwen3.5-4B \
    --template_name qwen3_5_nothink \
    --train_file_dir ./data/sft \
    --validation_file_dir ./data/sft \
    --per_device_train_batch_size 2 \
    --per_device_eval_batch_size 2 \
    --do_train \
    --do_eval \
    --use_peft True \
    --max_train_samples -1 \
    --max_eval_samples 200 \
    --model_max_length 1024 \
    --num_train_epochs 3 \
    --learning_rate 2e-5 \
    --warmup_ratio 0.05 \
    --weight_decay 0.05 \
    --logging_strategy steps \
    --logging_steps 20 \
    --eval_steps 500 \
    --eval_strategy steps \
    --save_steps 1000 \
    --save_strategy steps \
    --save_total_limit 3 \
    --gradient_accumulation_steps 8 \
    --preprocessing_num_workers 8 \
    --output_dir ./outputs/qwen3.5-4b-medical-sft \
    --ddp_timeout 30000 \
    --logging_first_step True \
    --target_modules all \
    --lora_rank 16 \
    --lora_alpha 32 \
    --lora_dropout 0.05 \
    --torch_dtype bfloat16 \
    --bf16 \
    --seed 42 \
    --report_to tensorboard \
    --ddp_find_unused_parameters False \
    --gradient_checkpointing True \
    --tool_format default \
    --cache_dir ./cache \
    --flash_attn True
```

**参数来源对照（代码 → 命令）：**

| 参数                       | 定义位置                       | 说明                                              |
| ------------------------ | -------------------------- | ----------------------------------------------- |
| `--model_name_or_path`   | `ModelArguments`           | 基座模型 HF 路径                                      |
| `--template_name`        | `ScriptArguments`          | `qwen3_5_nothink` 禁用 thinking mode              |
| `--train_file_dir`       | `DataArguments`            | 自动递归加载目录下所有 `*.jsonl`                           |
| `--flash_attn`           | `ModelArguments`           | 启用 FlashAttention-2（需 `pip install flash-attn`） |
| `--use_peft`             | `ScriptArguments`          | 启用 LoRA 微调                                      |
| `--lora_rank/lora_alpha` | `ScriptArguments`          | rank=16, alpha=32（rank 的 2 倍）                   |
| `--target_modules all`   | `ScriptArguments`          | 自动检测所有 linear 层                                 |
| `--tool_format default`  | `ScriptArguments`          | 支持 Agent Function Call 混合训练                     |
| `--max_train_samples -1` | `DataArguments`            | -1 表示使用全部数据                                     |
| `--model_max_length`     | `ScriptArguments`          | 上下文截断长度                                         |
| `--warmup_ratio`         | `Seq2SeqTrainingArguments` | 替代 `warmup_steps`，更稳健                           |
| `--bf16`                 | `Seq2SeqTrainingArguments` | BF16 混合精度（Compute Capability 8.6 支持）            |

**训练完成后，输出目录结构：**

```
outputs/qwen3.5-4b-medical-sft/
├── adapter_config.json          ← LoRA 配置 (rank, alpha, target_modules)
├── adapter_model.safetensors    ← LoRA 权重 (~100MB)
├── trainer_state.json           ← 训练状态 (loss, step, epoch)
└── checkpoint-*/                ← 分步保存的 checkpoint
```

**预期指标**：

| 项目                | 估值                         |
| ----------------- | -------------------------- |
| 训练数据量             | ~97 万条（27.6万华佗 + 70万医疗SFT） |
| 等效 batch size     | 32                         |
| 总步数 (3 epochs)    | ~91,000 步                  |
| 每步耗时              | ~0.3-0.5 秒                 |
| **总训练时间**         | **~8-12 小时**               |
| **费用 (RTX 4090)** | **~15-23 元**               |

### 3.4 第二阶段（可选）：OPD 策略蒸馏

> **源码依据**：参数来自 `training/opd_training.py` 的 `ModelArguments` + `DataArguments` + `OPDScriptArguments` + TRL `GKDConfig`。

OPD（On-Policy Distillation）用一个更强的冻结教师模型指导小模型，提升输出质量。教师模型用 4bit 加载以节省显存。

```bash
# ========== OPD 蒸馏训练 ==========
# 教师: Qwen3-8B-Instruct (4bit)  → 学生: Qwen3.5-4B (BF16 + LoRA)
# 注意: Qwen3.5 系列没有 8B 尺寸，所以教师用 Qwen3-8B-Instruct

CUDA_VISIBLE_DEVICES=0 torchrun --nproc_per_node 1 training/opd_training.py \
    --model_name_or_path ./outputs/qwen3.5-4b-medical-sft \
    --teacher_model_name_or_path Qwen/Qwen3-8B-Instruct \
    --template_name qwen3_5_nothink \
    --train_file_dir ./data/sft \
    --validation_file_dir ./data/sft \
    --per_device_train_batch_size 2 \
    --per_device_eval_batch_size 1 \
    --do_train \
    --do_eval \
    --use_peft True \
    --teacher_load_in_4bit True \
    --max_train_samples -1 \
    --max_eval_samples 100 \
    --max_prompt_length 1024 \
    --max_new_tokens 512 \
    --num_train_epochs 1 \
    --learning_rate 5e-5 \
    --warmup_steps 10 \
    --weight_decay 0.05 \
    --logging_strategy steps \
    --logging_steps 10 \
    --eval_steps 500 \
    --eval_strategy steps \
    --save_steps 1000 \
    --save_strategy steps \
    --save_total_limit 2 \
    --gradient_accumulation_steps 8 \
    --preprocessing_num_workers 4 \
    --output_dir ./outputs/qwen3.5-4b-medical-opd \
    --ddp_timeout 30000 \
    --logging_first_step True \
    --target_modules all \
    --lora_rank 16 \
    --lora_alpha 32 \
    --lora_dropout 0.05 \
    --torch_dtype bfloat16 \
    --bf16 \
    --seed 42 \
    --report_to tensorboard \
    --ddp_find_unused_parameters False \
    --gradient_checkpointing True \
    --flash_attn True \
    --opd_lambda 0.5 \
    --opd_beta 0.5 \
    --temperature 0.9 \
    --tool_format default \
    --cache_dir ./cache
```

**参数来源对照（代码 → 命令）：**

| 参数 | 定义位置 | 说明 |
|------|------|------|
| `--teacher_model_name_or_path` | `GKDConfig` | 教师模型（4bit 冻结，仅做前向） |
| `--teacher_load_in_4bit` | `OPDScriptArguments` | 教师用 4bit 加载，节省 ~60% 显存 |
| `--max_prompt_length` | `OPDScriptArguments` | prompt 最大 token 数 |
| `--max_new_tokens` | `GKDConfig` | 生成长度上限 |
| `--opd_lambda` | `OPDScriptArguments` | 蒸馏 loss 权重（0.5 = 均衡） |
| `--opd_beta` | `OPDScriptArguments` | JSD/KL 插值系数 |
| `--temperature` | `GKDConfig` | 蒸馏温度（0.9 = 偏平滑分布） |
| `--template_name` | `OPDScriptArguments` | 需与 SFT 阶段一致 |
| `--flash_attn` | `ModelArguments` | OPD 同样支持 FA2 加速 |

**预期**: ~3-5 小时 | 费用 (RTX 4090): ~6-10 元

> **关于是否做 OPD**：OPD 能显著提升模型输出的流畅度和医学专业性。**建议先用纯 SFT 模型跑一次推理测试，输出质量满意就跳过 OPD**。简历上 SFT + OPD 全链路更有分量。

### 3.5 第三阶段：合并 LoRA 权重

```bash
# 合并 LoRA 到 Base Model（无论是否做了 OPD，操作相同）
# 如果做了 OPD，lora_model 指向 OPD 输出；
# 如果只做了 SFT，lora_model 指向 SFT 输出。

python tools/merge_peft_adapter.py \
    --base_model Qwen/Qwen3.5-4B \
    --lora_model ./outputs/qwen3.5-4b-medical-opd \
    --output_dir ./outputs/qwen3.5-4b-medical-merged

# 注意：如果 base_model 在 HuggingFace 上，会自动下载。
# 如果本地已有缓存，可以使用本地路径。
```

### 3.6 第四阶段：量化为 GGUF（本地执行）

合并后的完整模型约 8GB（BF16），需要量化为 GGUF Q4_K_M 才能在 RTX 3060 6GB 上运行。

> **注意**：量化步骤建议在本地执行（不需要 GPU），或者直接在云服务器上做然后下载到本地。

```bash
# ========== 方案 A：用 llama.cpp 量化（推荐，最通用） ==========
# 1. 克隆并编译 llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
make -j8

# 2. 转换 HF 模型 → GGUF FP16
python convert_hf_to_gguf.py \
    ../outputs/qwen3.5-4b-medical-merged \
    --outtype f16 \
    --outfile ../outputs/qwen3.5-4b-medical-f16.gguf

# 3. 量化 FP16 → Q4_K_M
./llama-quantize \
    ../outputs/qwen3.5-4b-medical-f16.gguf \
    ../outputs/qwen3.5-4b-medical-Q4_K_M.gguf \
    Q4_K_M

# 最终产物: qwen3.5-4b-medical-Q4_K_M.gguf (~2.5GB)
```

```bash
# ========== 方案 B：用 Ollama 直接导入（更简单） ==========
# 1. 创建 Modelfile
cat > Modelfile << 'EOF'
FROM ./outputs/qwen3.5-4b-medical-Q4_K_M.gguf
TEMPLATE """<|im_start|>system
{{ .System }}<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"""
SYSTEM """你是一个专业的医疗健康助手。你具备丰富的医学知识，能够：
1. 根据用户的症状描述提供初步分析（仅供参考，不构成诊断）
2. 解释医学术语和检查报告
3. 提供健康生活方式的建议
4. 在必要时建议就医

重要准则：
- 你必须强调你的回答仅供参考，不能替代专业医生的诊断
- 遇到紧急症状（胸痛、呼吸困难、严重外伤等），优先建议立即就医
- 不要开具处方或推荐具体药物剂量
- 保持专业、温和、共情的语气"""
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER top_k 40
EOF

# 2. 导入 Ollama
ollama create medical-agent -f Modelfile

# 3. 测试
ollama run medical-agent "我最近经常头痛，可能是什么原因？"
```

### 3.7 云端产物打包下载

```bash
# 在云服务器上打包所有产物
cd /root/autodl-tmp/MedicalGPT
tar -czf medical-model-final.tar.gz \
    outputs/qwen3.5-4b-medical-merged/ \
    outputs/qwen3.5-4b-medical-Q4_K_M.gguf \
    outputs/qwen3.5-4b-medical-sft/  # 保留 LoRA 权重以备后用

# 下载到本地（在本地终端执行）
# scp root@<云服务器IP>:/root/autodl-tmp/MedicalGPT/medical-model-final.tar.gz .
```

---

## 四、本地部署集成

### 4.1 本地环境

```bash
# Windows 上安装 Ollama（如已安装跳过）
# 官网下载: https://ollama.com/download/windows

# 验证 GPU 可用
ollama run qwen2.5:0.5b "你好"  # 快速测试

# 导入自定义模型
ollama create medical-agent -f Modelfile

# 启动 Ollama 服务（默认监听 localhost:11434）
ollama serve
```

### 4.2 LangGraph 集成

```python
# agents/medical_consultant.py
from langchain_ollama import ChatOllama
from langchain_deepseek import ChatDeepSeek
from langgraph.graph import StateGraph, END
from typing import TypedDict

class MedicalState(TypedDict):
    query: str
    privacy_mode: bool
    use_local: bool
    retrieved_docs: list[str]
    response: str
    source: str  # "cloud" | "local"

# 本地模型（Ollama）
local_llm = ChatOllama(
    model="medical-agent",
    temperature=0.3,
    num_predict=1024,
)

# 云端模型（DeepSeek API）
cloud_llm = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0.15,
    max_tokens=2048,
)

def router(state: MedicalState) -> str:
    """路由判断：在线/离线/隐私/高频"""
    if state.get("privacy_mode"):
        return "local"
    if state.get("use_local"):
        return "local"
    # 可以加 API 可用性检测
    return "cloud"

# 构建 LangGraph
graph = StateGraph(MedicalState)
graph.add_node("retrieve", retrieve_medical_knowledge)  # RAG 检索
graph.add_node("local_llm", local_llm_node)
graph.add_node("cloud_llm", cloud_llm_node)
# ... 添加边和条件路由
```

### 4.3 推理性能预估（RTX 3060 6GB）

| 指标 | 估值 |
|------|------|
| 模型加载时间（冷启动） | ~5-8 秒 |
| 推理速度 (Q4_K_M, 4k ctx) | ~25-35 tokens/s |
| 首 token 延迟 | ~1-2 秒 |
| 并发能力 | 1 路（6GB 显存不支持批处理） |
| 日常医疗问答体验 | ✅ 流畅，对话无明显等待 |

---

## 五、成本总览

| 阶段 | 操作 | GPU | 耗时 | 费用 |
|------|------|-----|------|------|
| 环境搭建 | 装包 + 下载模型 | 4090 | ~0.5h | ~1 元 |
| 数据准备 | prepare_data.py 下载 ~97万条 | 4090 | ~0.5h | ~1 元 |
| **SFT 训练** | LoRA rank=16, 3 epochs | 4090 | **~8-12h** | **~15-23 元** |
| OPD 蒸馏（可选） | 教师 Qwen3-8B 4bit | 4090 | 3-5h | ~6-10 元 |
| 合并 + 量化 | CPU | 本地/云端 | ~0.5h | 0 |
| **合计（含 OPD）** | | | **~12-18h** | **~23-35 元** |
| **合计（仅 SFT）** | | | **~9-13h** | **~17-25 元** |

---

## 六、关键参数速查表

训练时如需调整，以下是最关键的几个参数：

| 参数 | Demo 默认值 | 生产建议值 | 说明 |
|------|------------|-----------|------|
| `--lora_rank` | 8 | **16** | 秩越大，LoRA 容量越大 |
| `--lora_alpha` | 16 | **32** | rank 的 2 倍 |
| `--model_max_length` | 512 | **2048** | 医疗问答需要较长上下文 |
| `--num_train_epochs` | 1 | **3** | 数据量大可减到 2 |
| `--learning_rate` | 2e-5 | **2e-5** | LoRA 训练的标准 lr |
| `--per_device_train_batch_size` | 2 | **4** | 4090 24GB 可开到 4 |
| `--gradient_accumulation_steps` | 8 | **8** | 等效 batch=32 |
| `--max_train_samples` | 1000 | **-1** | -1 = 使用全部数据 |
| `--template_name` | 不指定 | **qwen3_5_nothink** | 禁用 thinking 节省 token |

---

## 七、故障预案

### 7.1 训练时 OOM

```bash
# 方案 1: 减小 batch size（等效 batch 不变）
--per_device_train_batch_size 2 --gradient_accumulation_steps 16

# 方案 2: 减小上下文长度
--model_max_length 1024  # SFT
--max_prompt_length 512 --max_new_tokens 256  # OPD

# 方案 3: 降级到 2B 模型（最稳）
--model_name_or_path Qwen/Qwen3.5-2B
# 同时 OPD 教师也换成更小的
--teacher_model_name_or_path Qwen/Qwen3-4B-Instruct

# 方案 4: 单卡不够加卡（需租 2×4090）
# torchrun --nproc_per_node 2 ...  → 显存翻倍，速度翻倍，但费用也翻倍
```

### 7.2 模型下载失败

```bash
# Qwen3.5-4B HF 路径可能的变体
# Qwen/Qwen3.5-4B              ← 大概率是这个
# Qwen/Qwen3.5-4B-Base         ← 或者是这个
# Qwen/Qwen3.5-4B-Instruct     ← 如果发布了 Instruct 版

# 先验证路径是否存在
python -c "from huggingface_hub import list_repo_refs; print(list_repo_refs('Qwen/Qwen3.5-4B'))"

# 如果 404，一键切换到 Qwen3-4B-Instruct
# 全局替换：Qwen/Qwen3.5-4B → Qwen/Qwen3-4B-Instruct
# 全局替换：qwen3_5_nothink  → qwen3_nothink

# 国内镜像加速
export HF_ENDPOINT=https://hf-mirror.com
```

### 7.3 本地 Ollama 启动失败

```bash
# 检查 Ollama 日志
ollama serve  # 前台运行查看错误

# 常见问题：Windows 上 GPU 未被识别
# 解决：更新 NVIDIA 驱动到 535+

# 如果 GPU 推理失败，可用 CPU 模式（较慢但可用）
ollama create medical-agent-cpu -f Modelfile
# 在 Modelfile 中去掉 GPU 相关配置
```

### 7.4 数据下载失败（shibing624/medical）

```bash
# 方案 1: 换回 HF 官方域名（hf-mirror 可能限流）
export HF_ENDPOINT=https://huggingface.co
python prepare_data.py

# 方案 2: 手动下载单个文件排查
wget "https://hf-mirror.com/datasets/shibing624/medical/resolve/main/finetune/train_zh_0.json"

# 方案 3: 如果 finetune 文件全部不可用，只用华佗数据集（27.6万条也能训练）
# 删除 prepare_data.py 中的 process_medical_finetune() 调用，
# SFT 训练时 --num_train_epochs 可以加到 5 来补偿数据量不足
```

---

## 八、时间线

```
Day 1 上午   环境搭建 + 数据准备（prepare_data.py，1 小时）
Day 1 中午   SFT 训练启动，8-12 小时后台运行
Day 2 凌晨   SFT 完成，查看 loss → 决定是否做 OPD
Day 2 上午   OPD 训练（可选，3-5 小时）
Day 2 下午   合并 LoRA + 量化 GGUF（1 小时）
Day 2 晚上   打包下载到本地 + Ollama 导入 + 推理测试
Day 3        接入 LangGraph Agent + RAG + 端到端联调
```

**总计：2-3 天完成从训练到本地部署的全链路。**

---

## 九、总结

```
┌──────────────────────────────────────────────────────────────────┐
│                    最终方案一句话总结                               │
│                                                                   │
│  云端 RTX 4090 (1.88元/h) → prepare_data.py 数据准备              │
│  → MedicalGPT SFT (Qwen3.5-4B, LoRA rank=16, ~97万条)             │
│  → 可选 OPD (教师 Qwen3-8B-Instruct, 4bit)                        │
│  → merge_peft_adapter.py 合并 → llama.cpp 量化 Q4_K_M (2.5GB)     │
│  → 下载到本地 → Ollama 部署 → LangGraph Agent 接入                 │
│                                                                   │
│  总成本: ~23-35 元 (含OPD) 或 ~17-25 元 (仅SFT)                    │
│  总耗时: 2-3 天 | 本地显存占用: ~3.6GB                             │
└──────────────────────────────────────────────────────────────────┘
```
