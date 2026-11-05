"""POST /sessions/{session_id}/answer —— 回答一轮。

这个文件自带它需要的全部函数：入口 `answer_session`、它调用的 `_submit_answer`
和 `_save_report_if_finished`。只有被多个端点共用的原语才放在 `src/api/graph_io.py`。

图里跑：评分 → 决策 → 挑下一题（或收尾），返回下一题或最终报告。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from langgraph.types import Command

from src.api import graph_io
from src.api.deps import get_active_session, get_graph
from src.model import DIMENSIONS, TurnOut
from src.orm_models import ReportRecord, SessionRecord

router = APIRouter(tags=["面试"])


async def _save_report_if_finished(session_id: str, values: dict[str, Any]) -> None:
    """报告生成后落库一次，并把会话标成 finished（重复调用不会写两份）。

    只在这个文件里用：报告落库是「答完最后一轮」的副作用，别的端点不写库。
    """
    report = values.get("report")
    if not report:
        return

    session = await SessionRecord.get_or_none(session_id=session_id)
    if session is None or session.status == "finished":
        return

    turns = values.get("turns") or []
    averages: dict[str, float] = report.get("dimension_summary") or {}
    overall_score = round(sum(averages.values()) / len(averages), 2) if averages else 0.0
    asked = {turn["question"]["dimension"] for turn in turns}
    skipped_dims = [d.value for d in DIMENSIONS if d.value not in asked]

    await ReportRecord.create(
        session=session,
        overall=report["overall"],
        overall_score=overall_score,
        dimension_summary=averages,
        strengths=report.get("strengths", []),
        weaknesses=report.get("weaknesses", []),
        gap_conclusion=report.get("gap_conclusion", ""),
        next_steps=report.get("next_steps", []),
        turns_used=len(turns),
        skipped_dims=skipped_dims,
    )
    session.status = "finished"
    await session.save(update_fields=["status"])


async def _submit_answer(
    graph: Any, config: dict[str, Any], session_id: str, answer: str
) -> TurnOut:
    """提交一轮回答：resume 图 → 落库（如果结束了）→ 返回下一题或报告。

    空回答按跳过处理：接口上「跳过」和「答了但没内容」是同一件事，
    都由图的 skip 分支记一条 turn，不在这里分叉。
    """
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
    """把回答 resume 进图，返回下一题或最终报告。

    `answer` 传空字符串 = 跳过（图里走 skip 分支）。会话已结束则 409（由依赖拦）。
    请求体形状：`{"answer": "..."}`；`session_id` 只在路径里出现一次，不重复收。
    """
    config = graph_io.config_for(session.session_id)
    return await _submit_answer(graph, config, session.session_id, answer)
