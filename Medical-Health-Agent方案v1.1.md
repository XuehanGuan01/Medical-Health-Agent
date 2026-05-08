# 🏥 Medical-Health-Agent 可行性分析与优化方案 v1

---

## 一、核心可行性判断

| 维度                      | 可行性           | 关键风险                  |
| ----------------------- | ------------- | --------------------- |
| Apple Health 数据采集       | ⭐⭐⭐⭐⭐ 极高      | 数据聚合层的设计质量            |
| LLM 健康数据分析              | ⭐⭐⭐⭐⭐ 极高      | Prompt 设计，幻觉控制        |
| MedicalGPT 7B 本地部署      | ⭐⭐⭐ **有条件可行** | **6GB 显存是硬瓶颈**        |
| 三层 Agent 架构 (LangGraph) | ⭐⭐⭐⭐ 高        | 学习曲线，但 LangGraph 文档成熟 |

### ⚠️ 最关键的风险点：6GB 显存

计算（7B × 4bit ≈ 5GB）只算了**模型权重本身**。实际推理时还要占用：

| 组件 | 额外显存 |
|------|----------|
| KV Cache（上下文越长越大） | 1-2 GB（2k token 约 0.5GB） |
| 推理框架开销 (CUDA kernel, 中间激活) | 0.5-1 GB |
| **实际总需求** | **6.5-8 GB** |

这意味着 7B 模型在 RTX 3060 6GB 上，**上下文窗口会被压缩到 512 token 以内**，医疗对话几乎不可用。这不是不能跑，而是**跑起来体验会很差**。

---

## 二、优化方案 v1：架构重构

把方案从「本地硬跑 7B」调整为**「本地小模型路由 + 云端强模型推理 + 按需本地医疗微模型」**的混合架构。

### 2.1 新的模型分层策略

```
┌─────────────────────────────────────────────────┐
│                  调度层 (LangGraph)                │
│         意图识别 → 路由分发 → 结果聚合               │
│         模型: DeepSeek V4 Flash (API)             │
└────────┬──────────────┬──────────────┬───────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────┐ ┌──────────────┐ ┌────────────────┐
│ 感知 Agent   │ │ 分析 Agent    │ │ 行动 Agent     │
│ Apple Watch │ │ 医疗问答      │ │ 对话/提醒/     │
│ 数据聚合     │ │              │ │ 建议推送       │
│             │ │              │ │               │
│ 温度: 0.1   │ │ 温度: 0.15   │ │ 温度: 0.3-0.7  │
│ DS V4 Flash │ │ Qwen3-Max    │ │ DS V4 Pro      │
│ (API)       │ │ (API) + RAG  │ │ (API) + Memory │
└─────────────┘ └──────┬───────┘ └────────────────┘
                       │
                       │ 仅在「离线/隐私敏感/高频」场景触发
                       ▼
              ┌─────────────────┐
              │ 本地医疗微模型    │
              │ Qwen3-4B (QLoRA) │
              │ ← MedicalGPT 微调 │
              │ 显存: ~3GB       │
              └─────────────────┘
```

**核心思路**：不要用本地 7B 替代云端 API，而是在关键路径上用云端强模型，本地只部署一个用 MedicalGPT 训练管线微调的**小模型**（Qwen3-4B）做兜底。

### 2.2 为什么选 Qwen3-4B 而不是 7B？

MedicalGPT 已支持 Qwen3 全系列（0.6B / 1.7B / 4B / 8B / 14B / 32B / 235B），包括 Base、Instruct 和 MoE 变体，PT/SFT/DPO/ORPO/GRPO 全流程适配。

| 模型 | 4bit 显存 | 剩余给 KV Cache | 最大上下文 |
|------|-----------|-----------------|------------|
| Qwen3-4B | ~2.5GB | ~3.5GB | 4k-8k token ✅ |
| Qwen3-8B | ~5GB | ~1GB | 512-1k token ❌ |
| Qwen2.5-1.8B | ~1.2GB | ~4.8GB | 8k+ token ✅ |

**推荐 Qwen3-4B**：在医学知识、中文能力、显存余量三者之间取得最优平衡。MedicalGPT 的训练管线完全兼容。

### 2.3 本地部署方案：Ollama + 自定义 Modelfile

不用自己折腾 vLLM 或 llama.cpp。直接用 Ollama：

```bash
# 1. 先用 MedicalGPT 在云端训练 Qwen3-4B 医疗模型
#    得到 LoRA 权重后，合并并量化为 GGUF Q4_K_M

# 2. 创建 Modelfile
# FROM ./medical-qwen3-4b-q4.gguf
# TEMPLATE """{{ .System }}
# {{ .Prompt }}"""
# SYSTEM """你是一个专业的医疗健康助手..."""

# 3. 导入并运行
ollama create medical-agent
ollama run medical-agent
```

Ollama 暴露 OpenAI 兼容 API，可以直接接入 LangGraph。

---

## 三、高温度创意方案（3 个方向）

### 方向 1：「数字孪生」—— 给 Agent 一个你的"身体模型"

