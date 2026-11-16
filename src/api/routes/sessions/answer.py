"""POST /sessions/{session_id}/answer —— 回答一轮。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from langgraph.types import Command

from src import crud
from src.api import graph_io
from src.api.deps import get_active_session, get_graph
from src.graph.policy import active_dimensions
from src.model import TurnOut
from src.orm_models import SessionRecord

router = APIRouter(tags=["面试"])


async def _save_report_if_finished(session_id: str, values: dict[str, Any]) -> None:
    """报告生成后落库一次，并把会话标成 finished（重复调用不会写两份）。"""
    report = values.get("report")
    if not report:
        return

    session = await crud.get_session(session_id)
    if session is None or session.status == "finished":
        return

    turns = values.get("turns") or []
    averages: dict[str, float] = report.get("dimension_summary") or {}
    overall_score = round(sum(averages.values()) / len(averages), 2) if averages else 0.0
    asked = {turn["question"]["dimension"] for turn in turns}
    skipped_dims = [
        d.value for d in active_dimensions(values.get("resume_profile") or {}) if d.value not in asked
    ]

    await crud.save_report(
        session,
        report,
        overall_score=overall_score,
        turns_used=len(turns),
        skipped_dims=skipped_dims,
    )
    await crud.finish_session(session)


async def _submit_answer(
    graph: Any, config: dict[str, Any], session_id: str, answer: str
) -> TurnOut:
    """提交一轮回答：resume 图 → 落库（如果结束了）→ 返回下一题或报告。"""
    reply = {"text": answer} if answer.strip() else {"skip": True}
    await graph_io.invoke_graph(graph, config, Command(resume=reply))

    snapshot = await graph_io.read_snapshot(graph, config)
    await _save_report_if_finished(session_id, snapshot.values)
    return graph_io.build_turn_out(session_id, snapshot)


@router.post("/sessions/{session_id}/answer", response_model=TurnOut, summary="回答一轮")
async def answer_session(
    graph: Any = Depends(get_graph),
    session: SessionRecord = Depends(get_active_session),
    answer: str = Body(default="", embed=True, description="候选人回答；留空表示跳过"),
) -> TurnOut:
    """把回答 resume 进图，返回下一题或最终报告。"""
    config = graph_io.config_for(session.session_id)
    return await _submit_answer(graph, config, session.session_id, answer)
