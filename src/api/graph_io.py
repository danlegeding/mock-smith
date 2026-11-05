"""图操作的公共原语：被 2 个以上端点用到的那几个函数才放这里。

为什么有这个文件：按「调用者与被调用者放在一起」组织代码时，大多数函数应该待在
调用它的那个端点文件里（`create.py` 里的 `_start_interview`、`answer.py` 里的
`_submit_answer`）。但下面这三个是被**多个**端点共用的——放进任何一个端点文件，
另外两个就得 import 隔壁端点，或者复制一份：

    config_for       3 个端点都要构造 thread_id 配置
    read_snapshot    3 个端点都要读图的状态快照
    invoke_graph     2 个端点都要推进图
    build_turn_out   2 个端点要把"图停在哪"翻译成接口响应

共用的东西集中在一个明确标注「公共」的文件里，比复制三份好：改一处不会漏另外两处。

所有图调用都走 `run_in_threadpool`：图是同步的（psycopg 连接池同步），
在 async 端点里直接调会卡住事件循环——本地单人跑看不出来，一并发就现原形。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.concurrency import run_in_threadpool
from langgraph.types import Command  # noqa: F401  - 调用方会用到 Command，一起导出

from src.api.errors import APIError
from src.model import Question, Report, TurnOut


def config_for(session_id: str) -> dict[str, Any]:
    """LangGraph 的调用配置。thread_id 就是 session_id——两者必须一致，否则断线续不上。"""
    return {"configurable": {"thread_id": session_id}}


def new_session_id() -> str:
    """16 位十六进制够用且好念；不用完整 uuid4 是为了日志和 URL 干净。"""
    return uuid.uuid4().hex[:16]


def first_interrupt(snapshot: Any) -> dict[str, Any] | None:
    """图停在哪个 interrupt 上，就把那个问题取出来；返回 None 表示已经跑完。"""
    for task in snapshot.tasks:
        for item in task.interrupts:
            return item.value
    return None


async def read_snapshot(graph: Any, config: dict[str, Any]) -> Any:
    """读一次图的状态快照（一个 DB roundtrip）。

    快照里同时有 `values`（全部 state）和 `tasks[].interrupts`（停在哪一题），
    所以「要不要给下一题」和「state 里有什么」一次读全，别读两遍。
    """
    return await run_in_threadpool(graph.get_state, config)


async def invoke_graph(graph: Any, config: dict[str, Any], payload: Any) -> None:
    """推进图一次：`payload` 是初始 state（dict）或 `Command(resume=...)`。"""
    try:
        await run_in_threadpool(graph.invoke, payload, config)
    except Exception as exc:  # noqa: BLE001 - 图里任何异常都要带上原因返回给调用方
        raise APIError(500, f"面试流程执行失败：{exc}") from exc


def build_turn_out(session_id: str, snapshot: Any) -> TurnOut:
    """把「图当前停在哪」翻译成接口响应：下一题，或者最终报告。"""
    values = snapshot.values
    turns = values.get("turns") or []
    pending = first_interrupt(snapshot)

    if pending is not None:
        return TurnOut(
            session_id=session_id,
            type="question",
            question=Question.model_validate(pending),
            turn_index=len(turns),
        )

    report = values.get("report")
    if report is None:
        # 图跑完却没有报告：这是配置/节点问题，值得 500（别伪装成「面试结束」）
        raise APIError(500, "面试已结束但没有生成报告")
    return TurnOut(
        session_id=session_id,
        type="report",
        report=Report.model_validate(report),
        turn_index=len(turns),
    )
