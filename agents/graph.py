"""
LangGraph StateGraph 编译 + chat() 对话入口（Phase 4 多轮记忆升级）。

拓扑:
  START → router → perception / retrieve / action / (emergency shortcut)
  perception → action → END
  retrieve → generate → reflect → revise(generate) / reject → action / accept → action
  emergency shortcut: boundary 检测 → 直接返回拒答，不调 LLM

Phase 4 多轮逻辑:
  ① 从 memory.history 读最近 5 轮 → 注入 state["messages"]
  ② Router 只读当前 query（不读历史，Q8决策）
  ③ Graph 执行完成后自动写入 chat_history
"""
import logging
import uuid

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

from agents.state import AgentState
from agents.boundary import check_emergency
from agents.router import router_node
from agents.analysis import retrieve, generate, reflect, revise, should_retry
from agents.perception import perception_node
from agents.action import action_node, reject_node as reject_node_fn

logger = logging.getLogger("agent.graph")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # 节点注册
    graph.add_node("router", router_node)
    graph.add_node("perception", perception_node)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("reflect", reflect)
    graph.add_node("revise", revise)
    graph.add_node("reject", reject_node_fn)
    graph.add_node("action", action_node)

    graph.set_entry_point("router")

    # 路由条件边
    graph.add_conditional_edges(
        "router",
        _route_condition,
        {
            "perception": "perception",
            "analysis": "retrieve",
            "action": "action",
            "emergency": "action",
        },
    )

    # perception → action
    graph.add_edge("perception", "action")

    # Self-RAG 闭环
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "reflect")
    graph.add_conditional_edges(
        "reflect",
        should_retry,
        {
            "revise": "revise",
            "reject": "reject",
            "accept": "action",
        },
    )
    graph.add_edge("revise", "generate")   # 回 generate 重生成
    graph.add_edge("reject", END)          # reject → END（不调 action，直接拒答）

    # action → END
    graph.add_edge("action", END)

    return graph.compile()


def _route_condition(state: AgentState) -> str:
    return state.get("route", "action")


# ── 编译图（模块级单例） ──
agent_graph = build_graph()


# ── chat() 入口 ──

def chat(query: str, session_id: str = None) -> dict:
    """
    Phase 4 多轮对话入口。

    返回:
      {
        "response": str, "intent": str, "route": str,
        "source": str, "safety_level": str, "retry_count": int,
        "session_id": str,
      }
    """
    if session_id is None:
        session_id = uuid.uuid4().hex[:8]

    # 硬边界短路（不受历史影响）
    is_emergency, emergency_msg = check_emergency(query)
    if is_emergency:
        _save_turn(session_id, "user", query)
        _save_turn(session_id, "assistant", emergency_msg,
                   intent="emergency", safety_level="emergency")
        return {
            "response": emergency_msg, "intent": "emergency",
            "route": "emergency", "source": "rule",
            "safety_level": "emergency", "retry_count": 0,
            "session_id": session_id,
        }

    # ① 注入历史 → state["messages"]
    messages = _load_history(session_id)

    # ② 保存当前 user query
    _save_turn(session_id, "user", query)

    # ③ 执行 Graph（Router 仅读 query，不受历史影响）
    initial: AgentState = {
        "query": query,
        "messages": messages,
        "intent": None, "route": None,
        "health_metrics": None, "personal_context": None,
        "retrieved_docs": None, "draft_response": None,
        "reflection": None, "retry_count": 0,
        "response": None, "source": None,
        "safety_level": "normal",
    }

    result = agent_graph.invoke(initial)

    # ④ 保存 assistant 回复
    _save_turn(
        session_id, "assistant",
        result.get("response", ""),
        intent=result.get("intent"),
        safety_level=result.get("safety_level", "normal"),
        retry_count=result.get("retry_count", 0),
    )

    return {
        "response": result.get("response", ""),
        "intent": result.get("intent", ""),
        "route": result.get("route", ""),
        "source": result.get("source", ""),
        "safety_level": result.get("safety_level", "normal"),
        "retry_count": result.get("retry_count", 0),
        "session_id": session_id,
    }


# ── Phase 4 辅助函数 ──

def _load_history(session_id: str) -> list:
    """从 memory.db 读最近 5 轮，转 langchain 消息格式"""
    try:
        from memory.database import get_memory_db
        from memory.history import get_recent_history
        g = get_memory_db()
        db = next(g)
        try:
            history = get_recent_history(db, session_id)
            messages = []
            for h in history:
                if h["role"] == "user":
                    messages.append(HumanMessage(content=h["content"]))
                else:
                    messages.append(AIMessage(content=h["content"]))
            return messages
        finally:
            db.close()
    except Exception:
        return []


def _save_turn(session_id: str, role: str, content: str,
               intent: str = None, safety_level: str = "normal",
               retry_count: int = 0):
    """写入 memory.db 的 chat_history 表"""
    try:
        from memory.database import get_memory_db
        from memory.history import save_turn
        g = get_memory_db()
        db = next(g)
        try:
            save_turn(db, session_id, role, content,
                      intent=intent, safety_level=safety_level,
                      retry_count=retry_count)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to save chat history: {e}")


# ── 线程安全确认 ──
#
# langgraph.StateGraph.compile() 返回的 CompiledGraph 是 immutable 的
# 运行时状态完全封装在每次 invoke() 调用传递的 state dict 中
# 无共享可变状态 → 天然线程安全
#
# 单例 _retriever (analysis.py) 仅读取 ChromaDB → 线程安全
# SessionLocal (perception.py) 每次创建新会话 → 线程安全
