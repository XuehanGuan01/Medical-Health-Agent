"""
LLM配置中心 — 支持运行时动态切换模型，无需重启后端。

核心设计:
  - ModelManager 单例: 持有当前 provider 状态，线程安全
  - get_llm(role): 从 ModelManager 读取当前 provider，每次调用创建新实例
  - API 端点: GET/POST /api/v1/settings/model 供前端切换

支持:
  - 阿里云百炼 (DashScope) — Qwen / DeepSeek / Kimi / GLM 全系列
  - DeepSeek 官方 API (V4 Flash / V4 Pro)
  - 任意 OpenAI-Compatible API (如 vLLM / Ollama / 本地模型)

用法:
  from config.llm import get_llm, model_manager
  llm = get_llm("analysis")                    # 获取当前 provider 的 LLM
  model_manager.set_provider("kimi-k2.7-code") # 运行时切换
  llm = get_llm("analysis")                    # 立即使用新 provider
"""
from __future__ import annotations

import os
import time
import logging
import threading
from typing import Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger("llm")

# ============================================================
# Provider 配置表 — 所有可用模型
# ============================================================
# 阿里云百炼平台 (DashScope) 统一配置
_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DASHSCOPE_ENV_KEY = "DASHSCOPE_API_KEY"

PROVIDER_CONFIGS = {
    # ── Qwen (通义千问) 系列 ──
    "qwen3.7-max": {
        "model_name": "qwen3.7-max-2026-05-20",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.7 Max (05-20) — 最强推理",
        "series": "qwen",
    },
    "qwen3.7-max-0608": {
        "model_name": "qwen3.7-max-2026-06-08",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.7 Max (06-08) — 最新版",
        "series": "qwen",
    },
    "qwen3.7-max-preview": {
        "model_name": "qwen3.7-max-preview",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.7 Max Preview — 预览版",
        "series": "qwen",
    },
    "qwen3.7-plus": {
        "model_name": "qwen3.7-plus-2026-05-26",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.7 Plus — 性价比之选",
        "series": "qwen",
    },
    "qwen3.6-max-preview": {
        "model_name": "qwen3.6-max-preview",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.6 Max Preview",
        "series": "qwen",
    },
    "qwen3.6-27b": {
        "model_name": "qwen3.6-27b",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.6 27B — 轻量高效",
        "series": "qwen",
    },
    "qwen3.5-plus": {
        "model_name": "qwen3.5-plus-2026-04-20",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.5 Plus — 稳定版",
        "series": "qwen",
    },
    "qwen3.5-ocr": {
        "model_name": "qwen3.5-ocr",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Qwen3.5 OCR — 文档识别专用",
        "series": "qwen",
    },

    # ── DeepSeek (深度求索) 系列 — 百炼平台 ──
    "deepseek-v4-pro": {
        "model_name": "deepseek-v4-pro",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "DeepSeek V4 Pro — 深度推理",
        "series": "deepseek",
    },
    "deepseek-v4-flash": {
        "model_name": "deepseek-v4-flash",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "DeepSeek V4 Flash — 快速响应",
        "series": "deepseek",
    },

    # ── Kimi (月之暗面) 系列 ──
    "kimi-k2.7-code": {
        "model_name": "kimi-k2.7-code",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Kimi K2.7 Code — 代码专精",
        "series": "kimi",
    },
    "kimi-k2.6": {
        "model_name": "kimi-k2.6",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "Kimi K2.6 — 通用对话",
        "series": "kimi",
    },

    # ── GLM (智谱) 系列 ──
    "glm-5.2": {
        "model_name": "glm-5.2",
        "base_url": _DASHSCOPE_BASE_URL,
        "env_key": _DASHSCOPE_ENV_KEY,
        "desc": "GLM 5.2 — 智谱旗舰",
        "series": "glm",
    },

    # ── DeepSeek 官方 API（独立 API Key） ──
    "deepseek-official-flash": {
        "model_name": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "desc": "DeepSeek V4 Flash (官方API)",
        "series": "deepseek",
    },
    "deepseek-official-pro": {
        "model_name": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "desc": "DeepSeek V4 Pro (官方API)",
        "series": "deepseek",
    },
}

# 向后兼容别名
PROVIDER_CONFIGS["qwen"] = PROVIDER_CONFIGS["qwen3.7-max"]
PROVIDER_CONFIGS["deepseek"] = PROVIDER_CONFIGS["deepseek-v4-flash"]

# 默认 provider
DEFAULT_PROVIDER = "qwen3.7-max"

# ============================================================
# 各 Agent 角色的温度 / max_tokens 预设
# ============================================================
AGENT_PRESETS = {
    "router":     {"temperature": 0.0,  "max_tokens": 100,  "desc": "意图路由"},
    "analysis":   {"temperature": 0.15, "max_tokens": 2048, "desc": "医疗分析 + Self-RAG"},
    "action":     {"temperature": 0.5,  "max_tokens": 2048, "desc": "对话回答"},
    "reflect":    {"temperature": 0.0,  "max_tokens": 300,  "desc": "Self-RAG 自检"},
    "perception": {"temperature": 0.1,  "max_tokens": 1024, "desc": "健康数据感知"},
}


