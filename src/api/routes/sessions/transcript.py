"""GET /sessions/{session_id}/transcript —— 拿一场面试的问答记录。

为什么需要它：`reports` 表只存了结论，用户想回看「当时问了什么、我答了什么」就得读图的
state。checkpointer 里每次 checkpoint 都留着完整 state，这里只是把 `turns` 摆出来，
不重新调模型、不产生费用。

未结束的会话也能取（返回已经答过的部分）——记录页要能看进行中的那一场；
并且额外给出 `pending_question`：前端靠它把「继续这场面试」还原回面试页，
不用再猜下一题是什么。
"""

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
    """返回 `{"session_id", "status", "turns": [...], "pending_question": {...} | None}`。

    问答顺序就是 `turns` 的顺序；`skipped=True` 表示这一题被跳过（没有回答）。
    `pending_question` 是「图停在这一题上、还没答」的那道题，已结束的会话为 None。
    """
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