不只是分析数据，而是让 Agent 维护一个**持续更新的个人健康数字孪生**：

- **生理基线建模**：用前 30 天数据学习你的「正常」心率区间、睡眠模式、活动水平的统计分布（均值 ± 2σ）。
- **异常检测不是硬阈值**：静息心率 65 对你来说可能是正常的，对别人不是。模型学习的是**「偏离你自己的基线」**，而非偏离人群标准。
- **反事实推理**：「如果昨晚你多睡 1 小时，今天的 HRV 可能会高 5ms，建议今晚 22:30 前入睡。」

实现上，这个不需要 LLM 做，用简单的统计模型（numpy/scipy 就够了），把结果作为 context 喂给 LLM。

### 方向 2：「医疗 Agent 的自我怀疑机制」

LLM 在医疗场景最大的问题是**过于自信的错误**。可以设计一个「自我怀疑回路」：

1. **本地 MedicalGPT 输出初稿诊断**
2. **DeepSeek/Qwen3-Max 扮演「质疑者」角色**，专门找初稿中的逻辑漏洞、遗漏的鉴别诊断
3. **两轮辩论后**，由第三个轻量 prompt 做**裁决和汇总**
4. 最终输出以 **「共识强度」** 标记（高/中/低共识），低共识的内容自动加上更强的免责声明

这本质是 Multi-Agent Debate，LangGraph 的 `StateGraph` 非常适合实现这个。

### 方向 3：「健康叙事引擎」—— 数据 → 故事

大多数健康数据分析输出的都是无聊的表格和列表。可以尝试：

- 将每周健康数据转化为**一段叙事性文字**，像写日记一样：「这周二你的身体经历了高强度的压力峰值，心率一度飙到 145，但周三你给了自己足够的休息，HRV 回升到了 52ms——这说明你的恢复能力在变好。」
- 用这个叙事作为**长期记忆**（存储在向量数据库），3 个月后你可以问：「我这三个月的压力水平变化趋势是什么？」Agent 能调出每周的叙事摘要来回答。
- 甚至可以生成**月报/季报**，像一个真正的私人医生写的健康总结。

---

## 四、具体实施路线图（Phase 1 → Phase 4）

### Phase 1：数据管道（1-2 周）

```
iPhone Shortcuts → Webhook → FastAPI → SQLite/PostgreSQL → 数据聚合层
```

- 用 iOS 快捷指令的「查找健康样本」+「获取 URL 内容」定时推送
- 后端做聚合：原始数据（每 5 分钟心率）→ 日指标（均值/标准差/区间分布/异常次数）
- **这个阶段不涉及任何 LLM**，纯粹是数据工程

### Phase 2：感知 Agent + 分析 Agent（2-3 周）

- LangGraph 构建 `HealthAnalysisGraph`
- **感知节点**读取聚合数据 → 对比个人基线 → 输出结构化异常报告
- **分析节点**将报告 + prompt 模板发给 DeepSeek/Qwen3-Max API
- Prompt 模板设计（这是成败关键）：

```
你是私人健康顾问。基于以下数据给出分析：
- 今日心率：均值{avg}，范围{min}-{max}，异常波动{count}次
- 睡眠：总时长{total}h，深度睡眠{deep}h，REM{rem}h
- HRV：今日{hrv}ms，较30天均值偏离{delta}%
- 运动：活跃能量{energy}kcal，运动时长{exercise}min

请输出：
1. 今日状态总结（1句话）
2. 需要关注的点（如有）
3. 饮食建议（基于今日消耗）
4. 明日运动建议
```

### Phase 3：MedicalGPT 本地部署（3-4 周）⭐ 核心

**训练链路**（云端，租用 A100/L40S）：

```bash
# 1. 选基座：Qwen3-4B-Instruct（或 Qwen3.5-4B）
# 2. 用 MedicalGPT 做 SFT
bash scripts/run_sft.sh  # 使用 shibing624/medical 数据集
# 3. 可选：DPO 对齐
bash scripts/run_dpo.sh
# 4. 合并 LoRA + 量化
python tools/merge_peft_adapter.py --base_model ... --lora_model ...
# 然后用 llama.cpp 量化到 Q4_K_M
```

**推理链路**（本地）：

```
Ollama (Qwen3-4B-Medical-Q4)  ← 暴露 OpenAI API (localhost:11434)
         │
         ▼
  LangGraph 节点: medical_consultant
         │
         ├── 普通健康问答 → 本地模型直出
         ├── 复杂诊断推理 → 本地模型初稿 + 云端模型审查
         └── 离线/隐私模式 → 纯本地处理
```

**关键策略**：本地模型作为**第一响应者**，能回答的直接回答；需要深度推理的，本地模型生成初稿，再由云端强模型做**核查和补充**。这样既节省 API 费用，又保证了安全冗余。

### Phase 4：行动 Agent + 长期记忆（2-3 周）

