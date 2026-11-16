"""LLM 调用层：全项目只有这里能直接调模型。"""

from __future__ import annotations

import json
import os

import logging
from typing import Any, Literal, TypeVar

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

Method = Literal["function_calling", "json_schema", "json_mode"]

# 不加 override=True：真实环境变量优先于 .env（测试/CI 靠这个改配置）
load_dotenv()

DEFAULT_MODEL = "gpt-5.4-mini"


def _env(*names: str, default: str | None = None) -> str | None:
    """按顺序取第一个非空的同名环境变量。"""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# ChatOpenAI 内部持有连接池，按 (model, temperature) 复用实例
_model_cache: dict[tuple[str, float], ChatOpenAI] = {}


def get_chat_model(*, model: str | None = None, temperature: float = 0.0) -> ChatOpenAI:
    """模型工厂：按 (model, temperature) 缓存实例。"""
    name = model or _env("LLM_MODEL", default=DEFAULT_MODEL)
    key = (name, temperature)
    if key not in _model_cache:
        api_key = _env("CLOSEAI_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("没找到模型 API Key：请在 .env 里配 CLOSEAI_API_KEY")
        _model_cache[key] = ChatOpenAI(
            model=name,
            api_key=api_key,
            base_url=_env("CLOSEAI_API_URL", "LLM_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_URL"),
            temperature=temperature,
            timeout=60,
            max_retries=2,
        )
    return _model_cache[key]


def get_structured_model(
    schema: type[T],
    *,
    model: str | None = None,
    temperature: float = 0.0,
    method: Method = "function_calling",
    include_raw: bool = True,
):
    """拿到一个「调用后直接返回 schema 实例」的 runnable。"""
    llm = get_chat_model(model=model, temperature=temperature)
    return llm.with_structured_output(schema, method=method, include_raw=include_raw)


def _as_plain_text(message: BaseMessage) -> str:
    """把模型的一条消息压成纯文本（丢掉 tool_calls 这类会触发 API 校验的结构）。"""
    parts: list[str] = []
    content = message.content
    if isinstance(content, str):
        if content.strip():
            parts.append(content)
    elif isinstance(content, list):
        parts.extend(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    for call in getattr(message, "tool_calls", None) or []:
        args = json.dumps(call.get("args", {}), ensure_ascii=False)
        parts.append(f"（工具调用 {call.get('name')}，参数 {args}）")
    return "\n".join(parts) or "（上一轮没有输出可读内容）"


def call_json(
    schema: type[T],
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.0,
    method: Method = "function_calling",
    retries: int = 2,
) -> T:
    """要一份结构化数据；校验/解析失败就把错误原文喂回去重试。"""
    messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        runnable = get_structured_model(
            schema, model=model, temperature=temperature, method=method, include_raw=True
        )
        result: dict[str, Any] = runnable.invoke(messages)  # type: ignore[assignment]
        parsed, raw, err = result.get("parsed"), result.get("raw"), result.get("parsing_error")

        if parsed is not None:
            return parsed

        last_err = err or RuntimeError("模型没有给出可解析的结构化输出")
        log.warning("第 %d 次结构化输出失败: %s", attempt + 1, str(last_err)[:300])

        # 把模型上一轮的输出和校验错误一起塞回去，让它自己改
        # 坑：raw 走 function_calling 时带 tool_calls，原样追加会 400（assistant 的 tool_calls 后必须紧跟 tool 消息），
        # 所以先压成纯文本
        messages.append(AIMessage(content=_as_plain_text(raw)))
        messages.append(
            HumanMessage(
                content=(
                    f"上面这份输出不符合要求，报错是：\n{str(last_err)[:800]}\n"
                    "请修正后重新输出。"
                )
            )
        )

    raise RuntimeError(f"调模型 {retries + 1} 次都没拿到合法的 {schema.__name__}：{last_err}")
