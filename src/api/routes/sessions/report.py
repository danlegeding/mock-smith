"""GET /sessions/{session_id}/report —— 拿最终报告。"""

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
    """面试结束才能拿报告。"""
    if session.status != "finished":
        raise HTTPException(status_code=409, detail="面试还没结束，先用 /answer 继续答题")
    snapshot = await graph_io.read_snapshot(graph, graph_io.config_for(session.session_id))
    return snapshot.values.get("report") or {}