# ============================================================
# ModelManager — 运行时动态切换的单例
# ============================================================

class ModelManager:
    """
    线程安全的模型管理器（单例模式）。

    所有 get_llm() 调用通过此实例读取当前 provider，
    API 端点通过 set_provider() 动态切换，即时生效。

    用法:
      from config.llm import model_manager
      model_manager.set_provider("deepseek-v4-pro")  # 切换
      current = model_manager.get_provider()           # 查询
    """

    def __init__(self, default_provider: str = DEFAULT_PROVIDER):
        self._lock = threading.Lock()
        self._provider = default_provider
        self._history: list[dict] = []  # 切换历史记录
        logger.info(f"ModelManager initialized with provider: {default_provider}")

    def get_provider(self) -> str:
        """获取当前 provider 名称。"""
        with self._lock:
            return self._provider

    def set_provider(self, provider: str) -> dict:
        """
        动态切换 provider，即时生效。

        Args:
            provider: PROVIDER_CONFIGS 中的 key

        Returns:
            {"previous": str, "current": str, "model_name": str, "desc": str}

        Raises:
            ValueError: provider 不存在
            RuntimeError: API Key 未配置
        """
        if provider not in PROVIDER_CONFIGS:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Available: {list(PROVIDER_CONFIGS.keys())}"
            )

        # 预检查 API Key
        cfg = PROVIDER_CONFIGS[provider]
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            raise RuntimeError(
                f"环境变量 {cfg['env_key']} 未设置，无法切换到 {provider}"
            )

        with self._lock:
            previous = self._provider
            self._provider = provider
            self._history.append({
                "from": previous,
                "to": provider,
                "timestamp": time.time(),
            })
            # 只保留最近 50 条记录
            if len(self._history) > 50:
                self._history = self._history[-50:]

        logger.info(f"Provider switched: {previous} → {provider}")
        return {
            "previous": previous,
            "current": provider,
            "model_name": cfg["model_name"],
            "desc": cfg["desc"],
        }

    def get_config(self, provider: Optional[str] = None) -> dict:
        """获取指定 provider（或当前 provider）的完整配置。"""
        provider = provider or self.get_provider()
        if provider not in PROVIDER_CONFIGS:
            raise ValueError(f"Unknown provider: {provider}")
        cfg = PROVIDER_CONFIGS[provider]
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            raise RuntimeError(f"环境变量 {cfg['env_key']} 未设置")
        return {**cfg, "api_key": api_key, "provider_key": provider}

    def get_history(self) -> list[dict]:
        """获取切换历史。"""
        with self._lock:
            return list(self._history)

    @staticmethod
    def list_available_providers() -> list[dict]:
        """列出所有可用 provider（API Key 已配置的）。"""
        available = []
        for key, cfg in PROVIDER_CONFIGS.items():
            # 跳过别名
            if key in ("qwen", "deepseek"):
                continue
            api_key = os.getenv(cfg["env_key"])
            available.append({
                "key": key,
                "model_name": cfg["model_name"],
                "desc": cfg["desc"],
                "series": cfg.get("series", "other"),
                "available": bool(api_key),
            })
        return available


# ── 模块级单例 ──
model_manager = ModelManager()


# ============================================================
# 核心函数 — 所有 Agent 通过此函数获取 LLM
# ============================================================

def get_llm(agent_role: str = "analysis", provider: Optional[str] = None, **kwargs):
    """
    获取指定角色使用的 LLM 实例。

    每次调用都从 model_manager 读取当前 provider，
    因此运行时切换 provider 后，下次调用立即生效。

    agent_role: "router" | "analysis" | "action" | "reflect" | "perception"
    provider:   覆盖当前 provider（不传则用 model_manager 的值）

    用法:
      analysis_llm = get_llm("analysis")
      action_llm   = get_llm("action", provider="deepseek-v4-pro")
    """
    cfg = model_manager.get_config(provider)
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

TEST_MESSAGE = "你是什么模型？请具体到型号（max/pro/flash）。你的训练截至日期是什么时候？（20个字以内）"


def test_one_provider(provider: str, timeout: float = 15.0) -> dict:
    """
    测试单个 provider 是否连通。

    返回: {"ok": bool, "model_name": str, "model_desc": str,
           "latency_ms": float, "response": str, "error": str}
    """
    try:
        cfg = model_manager.get_config(provider)
    except (ValueError, RuntimeError) as e:
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
        providers = [k for k in PROVIDER_CONFIGS if k not in ("qwen", "deepseek")]

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
    current = model_manager.get_provider()
    cfg = PROVIDER_CONFIGS[current]
    print(f"当前 Provider: {current} ({cfg['desc']})")
    result = test_one_provider(current)
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
        # 测试指定 provider: python config/llm.py deepseek-v4-pro
        provider = sys.argv[1]
        cfg = PROVIDER_CONFIGS.get(provider)
        if cfg is None:
            print(f"Unknown provider: {provider}. Available: {list(PROVIDER_CONFIGS.keys())}")
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
        current = model_manager.get_provider()
        print(f"Current provider: {current}")
        test_current_provider()
