"""节点 5：ask —— 把问题抛给用户，等回答回来。"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from src.graph.state import InterviewState
from src.model import Question, Turn


def ask_question(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：提问 → 暂停等回答 → 把这一轮记录进 turns。"""
    # question_plan 里存的是 dict，这里还原成模型才能拿枚举、用 model_dump
    question = Question.model_validate(state["current_question"])

    # resume 会重放本节点：interrupt 前不能有副作用；载荷用 model_dump 全量带出，手写字段清单会漏字段
    reply = interrupt(question.model_dump(mode="json"))

    # resume 允许两种写法：直接给字符串，或给 {"text": ...} / {"skip": True}
    if isinstance(reply, str):
        reply = {"text": reply}
    skipped = bool(reply.get("skip"))
    answer = "" if skipped else str(reply.get("text", "")).strip()

    turn = Turn(question=question, answer=answer, skipped=skipped)
    turns = list(state.get("turns") or [])
    turns.append(turn.model_dump(mode="json"))
    return {"turns": turns, "current_question": None}
