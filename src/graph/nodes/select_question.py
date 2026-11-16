"""节点 4：select_question —— 从题池里挑下一题。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.graph.policy import MAX_QUESTIONS_PER_DIM, MAX_SKIPS_PER_DIM, MAX_TURNS, counted_turns
from src.graph.state import InterviewState, QuestionDict, TurnDict


def _count_turns_by_dimension(turns: list[TurnDict]) -> tuple[Counter, Counter]:
    """按维度统计：问了几次（Asked）、跳过几次（Skipped）。"""
    asked: Counter = Counter()
    skipped: Counter = Counter()
    for turn in turns:
        dimension = turn["question"]["dimension"]
        asked[dimension] += 1
        if turn.get("skipped"):
            skipped[dimension] += 1
    return asked, skipped


def _pick_question(
    plan: list[QuestionDict],
    turns: list[TurnDict],
    hint: int | None = None,
) -> QuestionDict | None:
    """从题池里挑下一题；没有可问的返回 None（表示该结束了）。"""
    if counted_turns(turns) >= MAX_TURNS:
        return None

    asked, skipped = _count_turns_by_dimension(turns)
    asked_texts = {turn["question"]["text"] for turn in turns}

    candidates: list[QuestionDict] = []
    for question in plan:
        dimension = question["dimension"]
        if question["text"] in asked_texts:
            continue
        if asked[dimension] >= MAX_QUESTIONS_PER_DIM:
            continue
        if skipped[dimension] >= MAX_SKIPS_PER_DIM:
            continue
        candidates.append(question)

    if not candidates:
        return None

    # 先问"最没问过的维度"；decide_next 给了难度提示时，优先挑贴近提示难度的题
    if hint:
        candidates.sort(
            key=lambda q: (asked[q["dimension"]], abs(q["difficulty"] - hint), q["difficulty"])
        )
    else:
        candidates.sort(key=lambda q: (asked[q["dimension"]], q["difficulty"]))
    return candidates[0]


def select_question(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：挑出下一题放进 current_question。"""
    # 这个节点只读 state：挑题、计数都不改 plan / turns 里的内容，
    # 所以直接拿原列表，不复制（要 append / 替换元素的节点才需要 list() 复制一份）。
    plan = state.get("question_plan") or []
    turns = state.get("turns") or []
    question = _pick_question(plan, turns, state.get("next_difficulty"))
    # next_difficulty 是一次性提示：用掉就清空，否则会一直影响后面所有选题
    return {"current_question": question, "next_difficulty": None}
