"""LLM 调用层：全项目只有这里能直接调模型。

两个入口：
- `chat()`               —— 要一段自由文字（后面写报告点评时用）
- `call_json()`          —— 要一份结构化数据（Pydantic 实例）

结构化输出走 LangChain 的 `ChatOpenAI.with_structured_output(schema)`：
你给它一个 Pydantic 类，它返回的 runnable 直接吐出这个类的实例，
不用自己解析 JSON 字符串，也不用自己拼 JSON Schema 塞进 prompt。

三个参数值得知道：
- `method`：`"function_calling"`（工具调用，兼容性最好，默认用它）、
  `"json_schema"`（OpenAI 严格结构化输出，中转站不一定支持）、
  `"json_mode"`（要求 prompt 里出现 "JSON" 字样）。
- `include_raw=True`：返回 `{"raw": AIMessage, "parsed": 实例或 None,
  "parsing_error": 异常或 None}`。解析失败率是可以统计的指标，别把它藏起来。
- `temperature=0`：抽取类任务不需要创造力。

base_url 必须自带 `/v1`（.env 里写全，例如 https://api.openai-proxy.org/v1）：
中转站少这一段就是 404 page not found。
"""

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

# 模块被 import 时读一次 .env，把里面的键写进 os.environ。
# 不加 override=True：真实环境变量优先级要高于文件（测试/CI 靠这个改配置）。
load_dotenv()

# 默认模型。中转站上 gpt-5.4-mini 实测可用（chat 和两种结构化输出都通）。
DEFAULT_MODEL = "gpt-5.4-mini"


def _env(*names: str, default: str | None = None) -> str | None:
    """按顺序取第一个非空的同名环境变量。

    为什么列多个名字：.env 里用过 CLOSEAI_* 这套，以后可能改成 OPENAI_* / LLM_*。
    在这里一次认完，改 .env 不用回来改代码。
    """
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# ChatOpenAI 内部持有 httpx 连接池，别每次调用都新建一个。
# key 用 (model, temperature)，同一规格复用同一个实例。
_model_cache: dict[tuple[str, float], ChatOpenAI] = {}


def get_chat_model(*, model: str | None = None, temperature: float = 0.0) -> ChatOpenAI:
    """模型工厂：按 (model, temperature) 缓存实例。

    两个坑：
    1. `model or _env("LLM_MODEL", default=...)` 的兜底不能省：调用方不传 model 时它是 None，
       直接塞给 ChatOpenAI 会报 "model Input should be a valid string"。
    2. 这里的键名必须和 .env 里的一致（CLOSEAI_API_KEY / CLOSEAI_API_URL）。
       配错不会报"配置错了"，只会在后面拿到 None，然后炸在一行看不懂的 pydantic 报错上。
    3. base_url 从 .env 原样读，不做拼接——所以 .env 里必须写全 `.../v1`。
       少了 /v1 的症状是 404 page not found；整个缺了会回落到官方 api.openai.com 再 401。
    """
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


def chat(
    messages: list[BaseMessage] | list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> str:
    """要一段自由文字：发消息，拿字符串。"""
    resp = get_chat_model(model=model, temperature=temperature).invoke(messages)
    content = resp.content
    if isinstance(content, str):
        return content
    # 少数多模态模型会返回 list[dict]，把其中的文本拼起来
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


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
    """要一份结构化数据；校验/解析失败就把错误原文喂回去重试。

    返回的已经是 `schema` 的实例，可以直接用 `.field` 取值。
    """
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

        # 关键的一步：把模型刚才的输出 + 校验器说的错误一起塞回对话。
        # 模型看得懂自己的错误，会自己改；我们不用写一行"该怎么修"的逻辑。
        #
        # 坑：不能把 raw 原样塞回去。走 function_calling 时它是带 tool_calls 的
        #     AIMessage，而 OpenAI 规定 assistant 的 tool_calls 后面必须紧跟对应的
        #     tool 消息；少一条就整轮 400：
        #     An assistant message with 'tool_calls' must be followed by tool messages...
        #     所以要的只是"它上轮输出了什么"，先压成纯文本再追加，别把函数调用的壳带回去。
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
