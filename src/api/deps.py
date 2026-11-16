"""依赖注入：端点用 `Depends(xxx)` 拿这些东西，不自己 new、不自己查。"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Path

from src import crud
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
    """按 id 取会话；不存在就 404。"""
    session = await crud.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


async def get_active_session(
    session: SessionRecord = Depends(get_session),
) -> SessionRecord:
    """要求会话还没结束，否则 409（回答类端点用）。"""
    if session.status == "finished":
        raise HTTPException(status_code=409, detail="面试已经结束，可以 GET /report 看报告")
    return session
