"""把 agent 的工具调用打到日志里。

为什么需要：agent 和外层代码的区别就在"它自己决定调什么工具"。
看不见工具调用，就没法判断它到底是在自主决策还是在瞎编——
本地调试、面试演示都靠这几行日志。
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from src.log import get_logger

logger = get_logger(__name__)


class ToolCallLogger(BaseCallbackHandler):
    """记录「调了哪个工具、参数是什么、返回了什么」。"""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = serialized.get("name") or serialized.get("id") or "tool"
        logger.info("    %s[工具调用] %s(%s)", self.prefix, name, input_str)

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        text = str(output).replace("\n", " ")
        logger.info("    %s[工具返回] %s", self.prefix, text[:150])

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        logger.info("    %s[工具报错] %s", self.prefix, error)


def tool_logger(prefix: str = "") -> ToolCallLogger | None:
    """要一个记录器；设了 GRAPH_TRACE=0 就返回 None（自动化测试时静音）。"""
    if os.getenv("GRAPH_TRACE", "1") == "0":
        return None
    return ToolCallLogger(prefix)


def tool_callbacks(prefix: str = "") -> list[BaseCallbackHandler]:
    """给 invoke(config={"callbacks": ...}) 用的回调列表。

    有记录器就返回 [记录器]，静音时返回空列表——
    这样调用方不用写 `[x] if (x := tool_logger()) else []` 这种表达式。
    """
    handler = tool_logger(prefix)
    if handler is None:
        return []
    return [handler]
