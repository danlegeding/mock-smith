"""POST /sessions —— 开一场面试。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src import crud
from src.api import graph_io
from src.api.deps import get_graph
from src.model import SessionCreate, TurnOut

router = APIRouter(tags=["面试"])


async def _start_interview(
    graph: Any,
    config: dict[str, Any],
    session_id: str,
    jd_text: str,
    resume_text: str,
) -> TurnOut:
    """开一场面试：跑图到第一题 → 建 session 行 → 返回第一题。"""
    await graph_io.invoke_graph(graph, config, {"jd_text": jd_text, "resume_text": resume_text})

    snapshot = await graph_io.read_snapshot(graph, config)
    jd_title = (snapshot.values.get("jd_profile") or {}).get("role_title", "")
    await crud.create_session(session_id, jd_title)
    return graph_io.build_turn_out(session_id, snapshot)


@router.post("/sessions", response_model=TurnOut, summary="开一场面试")
async def create_session(
    payload: SessionCreate,
    graph: Any = Depends(get_graph),
) -> TurnOut:
    """开一场面试，返回 `session_id` + 第一题。"""
    session_id = graph_io.new_session_id()
    config = graph_io.config_for(session_id)
    return await _start_interview(
        graph, config, session_id, payload.jd_text, payload.resume_text
    )