- **历史对话记忆**：LangGraph 的 `MemorySaver` 或外接向量数据库 (ChromaDB/Milvus)
- **健康趋势记忆**：每周生成一次「健康周报摘要」，embedding 后存向量库
- **主动推送**：检测到异常指标 → 生成提醒消息 → 通过 Telegram Bot / 企业微信 / Bark 推送到手机
- **更多功能接入**：饮食拍照识别（GPT-4V API）、用药提醒、就诊记录 OCR + RAG

---

## 五、关键技术决策建议

| 决策点 | 推荐方案 | 备选方案 |
|--------|----------|----------|
| Agent 框架 | **LangGraph** | CrewAI（更简单但灵活性差） |
| 本地模型基座 | **Qwen3-4B**（4bit） | Qwen3.5-4B / Qwen2.5-4B |
| 模型推理引擎 | **Ollama** | llama.cpp / vLLM |
| 向量数据库 | **ChromaDB**（轻量） | Milvus / Qdrant |
| 后端框架 | **FastAPI** | Flask |
| 数据存储 | **SQLite**（初期）→ PostgreSQL | — |
| 前端 | **Gradio** 或直接 Telegram Bot | Streamlit |
| Apple Health 采集 | **iOS Shortcuts + Webhook** | 手动导出 XML |
| 云端 API（主） | **DeepSeek V4 Flash** | Qwen3-Max |
| 云端 API（审查） | **Qwen3-Max** | DeepSeek V4 Pro |

---

## 六、显存精算（RTX 3060 6GB）

| 场景 | 模型 | 显存占用 | 是否可行 |
|------|------|----------|----------|
| 纯推理 (Q4_K_M, 2k ctx) | Qwen3-4B | ~3.2GB | ✅ 剩余 2.8GB |
| 纯推理 (Q4_K_M, 4k ctx) | Qwen3-4B | ~3.8GB | ✅ 剩余 2.2GB |
| 纯推理 (Q4_K_M, 2k ctx) | Qwen3-8B | ~5.8GB | ⚠️ 接近极限 |
| 推理 + ChromaDB + FastAPI | Qwen3-4B + 服务 | ~4.5GB | ✅ 勉强可行 |
| QLoRA 微调 (4bit) | Qwen3-4B | ~5.5GB | ⚠️ 关闭所有其他程序 |

**结论**：Qwen3-4B 是甜点，Qwen3-8B 是红线。

---

## 七、如果一定要 7B/8B 模型怎么办？

三个备选路径：

1. **CPU 推理**：用 llama.cpp 在 CPU 上跑 Q8 量化版本，32GB 系统内存够用，速度会慢（2-5 token/s），但医疗问答不是实时对话，可接受。
2. **Apple MLX**：如果你有一台 M 系列 Mac（哪怕 MBA），用 MLX 框架推理 8B 模型非常流畅，跟 RTX 3060 不是一个级别。
3. **Qwen3.5-9B-4bit**：Qwen3.5 系列有 MoE 变体，激活参数小但总知识量大，可能更适合边缘部署。

---

## 八、医疗安全与免责机制

### 8.1 分层免责策略

| 场景 | 免责强度 | 触发条件 |
|------|----------|----------|
| 日常健康建议 | 轻量免责 | 所有输出末尾追加「仅供参考」 |
| 症状分析 | 中度免责 | 强制前置「我不是医生，以下内容不能替代专业诊断」 |
| 用药建议 | 最强免责 | 拒绝直接给药，仅提供知识参考 + 强调必须咨询医生 |
| 紧急症状识别 | 自动转介 | 检测到「胸痛」「呼吸困难」等关键词 → 强制输出急救提示 |

### 8.2 幻觉防御

- 在 Prompt 中约束：所有医学断言需要有据可查
- 本地 MedicalGPT 输出 → 云端强模型审查 → 有分歧则降级为「不确定」
- 所有输出标注「共识强度」：高/中/低

---

## 九、项目目录结构建议

```
Medical-Health-Agent/
├── data_pipeline/           # Phase 1: 数据采集与聚合
│   ├── webhook_server.py    # FastAPI 接收 Apple Health 数据
│   ├── aggregator.py        # 原始数据 → 日/周指标
│   └── models.py            # 数据模型定义
├── agents/                  # Phase 2 & 4: Agent 定义
│   ├── graph.py             # LangGraph StateGraph 主图
│   ├── perception.py        # 感知 Agent 节点
│   ├── analysis.py          # 分析 Agent 节点
│   ├── action.py            # 行动 Agent 节点
│   └── state.py             # Agent 状态定义
├── medical_llm/             # Phase 3: 本地医疗模型
│   ├── training/            # MedicalGPT 训练脚本 & 配置
│   ├── Modelfile            # Ollama 模型定义
│   └── deploy.sh            # 一键部署脚本
├── prompts/                 # Prompt 模板管理
│   ├── health_analysis.yaml
│   ├── medical_qa.yaml
│   └── safety_check.yaml
├── memory/                  # 向量存储 & 长期记忆
│   ├── vector_store.py
│   └── weekly_summary.py
├── frontend/                # UI
│   └── gradio_app.py
├── config.py                # 全局配置
├── requirements.txt
└── README.md
```
