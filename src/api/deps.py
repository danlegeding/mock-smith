"""依赖注入：端点用 `Depends(xxx)` 拿这些东西，不自己 new、不自己查。

FastAPI 的依赖就是"每个端点都需要的前置条件"：
- `get_graph()`：图单例。每次编译都会新建 psycopg 连接池，所以只能编译一次。
- `get_session()`：按 id 取会话，不存在直接 404。
- `get_active_session()`：在上一行的基础上再要求"还没面完"，否则 409。

好处：3 个端点都用到"会话必须存在"这条规则，只写一次；而且依赖可以链式复用
（`get_active_session` 依赖 `get_session`），不用手动传 session 对象。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Path

from src.graph.build import build_persistent_graph
from src.orm_models import SessionRecord

_graph: Any = None


def get_graph() -> Any:
    """进程内只编译一次图（重复编译 = 重复新建连接池 + 图上 interrupt 的恢复点会变）。"""
    global _graph
    if _graph is None:
        _graph = build_persistent_graph()
    return _graph


async def get_session(
    session_id: str = Path(description="会话 id（就是图里的 thread_id）"),
) -> SessionRecord:
    """按 id 取会话；不存在就 404。

    注意参数名 `session_id` 必须和路由里的 `{session_id}` 同名——
    FastAPI 靠名字把路径参数注入进来，改名就 422。
    """
    session = await SessionRecord.get_or_none(session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


async def get_active_session(
    session: SessionRecord = Depends(get_session),
) -> SessionRecord:
    """要求会话还没结束，否则 409（回答类端点用）。

    409 而不是 403/400：请求本身没毛病，只是"当前状态不允许"，409 Conflict 正好。
    """
    if session.status == "finished":
        raise HTTPException(status_code=409, detail="面试已经结束，可以 GET /report 看报告")
    return session
