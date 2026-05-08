"""
LLM配置中心 — 切换模型只需改 PROVIDER 一行。

支持:
  - DashScope (Qwen3-Max / Qwen3-Flash)   via OpenAI兼容接口
  - DeepSeek (V4 Flash / V4 Pro)          via OpenAI兼容接口
  - 任意 OpenAI-Compatible API             (如 vLLM / Ollama / 本地模型)

用法:
  from config.llm import get_llm, test_connection
  llm = get_llm("analysis")  # 获取分析Agent用的LLM实例
  test_connection()          # 测试当前配置是否连通
"""
from __future__ import annotations

import os
import time
import logging
from typing import Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger("llm")

# ============================================================
# 切换开关 — 改这里一键切换 provider
# ============================================================
CURRENT_PROVIDER = "qwen"  # "qwen" | "deepseek"

# ============================================================
# Provider 配置表 — 新增 provider 在这里加一行
# ============================================================
PROVIDER_CONFIGS = {
    "qwen": {
        "model_name": "qwen3-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
        "desc": "阿里云 DashScope (Qwen3-Max)",
    },
    "qwen-flash": {
        "model_name": "qwen3-flash",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
        "desc": "阿里云 DashScope (Qwen3-Flash, 快+省)",
    },
    "deepseek": {
        "model_name": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "desc": "DeepSeek V4 Flash (deepseek-chat)",
    },
    "deepseek-pro": {
        "model_name": "deepseek-reasoner",
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "desc": "DeepSeek V4 Pro (deepseek-reasoner)",
    },
}

# ============================================================
# 各 Agent 角色的温度 / max_tokens 预设
# ============================================================
AGENT_PRESETS = {
    "router":    {"temperature": 0.0, "max_tokens": 100,  "desc": "意图路由"},
    "analysis":  {"temperature": 0.15, "max_tokens": 2048, "desc": "医疗分析 + Self-RAG"},
    "action":    {"temperature": 0.5, "max_tokens": 2048, "desc": "对话回答"},
    "reflect":   {"temperature": 0.0, "max_tokens": 300,  "desc": "Self-RAG 自检"},
    "perception": {"temperature": 0.1, "max_tokens": 1024, "desc": "健康数据感知"},
}


def _get_provider_config(provider: Optional[str] = None) -> dict:
    """获取指定 provider 的配置，校验 API Key 是否存在。"""
    provider = provider or CURRENT_PROVIDER
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(
            f"Unknown provider: {provider}. Available: {list(PROVIDER_CONFIGS)}"
        )
    cfg = PROVIDER_CONFIGS[provider]
    api_key = os.getenv(cfg["env_key"])
    if not api_key:
        raise RuntimeError(
            f"环境变量 {cfg['env_key']} 未设置。\n"
            f"  export {cfg['env_key']}=<your-api-key>\n"
            f"  或在 .env 文件中配置。"
        )
    return {**cfg, "api_key": api_key}


def get_llm(agent_role: str = "analysis", provider: Optional[str] = None, **kwargs):
    """
    获取指定角色使用的 LLM 实例。

    agent_role: "router" | "analysis" | "action" | "reflect" | "perception"
    provider:   覆盖 CURRENT_PROVIDER（不传则用默认）

    用法:
      analysis_llm = get_llm("analysis")
      action_llm   = get_llm("action", provider="deepseek")
    """
    cfg = _get_provider_config(provider)
    preset = AGENT_PRESETS.get(agent_role, AGENT_PRESETS["analysis"])

    return ChatOpenAI(
        model=cfg["model_name"],
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        temperature=preset["temperature"],
        max_tokens=preset["max_tokens"],
        **kwargs,
    )


# ============================================================
# 便捷实例 — 不传参直接用
# ============================================================
def get_router_llm(provider=None):
    return get_llm("router", provider)

def get_analysis_llm(provider=None):
    return get_llm("analysis", provider)

def get_action_llm(provider=None):
    return get_llm("action", provider)

