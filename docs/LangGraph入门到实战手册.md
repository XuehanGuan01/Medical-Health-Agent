# LangGraph 入门到实战手册

> 从零开始，构建你的第一个 LangGraph Agent
> 以 Medical-Health-Agent 项目为主线案例

---

## 目录

1. [什么是 LangGraph](#一什么是-langgraph)
2. [核心概念](#二核心概念)
3. [第一个 Graph：线形流程](#三第一个-graph线形流程)
4. [条件路由：让 Agent 自己做决策](#四条件路由让-agent-自己做决策)
5. [复杂状态：TypedDict 定义一切](#五复杂状态typeddict-定义一切)
6. [实战模式：Self-RAG](#六实战模式self-rag)
7. [持久化记忆](#七持久化记忆)
8. [流式输出](#八流式输出)
9. [完整案例：Medical-Health-Agent](#九完整案例medical-health-agent)
10. [调试与最佳实践](#十调试与最佳实践)

---

## 一、什么是 LangGraph

### 1.1 一句话定义

**LangGraph 是一个用「图」来编排 LLM 工作流的框架。** 你把任务拆成节点（Node），用边（Edge）串联，LangGraph 负责按图调度执行。

### 1.2 为什么不用 LangChain 的 Chain？

```
Chain 的问题：
  A → B → C 只能走直线
  遇到"如果意图是A走这条路，否则走那条路"就抓瞎
  流程一变就要重写整个 Chain

LangGraph 的解法：
  用「图」而不是「链」
  节点可以做任何事（调LLM、查数据库、写文件...）
  条件边 = 让图自己决定下一步走哪
  状态在节点间自动传递
```

### 1.3 一张图理解全部

```
┌──────────┐      ┌──────────┐      ┌──────────┐
│   Node A  │─────→│   Node B  │─────→│   Node C  │
│ (输入处理) │      │ (LLM调用) │      │ (输出格式化)│
└──────────┘      └──────────┘      └──────────┘
                                             │
                                        ┌────┴────┐
                                        │ 条件判断  │
                                        └────┬────┘
                                      ┌──────┴──────┐
                                      │             │
                                      ▼             ▼
                                 ┌────────┐   ┌────────┐
                                 │ Node D │   │ Node E │
                                 │ 通过   │   │ 重试   │
                                 └────────┘   └────────┘
```

### 1.4 三个你必须先理解的概念

| 概念 | 类比 | 在代码中是什么 |
|------|------|-------------|
| **State** (状态) | 快递包裹——节点之间传递的数据 | 一个 dict 或 TypedDict |
| **Node** (节点) | 快递站点——对包裹做点什么 | 一个 Python 函数，接收State，返回更新 |
| **Edge** (边) | 传送带——包裹从哪个站送到哪个站 | `add_edge("A", "B")` |

---

## 二、核心概念

### 2.1 StateGraph：图的蓝图

```python
from langgraph.graph import StateGraph

# StateGraph 是"图的设计图"
# 你需要告诉它：
#   1. State 长什么样（数据格式）
#   2. 有哪些节点（处理步骤）
#   3. 节点之间怎么连（执行顺序）

graph = StateGraph(MyState)  # MyState 是你定义的状态类
```

**通俗理解**：StateGraph 就像乐高的底板，你在上面拼节点和边。

### 2.2 State：图的"血液"

State 在节点之间流动，每个节点读取它、修改它、传递它。

```python
from typing import TypedDict

class MyState(TypedDict):
    query: str           # 用户输入
    result: str          # 处理结果
    step_count: int      # 执行步数
```

**关键规则**：节点函数**不直接修改** State，而是**返回一个包含变更的 dict**。LangGraph 自动合并这些变更。

```python
# ✅ 正确：返回要更新的字段
def my_node(state: MyState) -> dict:
    return {"result": "处理完成", "step_count": state["step_count"] + 1}

# ❌ 错误：直接修改（不会生效）
def my_node(state: MyState) -> dict:
    state["result"] = "处理完成"  # 这样改没用！
```

### 2.3 Node：图的"器官"

节点就是一个普通的 Python 函数，签名为：

```python
def node_function(state: YourState) -> dict:
    """
    输入: 当前完整的 State
    输出: 一个 dict，只包含你想要更新的字段
          未出现在 dict 中的字段保持不变
    """
    # 做任何事：调LLM、查数据库、写文件、调API...
    return {"field_to_update": new_value}
```

### 2.4 Edge：图的"神经"

LangGraph 有三种边：

```python
# 1. 普通边：固定路线 A → B
graph.add_edge("node_a", "node_b")

# 2. 条件边：根据 state 决定走哪条路
graph.add_conditional_edges(
    "source_node",           # 从哪个节点出发
    decision_function,       # 决策函数：返回下一个节点名
    {
        "path_a": "node_x",  # 如果决策返回 "path_a"，去 node_x
        "path_b": "node_y",  # 如果决策返回 "path_b"，去 node_y
    }
)

# 3. 入口：从哪个节点开始
graph.set_entry_point("first_node")
```

### 2.5 Compile：把蓝图变成可执行的机器

```python
# StateGraph 只是"设计图"，compile() 之后才能用
app = graph.compile()

# 调用
result = app.invoke({"query": "你好"})
# → {"query": "你好", "result": "...", "step_count": 3}
```

---

## 三、第一个 Graph：线形流程

### 3.1 场景

构建一个最简单的三步骤流程：接收输入 → 处理 → 输出结果。

### 3.2 完整代码

```python
from typing import TypedDict
from langgraph.graph import StateGraph, END

# ── Step 1: 定义 State ──────────────────────────────
class SimpleState(TypedDict):
    user_input: str
    processed: str
    final_output: str

# ── Step 2: 定义三个节点 ────────────────────────────
def input_node(state: SimpleState) -> dict:
    """第一站：接收并记录输入"""
    print(f"[输入] 收到: {state['user_input']}")
    return {}  # 不修改任何字段

def process_node(state: SimpleState) -> dict:
    """第二站：处理输入（真实场景这里可能调LLM）"""
    result = state["user_input"].upper()  # 简单处理：转大写
    print(f"[处理] '{state['user_input']}' → '{result}'")
    return {"processed": result}

def output_node(state: SimpleState) -> dict:
    """第三站：格式化最终输出"""
    final = f"处理结果: {state['processed']} (共{len(state['processed'])}字符)"
    print(f"[输出] {final}")
    return {"final_output": final}

# ── Step 3: 构建图 ──────────────────────────────────
graph = StateGraph(SimpleState)

graph.add_node("input", input_node)      # 注册节点
graph.add_node("process", process_node)
graph.add_node("output", output_node)

graph.set_entry_point("input")            # 起点
graph.add_edge("input", "process")        # input → process
graph.add_edge("process", "output")       # process → output
graph.add_edge("output", END)             # output → 结束

app = graph.compile()

# ── Step 4: 运行 ────────────────────────────────────
result = app.invoke({"user_input": "hello world"})
print(f"\n最终State: {result}")
```

**输出**：
```
[输入] 收到: hello world
[处理] 'hello world' → 'HELLO WORLD'
[输出] 处理结果: HELLO WORLD (共11字符)

最终State: {'user_input': 'hello world', 'processed': 'HELLO WORLD', 'final_output': '处理结果: HELLO WORLD (共11字符)'}
```

### 3.3 可视化

如果你的 graph 不太复杂，可以直观画出：

```
input ──→ process ──→ output ──→ END
```

这就是最简单的 `StateGraph`——三个节点排成一排，数据从左流到右。

---

## 四、条件路由：让 Agent 自己做决策

### 4.1 场景

用户发来消息，先判断意图：
- 如果是"查健康数据"→ 走数据查询节点
- 如果是"医疗问答"→ 走 RAG 问答节点
- 如果是"普通聊天"→ 走闲聊节点

### 4.2 完整代码

```python
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END

# ── State ────────────────────────────────────────────
class RouterState(TypedDict):
    query: str
    intent: str       # 意图分类结果
    response: str     # 最终回复

# ── 节点：意图识别 ────────────────────────────────────
def classify_intent(state: RouterState) -> dict:
    """
    真实场景这里会调 LLM 做分类。
    这里用关键词模拟。
    """
    query = state["query"]

    # 模拟 LLM 的分类逻辑
    health_keywords = ["心率", "睡眠", "步数", "血压", "运动", "健康"]
    medical_keywords = ["发烧", "头疼", "咳嗽", "吃药", "症状", "病", "疼"]

    if any(kw in query for kw in health_keywords):
        intent = "health_data"
    elif any(kw in query for kw in medical_keywords):
        intent = "medical_qa"
    else:
        intent = "general_chat"

    print(f"[Router] '{query}' → intent={intent}")
    return {"intent": intent}

# ── 路由决策函数 ──────────────────────────────────────
def route_by_intent(state: RouterState) -> Literal["health_data", "medical_qa", "general_chat"]:
    """
    条件边的决策函数：
    - 输入: 当前 State
    - 输出: 必须是下一个节点的**名字**（字符串）
    - 返回的字符串必须在 add_conditional_edges 的 mapping 中
    """
    return state["intent"]

# ── 三个处理节点 ──────────────────────────────────────
def health_data_node(state: RouterState) -> dict:
    """模拟健康数据查询"""
    return {"response": "📊 今日健康数据：心率72bpm，步数8500，睡眠7.2h"}

def medical_qa_node(state: RouterState) -> dict:
    """模拟医疗问答（真实场景会走 RAG 检索 + LLM）"""
    return {"response": "🏥 关于您的问题，建议如下：...(此处为RAG增强回答)"}

def general_chat_node(state: RouterState) -> dict:
    """模拟普通对话"""
    return {"response": f"👋 你好！你说了：'{state['query']}'。有什么健康方面的问题我可以帮你？"}

# ── 构建图 ──────────────────────────────────────────
graph = StateGraph(RouterState)

graph.add_node("router", classify_intent)
graph.add_node("health_handler", health_data_node)
graph.add_node("medical_handler", medical_qa_node)
graph.add_node("chat_handler", general_chat_node)

graph.set_entry_point("router")

# ★ 关键：条件边
graph.add_conditional_edges(
    "router",                # 从 router 节点出发
    route_by_intent,         # 用这个函数决定下一步
    {
        "health_data": "health_handler",   # 如果返回 "health_data"
        "medical_qa": "medical_handler",   # 如果返回 "medical_qa"
        "general_chat": "chat_handler",    # 如果返回 "general_chat"
    }
)

# 三个处理节点都通向结束
graph.add_edge("health_handler", END)
graph.add_edge("medical_handler", END)
graph.add_edge("chat_handler", END)

app = graph.compile()

# ── 测试 ────────────────────────────────────────────
for query in ["我今天心率有点高", "小孩发烧39度怎么办", "今天天气真好"]:
    result = app.invoke({"query": query})
    print(f"  回复: {result['response']}\n")
```

**输出**：
```
[Router] '我今天心率有点高' → intent=health_data
  回复: 📊 今日健康数据：心率72bpm，步数8500，睡眠7.2h

[Router] '小孩发烧39度怎么办' → intent=medical_qa
  回复: 🏥 关于您的问题，建议如下：...(此处为RAG增强回答)

[Router] '今天天气真好' → intent=general_chat
  回复: 👋 你好！你说了：'今天天气真好'。有什么健康方面的问题我可以帮你？
```

### 4.3 图的形状

```
                    ┌─────────┐
                    │ Router  │
                    │ 意图分类 │
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         health_data  medical_qa  general_chat
              │          │          │
              ▼          ▼          ▼
            health    medical     chat
           handler    handler    handler
              │          │          │
              └──────────┴──────────┘
                         │
                        END
```

---

## 五、复杂状态：TypedDict 定义一切

### 5.1 用 TypedDict 而不是普通 dict

```python
# ❌ 不推荐：普通 dict，没有类型提示，IDE 不会补全
class BadState(TypedDict):
    pass  # 空的！

# ✅ 推荐：明确定义每个字段
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # 基础字段
    query: str
    response: str

    # 可选字段
    intent: Optional[str]          # 意图分类结果

    # 使用 Annotated + add_messages 自动追加消息
    # 而不是覆盖！这对对话历史非常重要
    messages: Annotated[list, add_messages]

    # 复杂嵌套
    retrieved_docs: Optional[list[dict]]
```

### 5.2 `add_messages` 的魔法

```python
from langgraph.graph.message import add_messages
from typing import Annotated

class ChatState(TypedDict):
    # 用 add_messages 标注后：
    # 节点返回 {"messages": new_msg} → new_msg 被追加到列表
    # 节点返回 {"messages": [msg1, msg2]} → 两条都被追加
    # 而不是整个替换掉原来的 messages！
    messages: Annotated[list, add_messages]

# 第一个节点
def node_a(state: ChatState) -> dict:
    return {"messages": [{"role": "assistant", "content": "你好"}]}
# 此时 messages = [{"role": "assistant", "content": "你好"}]

# 第二个节点
def node_b(state: ChatState) -> dict:
    return {"messages": [{"role": "assistant", "content": "有什么可以帮您？"}]}
# 此时 messages = [
#   {"role": "assistant", "content": "你好"},
#   {"role": "assistant", "content": "有什么可以帮您？"}
# ]
# ↑ 自动追加，不是覆盖！
```

### 5.3 自定义 Reducer

如果你需要其他"合并逻辑"（而不是追加），可以自定义：

```python
from operator import add
from typing import Annotated

class MyState(TypedDict):
    # 字符串：追加拼接
    log: Annotated[str, lambda current, new: current + "\n" + new]

    # 列表：合并
    all_docs: Annotated[list, add]

    # 计数器：累加
    token_count: Annotated[int, lambda current, new: current + new]
```

---

## 六、实战模式：Self-RAG

### 6.1 什么是 Self-RAG

Self-RAG = **Self**-Reflective **R**etrieval-**A**ugmented **G**eneration

翻译：**会自我检查的检索增强生成**

```
传统RAG:
  检索 → 生成 → 输出（一条直线，生成什么就输出什么）

Self-RAG:
  检索 → 生成 → 自检 → 通过？→ 输出
                    ↓ 不通过
                   修正 → 再输出
```

### 6.2 Self-RAG 的 Graph 设计

```
用户问题
  │
  ▼
┌──────────┐
│ Retrieve │  从向量库检索相关医学知识
│  检索    │
└────┬─────┘
     │
     ▼
┌──────────┐
│ Generate │  LLM 基于检索知识生成回答初稿
│  生成    │
└────┬─────┘
     │
     ▼
┌──────────┐
│ Reflect  │  LLM 自检：
│  自检    │  ① 回答有检索依据吗？
└────┬─────┘  ② 有编造/幻觉吗？
     │       ③ 越界诊断了吗？
     │
     ▼
┌──────────────┐
│ 条件判断      │
│ check_result │
└──┬───┬───┬───┘
   │   │   │
 pass retry reject
   │   │   │
   ▼   ▼   ▼
┌────┐┌──────┐┌──────────┐
│输出││Revise││  Reject  │
│   ││ 修正 ││  拒答模板 │
└───┘└──┬───┘└──────────┘
        │
        ▼
      END
```

### 6.3 完整代码

```python
from typing import TypedDict, Optional, Annotated, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# ── State ────────────────────────────────────────────
class SelfRAGState(TypedDict):
    query: str
    messages: Annotated[list, add_messages]

    # RAG 检索结果
    retrieved_docs: Optional[list[dict]]
    retrieval_context: Optional[str]

    # Self-RAG 中间产物
    draft_response: Optional[str]
    reflection: Optional[dict]    # {"pass": bool, "issues": str, "action": "pass"|"retry"|"reject"}

    # 最终输出
    response: str

# ── Node 1: 检索 ─────────────────────────────────────
def retrieve_node(state: SelfRAGState) -> dict:
    """
    从向量库检索相关知识。
    真实场景调用 MedicalRetriever.search()
    """
    # 模拟检索结果（实际项目替换为真实检索）
    mock_docs = [
        {
            "question": "小孩发烧39度怎么办？",
            "content": "问：小孩发烧39度怎么办？\n答：小孩发烧39度属于高热...",
            "score": 0.92,
        },
        {
            "question": "儿童发热如何处理？",
            "content": "问：儿童发热如何处理？\n答：儿童发热需要...",
            "score": 0.85,
        },
    ]

    context = "\n\n".join(
        f"[参考{i+1}] {doc['content']}" for i, doc in enumerate(mock_docs)
    )

    return {
        "retrieved_docs": mock_docs,
        "retrieval_context": context,
    }

# ── Node 2: 生成 ─────────────────────────────────────
GENERATE_PROMPT = """你是专业的医疗健康助手。基于以下参考知识回答用户问题。

## 参考知识
{context}

## 回答准则
1. 回答必须基于参考知识，不要编造
2. 如果参考知识不足，诚实说明
3. 回答仅供参考，不能替代专业医生诊断
4. 不要开具处方或推荐具体药物剂量

## 用户问题
{query}

请给出回答："""

def generate_node(state: SelfRAGState) -> dict:
    """
    基于检索知识 + 用户问题，由 LLM 生成回答初稿。
    """
    prompt = GENERATE_PROMPT.format(
        context=state["retrieval_context"],
        query=state["query"],
    )

    # 实际项目：response = llm.invoke(prompt)
    draft = f"[LLM基于检索知识生成的回答初稿] 针对'{state['query']}'..."

    return {"draft_response": draft}

# ── Node 3: 自检 ─────────────────────────────────────
REFLECT_PROMPT = """你是医疗回答的质检员。审查以下回答：

## 检索到的参考知识
{context}

## AI生成的回答
{draft}

请判断并仅输出JSON:
{{
    "pass": true/false,
    "issues": "如果pass为false，说明具体问题",
    "action": "pass" / "retry" / "reject"
}}

判断标准：
- action="pass": 回答基于参考知识，没有编造，没有越界诊断
- action="retry": 回答有小问题（缺少就医建议、表述不够准确），可以修正
- action="reject": 回答涉及明确诊断或处方，必须拒答"""

def reflect_node(state: SelfRAGState) -> dict:
    """
    LLM 自检：审查生成的回答质量。
    """
    prompt = REFLECT_PROMPT.format(
        context=state["retrieval_context"],
        draft=state["draft_response"],
    )

    # 实际项目：response = reflect_llm.invoke(prompt); result = json.loads(response)
    # 这里模拟
    import json
    mock_reflection = {"pass": True, "issues": "", "action": "pass"}
    print(f"[Reflect] 自检结果: {mock_reflection['action']}")

    return {"reflection": mock_reflection}

# ── 条件路由 ──────────────────────────────────────────
def check_reflection(state: SelfRAGState) -> Literal["pass", "retry", "reject"]:
    """根据自检结果决定下一步"""
    action = state["reflection"]["action"]
    return action

# ── Node 4a: 通过 → 直接使用初稿 ──────────────────────
def pass_node(state: SelfRAGState) -> dict:
    return {
        "response": state["draft_response"],
        "messages": [{"role": "assistant", "content": state["draft_response"]}],
    }

# ── Node 4b: 修正 ────────────────────────────────────
REVISE_PROMPT = """根据质检意见修正以下回答：

## 原回答
{draft}

## 质检意见
{issues}

## 参考知识
{context}

请给出修正后的回答："""

def revise_node(state: SelfRAGState) -> dict:
    prompt = REVISE_PROMPT.format(
        draft=state["draft_response"],
        issues=state["reflection"]["issues"],
        context=state["retrieval_context"],
    )
    # 实际项目：response = llm.invoke(prompt)
    revised = f"[修正后的回答] {state['draft_response']}（已根据意见修正）"
    return {
        "response": revised,
        "messages": [{"role": "assistant", "content": revised}],
    }

# ── Node 4c: 拒答 ────────────────────────────────────
REJECT_TEMPLATE = """我无法回答这个问题。{issues}

建议您前往正规医疗机构就诊，由专业医生进行评估。

如果您有其他健康方面的问题（如饮食建议、运动指导、医学科普），我很乐意帮助。"""

def reject_node(state: SelfRAGState) -> dict:
    reject_msg = REJECT_TEMPLATE.format(issues=state["reflection"]["issues"])
    return {
        "response": reject_msg,
        "messages": [{"role": "assistant", "content": reject_msg}],
    }

# ── 构建 Graph ───────────────────────────────────────
def build_self_rag_graph():
    graph = StateGraph(SelfRAGState)

    # 注册节点
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("pass_output", pass_node)
    graph.add_node("revise", revise_node)
    graph.add_node("reject", reject_node)

    # 设入口
    graph.set_entry_point("retrieve")

    # 普通边：检索 → 生成 → 自检
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "reflect")

    # ★ 条件边：根据自检结果分叉
    graph.add_conditional_edges(
        "reflect",
        check_reflection,
        {
            "pass": "pass_output",
            "retry": "revise",
            "reject": "reject",
        }
    )

    # pass / revise / reject 都到 END
    graph.add_edge("pass_output", END)
    graph.add_edge("revise", END)
    graph.add_edge("reject", END)

    return graph.compile()

# ── 运行 ─────────────────────────────────────────────
if __name__ == "__main__":
    app = build_self_rag_graph()

    result = app.invoke({"query": "小孩发烧39度怎么办？"})
    print(f"\n最终回答:\n{result['response']}")
```

---

## 七、持久化记忆

### 7.1 LangGraph 的 Checkpointer

LangGraph 内置了 `MemorySaver`（内存）和 `SqliteSaver`（持久化）。配置后每个 `thread_id` 的对话历史自动保存。

```python
from langgraph.checkpoint.memory import MemorySaver
# from langgraph.checkpoint.sqlite import SqliteSaver  # 持久化版

# 创建 checkpointer
memory = MemorySaver()

# 编译时注入
app = graph.compile(checkpointer=memory)

# 调用时传入 thread_id
config = {"configurable": {"thread_id": "user_session_123"}}

# 第一轮对话
result1 = app.invoke(
    {"query": "我最近睡眠不好"},
    config=config
)

# 第二轮对话 —— LangGraph 自动加载历史
result2 = app.invoke(
    {"query": "有什么改善方法吗？"},
    config=config
)
# ↑ agent 知道"改善"指的是"改善睡眠"，因为第一轮的上下文被保留了
```

### 7.2 手动持久化（更灵活）

对于本项目，建议同时用 SQLite 存完整对话历史 + ChromaDB 存语义记忆：

```python
import sqlite3
import json
from datetime import datetime

def save_message(session_id: str, role: str, content: str):
    """保存单条消息到 SQLite"""
    conn = sqlite3.connect("data/chat_history.db")
    conn.execute(
        """INSERT INTO chat_history (session_id, role, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (session_id, role, content, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def load_history(session_id: str, limit: int = 20) -> list[dict]:
    """加载最近的对话历史"""
    conn = sqlite3.connect("data/chat_history.db")
    rows = conn.execute(
        """SELECT role, content FROM chat_history
           WHERE session_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
```

---

## 八、流式输出

### 8.1 基本用法

```python
# 非流式：等全部生成完才返回
result = app.invoke({"query": "你好"})

# 流式：每完成一个节点就推送
for event in app.stream({"query": "你好"}):
    node_name = list(event.keys())[0]
    node_output = event[node_name]
    print(f"[{node_name}] {node_output}")
```

### 8.2 实际效果

```
[retrieve] {'retrieved_docs': [...], 'retrieval_context': '...'}
[generate] {'draft_response': '小孩发烧39度属于高热...'}
[reflect] {'reflection': {'pass': True, 'action': 'pass'}}
[pass_output] {'response': '小孩发烧39度属于高热...'}
```

### 8.3 配合 FastAPI 实现 SSE

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()

@app.post("/api/v1/chat/stream")
async def chat_stream(query: str):
    async def event_generator():
        for event in agent_graph.stream({"query": query}):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
```

---

## 九、完整案例：Medical-Health-Agent

### 9.1 系统架构（回顾）

```
用户问题
  │
  ▼
┌─────────────────────────────────────────────┐
│               LangGraph Graph                │
│                                             │
│  Router → Perception/Analysis → Action      │
│           │                  │              │
│           ▼                  ▼              │
│     RAG检索(Phase2)   健康数据(Phase1)       │
└─────────────────────────────────────────────┘
```

### 9.2 `agents/state.py` — 状态定义

```python
"""Agent State — LangGraph 共享状态"""
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages

class HealthMetrics(TypedDict):
    """健康日聚合数据"""
    date: str
    heart_rate: dict        # {"avg": 72, "min": 60, "max": 95, "baseline_mean": 68, "deviation_sigma": 0.8}
    hrv: dict               # {"avg": 48, "baseline_mean": 45, "deviation_sigma": 0.5}
    steps: dict             # {"total": 8500, "baseline_mean": 7200}
    sleep: dict             # {"total_hours": 7.2, "deep_hours": 1.5, "rem_hours": 2.1}
    active_energy: dict     # {"total": 1800, "baseline_mean": 1600}

class AgentState(TypedDict):
    # ── 用户输入 ──
    query: str
    messages: Annotated[list, add_messages]

    # ── 路由 ──
    intent: str             # "health_data" | "medical_qa" | "general_chat" | "emergency"

    # ── 检索 & 健康数据 ──
    retrieved_docs: Optional[list[dict]]
    health_metrics: Optional[dict]     # HealthMetrics 或其简化版

    # ── Self-RAG 中间态 ──
    draft_response: Optional[str]
    reflection: Optional[dict]

    # ── 输出 ──
    response: str
    safety_level: str       # "normal" | "caution" | "emergency"
```

### 9.3 `agents/router.py` — 意图路由

```python
"""意图路由节点"""
from config.llm import get_llm

ROUTER_PROMPT = """你是医疗Agent的意图路由器。分析用户输入，判断意图：

1. health_data — 用户询问自己的健康数据（心率、睡眠、步数、运动等）
2. medical_qa — 用户提出医疗/健康问题（症状、疾病、药物、养生等）
3. general_chat — 日常对话、问候
4. emergency — 紧急症状（胸痛、呼吸困难、大出血、意识丧失等）

仅回复意图标签（health_data/medical_qa/general_chat/emergency），不要其他内容。"""

def router_node(state: "AgentState") -> dict:
    """意图路由节点"""
    llm = get_llm("router")  # temp=0.0, max_tokens=100

    response = llm.invoke(ROUTER_PROMPT + f"\n\n用户输入: {state['query']}")
    intent = response.content.strip().lower()

    # 规范化为标准值
    valid_intents = {"health_data", "medical_qa", "general_chat", "emergency"}
    if intent not in valid_intents:
        intent = "general_chat"

    return {"intent": intent}


def route_by_intent(state: "AgentState") -> str:
    """条件边决策：根据意图路由到不同处理节点"""
    mapping = {
        "health_data": "perception",
        "medical_qa": "retrieve",
        "general_chat": "action",
        "emergency": "emergency_handler",
    }
    return mapping.get(state["intent"], "action")
```

### 9.4 `agents/boundary.py` — 安全边界

```python
"""硬边界拒答"""
import re

EMERGENCY_KEYWORDS = [
    "胸痛", "胸闷", "呼吸困难", "大出血", "意识丧失",
    "严重外伤", "中风", "心梗", "窒息", "休克", "濒死",
    "剧烈腹痛", "突然失明", "半边身子动不了",
]

DIAGNOSIS_PATTERNS = [
    r"我是不是得了(.+病|.+症|.+癌)",
    r"帮我确诊",
    r"我这是什么病",
    r"给我开.*药",
]

def check_emergency(query: str) -> bool:
    """检查是否包含紧急关键词"""
    return any(kw in query for kw in EMERGENCY_KEYWORDS)

def check_diagnosis_request(query: str) -> bool:
    """检查是否在请求诊断/处方"""
    return any(re.search(p, query) for p in DIAGNOSIS_PATTERNS)

REJECT_TEMPLATES = {
    "emergency": (
        "⚠️ 您描述的症状可能需要紧急医疗处理。\n\n"
        "请立即拨打120或前往最近的急诊科。\n\n"
        "在等待救援期间：\n"
        "- 保持冷静，尽量平躺\n"
        "- 如有已知病史，告知急救人员\n"
        "- 不要自行用药"
    ),
    "diagnosis": (
        "我无法进行医学诊断。{issues}\n\n"
        "建议您前往正规医疗机构就诊，由专业医生进行评估。\n\n"
        "我可以为您提供以下帮助：\n"
        "- 相关医学知识的科普\n"
        "- 日常健康生活方式的建议\n"
        "- 帮助理解医生的诊断和检查报告"
    ),
    "prescription": (
        "我无法开具处方或推荐具体药物剂量。\n\n"
        "用药方案需要医生根据您的具体情况（年龄、体重、病史、过敏史等）综合制定。\n"
        "请咨询执业医师或药师。"
    ),
}
```

### 9.5 `agents/analysis.py` — Self-RAG 核心

```python
"""分析Agent — Self-RAG流程：检索→生成→自检→修正"""
import json
from config.llm import get_llm
from rag.retriever import MedicalRetriever

retriever = MedicalRetriever()  # 单例

# ── Prompt 模板 ─────────────────────────────────────
GENERATE_PROMPT = """你是专业的医疗健康助手。请基于以下参考知识回答用户问题。

## 参考知识
{context}

## 回答准则
1. 回答应基于参考知识，不要编造
2. 如果参考知识不足以回答问题，诚实说明
3. 回答仅供参考，不能替代专业医生诊断
4. 不要开具处方或推荐具体药物剂量
5. 涉及紧急症状时，优先建议立即就医
6. 保持专业、温和、共情的语气

## 用户问题
{query}

请给出回答："""

REFLECT_PROMPT = """你是医疗回答的质检员。请审查以下回答：

## 参考知识
{context}

## AI生成的回答
{draft}

请判断并严格输出JSON（不要其他内容）：
{{
    "pass": true/false,
    "issues": "如果pass为false，指出具体问题。如果pass为true，为空字符串",
    "action": "pass" / "retry" / "reject"
}}

判断标准：
- pass:  回答基于参考知识，无编造，无越界诊断，包含了就医建议
- retry: 回答有小问题（缺少就医建议、表述模糊、不够完整），可以修正
- reject: 回答涉及明确诊断结论、推荐处方，或用户问题本身在请求诊断"""

REVISE_PROMPT = """根据质检意见修正以下回答：

## 原回答
{draft}

## 质检意见
{issues}

## 参考知识
{context}

## 用户问题
{query}

请给出修正后的回答："""

# ── 节点函数 ─────────────────────────────────────────
def retrieve_node(state: "AgentState") -> dict:
    """RAG检索节点：从ChromaDB检索相关医学知识"""
    docs = retriever.search(state["query"], k=5)
    context = retriever.format_context(docs)
    return {
        "retrieved_docs": docs,
        "retrieval_context": context,
    }

def generate_node(state: "AgentState") -> dict:
    """生成节点：LLM基于检索知识生成回答初稿"""
    llm = get_llm("analysis")  # temp=0.15

    prompt = GENERATE_PROMPT.format(
        context=state.get("retrieval_context", "无参考知识"),
        query=state["query"],
    )
    response = llm.invoke(prompt)
    return {"draft_response": response.content.strip()}

def reflect_node(state: "AgentState") -> dict:
    """自检节点：LLM审查回答质量"""
    llm = get_llm("reflect")  # temp=0.0

    prompt = REFLECT_PROMPT.format(
        context=state.get("retrieval_context", "无"),
        draft=state["draft_response"],
    )
    response = llm.invoke(prompt)

    # 解析 JSON
    try:
        result = json.loads(response.content.strip())
    except json.JSONDecodeError:
        # Fallback: 解析失败则通过
        result = {"pass": True, "issues": "", "action": "pass"}

    return {"reflection": result}

def check_reflection(state: "AgentState") -> str:
    """条件边决策"""
    return state["reflection"].get("action", "pass")

def pass_node(state: "AgentState") -> dict:
    """通过：直接使用初稿"""
    reply = state["draft_response"]
    # 始终追加免责声明
    reply += "\n\n---\n*以上回答仅供参考，不能替代专业医生诊断。如有不适请及时就医。*"
    return {
        "response": reply,
        "safety_level": "normal",
    }

def revise_node(state: "AgentState") -> dict:
    """修正节点：根据自检意见重新生成"""
    llm = get_llm("analysis")  # temp=0.15

    prompt = REVISE_PROMPT.format(
        draft=state["draft_response"],
        issues=state["reflection"]["issues"],
        context=state.get("retrieval_context", "无"),
        query=state["query"],
    )
    response = llm.invoke(prompt)
    reply = response.content.strip()
    reply += "\n\n---\n*以上回答仅供参考，不能替代专业医生诊断。如有不适请及时就医。*"
    return {
        "response": reply,
        "safety_level": "caution",
    }

def reject_node(state: "AgentState") -> dict:
    """拒答节点"""
    issues = state["reflection"].get("issues", "")
    from agents.boundary import REJECT_TEMPLATES

    # 根据 issues 选择模板
    if "处方" in issues or "药物" in issues or "剂量" in issues:
        reply = REJECT_TEMPLATES["prescription"]
    else:
        reply = REJECT_TEMPLATES["diagnosis"].format(issues=issues)

    return {
        "response": reply,
        "safety_level": "emergency",
    }
```

### 9.6 `agents/graph.py` — 组装完整 Graph

```python
"""LangGraph 主图：组装所有 Agent 节点"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .router import router_node, route_by_intent
from .analysis import (
    retrieve_node, generate_node, reflect_node,
    check_reflection, pass_node, revise_node, reject_node,
)
from .perception import perception_node
from .action import action_node
from .boundary import emergency_node


def build_medical_agent_graph():
    """构建 Medical-Health-Agent 的完整 LangGraph"""
    graph = StateGraph(AgentState)

    # ── 注册所有节点 ──
    graph.add_node("router", router_node)
    graph.add_node("perception", perception_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("pass_output", pass_node)
    graph.add_node("revise", revise_node)
    graph.add_node("reject", reject_node)
    graph.add_node("action", action_node)
    graph.add_node("emergency_handler", emergency_node)

    # ── 入口 ──
    graph.set_entry_point("router")

    # ── Router 的条件边 ──
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "health_data": "perception",
            "medical_qa": "retrieve",
            "general_chat": "action",
            "emergency": "emergency_handler",
        }
    )

    # ── medical_qa 路径: Self-RAG 闭环 ──
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "reflect")
    graph.add_conditional_edges(
        "reflect",
        check_reflection,
        {
            "pass": "pass_output",
            "retry": "revise",
            "reject": "reject",
        }
    )
    # Self-RAG 三个出口都到 action（最终回复格式化）
    graph.add_edge("pass_output", "action")
    graph.add_edge("revise", "action")
    graph.add_edge("reject", "action")

    # ── health_data 路径: 感知 → 行动 ──
    graph.add_edge("perception", "action")

    # ── 终结点 ──
    graph.add_edge("action", END)
    graph.add_edge("emergency_handler", END)

    # ── 编译 ──
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
```

### 9.7 `agents/graph.py` — FastAPI 集成

```python
"""FastAPI 端点：暴露 Agent 为 HTTP API"""
from fastapi import FastAPI
from pydantic import BaseModel

from .graph import build_medical_agent_graph

app = FastAPI(title="Medical-Health-Agent API")
agent_graph = build_medical_agent_graph()


class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    intent: str
    safety_level: str

@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """对话端点"""
    config = {"configurable": {"thread_id": request.session_id}}

    result = agent_graph.invoke(
        {"query": request.query},
        config=config,
    )

    return ChatResponse(
        response=result.get("response", ""),
        intent=result.get("intent", "general_chat"),
        safety_level=result.get("safety_level", "normal"),
    )


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话端点"""
    from fastapi.responses import StreamingResponse
    import json

    config = {"configurable": {"thread_id": request.session_id}}

    async def generate():
        for event in agent_graph.stream(
            {"query": request.query},
            config=config,
        ):
            node_name = list(event.keys())[0]
            yield f"data: {json.dumps({node_name: event[node_name]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

---

## 十、调试与最佳实践

### 10.1 调试三件套

```python
# 1. 打印每次 invoke 的完整 State
result = app.invoke({"query": "测试"})
import json
print(json.dumps(result, indent=2, ensure_ascii=False))

# 2. 使用 stream 查看每个节点的输出
for event in app.stream({"query": "测试"}):
    print(event)

# 3. 用 LangGraph 内置的 draw_mermaid 生成流程图
from langgraph.graph import draw_mermaid
print(app.get_graph().draw_mermaid())
# 复制输出到 https://mermaid.live 即可看到可视化图
```

### 10.2 常见错误与解决

| 错误 | 原因 | 解决 |
|------|------|------|
| `节点的返回值覆盖了整个State` | 节点的return dict没包含所有字段可以，但有的字段被错误覆盖 | 确认你的return dict只包含要更新的字段 |
| `add_conditional_edges mapping不匹配` | 决策函数返回的字符串不在mapping的key中 | 确保返回值和mapping key完全一致（包括大小写和下划线） |
| `messages被覆盖而不是追加` | 没用 `Annotated[list, add_messages]` | 加上这个标注 |
| `节点函数签名不对` | 第一个参数必须是state，类型要和StateGraph的泛型一致 | `def node(state: YourState) -> dict:` |
| `checkpointer不工作` | 没传config或config格式不对 | config必须是 `{"configurable": {"thread_id": "xxx"}}` |

### 10.3 最佳实践

1. **State 字段从少到多**：不要一开始就定义 20 个字段。先定义核心字段（query, response），跑通后再加。

2. **一个节点只做一件事**：
   ```python
   # ✅ 好
   def retrieve(state): ...  # 只做检索
   def generate(state): ...  # 只做生成
   def reflect(state): ...   # 只做自检

   # ❌ 差
   def do_everything(state): ...  # 检索+生成+自检全在这
   ```

3. **用 TypedDict 而不是普通 dict**：IDE 自动补全 + 类型检查 + 文档即代码。

4. **Prompt 集中管理**：不要散落在节点函数中，放在 `prompts/` 目录统一维护。

5. **先 mock 后真实**：
   ```python
   # Phase 3 初期：用模拟数据开发 Agent 逻辑
   MOCK_DOCS = [{"question": "...", "content": "..."}]

   # Phase 3 后期：替换为真实 RAG 检索
   from rag.retriever import MedicalRetriever
   retriever = MedicalRetriever()
   ```

6. **善用 `stream` 而不是 `invoke`**：开发时用 `stream` 可以看到每个节点的执行结果，方便定位问题。

7. **graph 的 compile 是轻量操作**：每次修改节点函数后重新 compile 即可，不需要重启服务。

---

> **下一步**：从 `agents/state.py` 开始，按照第六章的 Self-RAG 模式逐步构建 Medical-Health-Agent。
>
> 遇到问题时回到这里查看对应章节，每个模式都有可运行的完整代码。
