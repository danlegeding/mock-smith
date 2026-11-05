"""GET /sessions/{session_id}/report —— 拿最终报告。

报告本体在图的 state 里（`values["report"]`），这个端点只做两件事：
检查会话状态 + 把 state 里的报告取出来。没有本文件私有的辅助函数——
读快照是三个端点共用的原语，放在 `src/api/graph_io.py`。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api import graph_io
from src.api.deps import get_graph, get_session
from src.orm_models import SessionRecord

router = APIRouter(tags=["面试"])


@router.get("/sessions/{session_id}/report", response_model=dict, summary="拿最终报告")
async def get_report(
    graph: Any = Depends(get_graph),
    session: SessionRecord = Depends(get_session),
) -> dict[str, Any]:
    """面试结束才能拿报告。

    没结束返回 409 而不是 404：资源（会话）是存在的，只是报告还没生成——这两种情况
    前端要分别处理（一个提示「继续答题」，一个提示「会话不存在」）。
    """
    if session.status != "finished":
        raise HTTPException(status_code=409, detail="面试还没结束，先用 /answer 继续答题")
    snapshot = await graph_io.read_snapshot(graph, graph_io.config_for(session.session_id))
    return snapshot.values.get("report") or {}
