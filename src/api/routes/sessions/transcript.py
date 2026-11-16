"""GET /sessions/{session_id}/transcript —— 拿一场面试的问答记录。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.api import graph_io
from src.api.deps import get_graph, get_session
from src.model import Question
from src.orm_models import SessionRecord

router = APIRouter(tags=["面试"])


def _as_dict(item: Any) -> dict[str, Any]:
    """state 里的 turn 可能是 pydantic 对象，也可能已经是 dict（取决于节点怎么写的），这里统一。"""
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return dict(item)


@router.get("/sessions/{session_id}/transcript", response_model=dict, summary="拿问答记录")
async def get_transcript(
    graph: Any = Depends(get_graph),
    session: SessionRecord = Depends(get_session),
) -> dict[str, Any]:
    """返回 `{"session_id", "status", "turns": [...], "pending_question": {...} | None}`。"""
    snapshot = await graph_io.read_snapshot(graph, graph_io.config_for(session.session_id))
    turns = [_as_dict(turn) for turn in (snapshot.values.get("turns") or [])]
    pending = graph_io.first_interrupt(snapshot)
    return {
        "session_id": session.session_id,
        "status": session.status,
        "turns": [
            {
                "question": turn.get("question"),
                "answer": turn.get("answer", ""),
                "score": turn.get("score"),
                "skipped": turn.get("skipped", False),
            }
            for turn in turns
        ],
        "pending_question": (
            Question.model_validate(pending).model_dump(mode="json") if pending is not None else None
        ),
    }
