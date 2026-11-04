"""把 agent 的工具调用打印出来。

为什么需要：agent 和外层代码的区别就在"它自己决定调什么工具"。
看不见工具调用，就没法判断它到底是在自主决策还是在瞎编——
本地调试、面试演示都靠这几行日志。
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class ToolCallLogger(BaseCallbackHandler):
    """打印「调了哪个工具、参数是什么、返回了什么」。"""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = serialized.get("name") or serialized.get("id") or "tool"
        print(f"    {self.prefix}[工具调用] {name}({input_str})")

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        text = str(output).replace("\n", " ")
        print(f"    {self.prefix}[工具返回] {text[:150]}")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        print(f"    {self.prefix}[工具报错] {error}")


def tool_logger(prefix: str = "") -> ToolCallLogger | None:
    """要一个打印器；设了 GRAPH_TRACE=0 就返回 None（自动化测试时静音）。"""
    if os.getenv("GRAPH_TRACE", "1") == "0":
        return None
    return ToolCallLogger(prefix)