def get_reflect_llm(provider=None):
    return get_llm("reflect", provider)

def get_perception_llm(provider=None):
    return get_llm("perception", provider)


# ============================================================
# API 连通性测试
# ============================================================
TEST_MESSAGE = "你好。请用一句话介绍你自己。（10个字以内）"


def test_one_provider(provider: str, timeout: float = 15.0) -> dict:
    """
    测试单个 provider 是否连通。

    返回: {"ok": bool, "model_name": str, "model_desc": str,
           "latency_ms": float, "response": str, "error": str}
    """
    try:
        cfg = _get_provider_config(provider)
    except RuntimeError as e:
        return {"ok": False, "model_name": "", "model_desc": "",
                "latency_ms": 0, "response": "", "error": str(e)}

    llm = ChatOpenAI(
        model=cfg["model_name"],
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        temperature=0.0,
        max_tokens=50,
        timeout=timeout,
    )

    t0 = time.perf_counter()
    try:
        resp = llm.invoke(TEST_MESSAGE)
        elapsed = (time.perf_counter() - t0) * 1000
        content = resp.content.strip() if hasattr(resp, "content") else str(resp)
        return {
            "ok": True,
            "model_name": cfg["model_name"],
            "model_desc": cfg["desc"],
            "latency_ms": round(elapsed, 1),
            "response": content[:100],
            "error": "",
        }
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "model_name": cfg["model_name"],
            "model_desc": cfg["desc"],
            "latency_ms": round(elapsed, 1),
            "response": "",
            "error": f"{type(e).__name__}: {e}",
        }


def test_all_providers(providers: Optional[list[str]] = None) -> dict:
    """
    测试所有（或指定）provider 的连通性。

    用法:
      python -m config.llm          # 直接运行，测试全部
      python -c "from config.llm import test_all_providers; print(test_all_providers())"
    """
    if providers is None:
        providers = list(PROVIDER_CONFIGS)

    results = {}
    for name in providers:
        print(f"\n{'='*60}")
        print(f"  Testing: {name} ({PROVIDER_CONFIGS[name]['desc']})")
        print(f"{'='*60}")
        result = test_one_provider(name)
        results[name] = result
        if result["ok"]:
            print(f"  🟢 型号: {result['model_name']} | {result['model_desc']}")
            print(f"  ✅ 连通成功! 延迟 {result['latency_ms']:.0f}ms")
            print(f"  响应: {result['response']}")
        else:
            print(f"  ❌ 连接失败: {result['error']}")
    return results


def test_current_provider():
    """快速测试当前默认 provider 是否连通。"""
    print(f"当前 Provider: {CURRENT_PROVIDER} ({PROVIDER_CONFIGS[CURRENT_PROVIDER]['desc']})")
    result = test_one_provider(CURRENT_PROVIDER)
    if result["ok"]:
        print(f"🟢 型号: {result['model_name']} | {result['model_desc']}")
        print(f"✅ 连通成功! 延迟 {result['latency_ms']:.0f}ms")
        print(f"   响应: {result['response']}")
    else:
        print(f"❌ 连接失败: {result['error']}")
    return result


# ============================================================
# 可直接运行 python -m config.llm 测试连通性
# ============================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 测试指定 provider: python config/llm.py deepseek
        provider = sys.argv[1]
        cfg = PROVIDER_CONFIGS.get(provider)
        if cfg is None:
            print(f"Unknown provider: {provider}. Available: {list(PROVIDER_CONFIGS)}")
            sys.exit(1)
        result = test_one_provider(provider)
        if result["ok"]:
            print(f"🟢 型号: {result['model_name']} | {result['model_desc']}")
            print(f"✅ {provider} 连通! 延迟 {result['latency_ms']:.0f}ms")
            print(f"   {result['response']}")
        else:
            print(f"❌ {provider} 失败: {result['error']}")
    else:
        # 默认测试当前 provider
        print(f"Current provider: {CURRENT_PROVIDER}")
        test_current_provider()
