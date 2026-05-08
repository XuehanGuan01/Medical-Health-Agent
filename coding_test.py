from langchain_community.llms.tongyi import Tongyi

llm=Tongyi(
    model="qwen3-max",
)

from langchain_deepseek import ChatDeepSeek
# 实例化模型
llm2 = ChatDeepSeek(
    model="deepseek-V4-pro",  # 非推理模型，支持工具调用
    temperature=0.7,
    max_tokens=1024
)