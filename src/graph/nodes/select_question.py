"""节点 4：select_question —— 从题池里挑下一题。

这一步**不调用大模型**，全是规则。原因：挑题是"根据已问情况做选择"，
规则能说清、能测、能离线复现；交给模型反而每次行为不一样，面试里没法解释。

规则（按优先级）：
1. 本轮数到 MAX_TURNS → 不问了，结束（跳过的不计入轮数）
2. 这一题已经问过（按题干去重）→ 跳过
3. 这个维度已经问够 MAX_QUESTIONS_PER_DIM 道 → 跳过
4. 这个维度被跳过 MAX_SKIPS_PER_DIM 次 → 跳过（别继续为难人）
5. 在剩下的题里：优先问"被问次数最少的维度"，同分时先问难度低的
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.graph.policy import MAX_QUESTIONS_PER_DIM, MAX_SKIPS_PER_DIM, MAX_TURNS, counted_turns
from src.graph.state import InterviewState, QuestionDict, TurnDict


def _count_turns_by_dimension(turns: list[TurnDict]) -> tuple[Counter, Counter]:
    """按维度统计：问了几次（Asked）、跳过几次（Skipped）。

    Args:
        turns: 已发生的问答轮次列表。

    Returns:
        tuple[Counter, Counter]: (asked, skipped)，键都是维度英文值。
    """
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
    """从题池里挑下一题；没有可问的返回 None（表示该结束了）。

    Args:
        plan: 完整题池。
        turns: 已问过的轮次。
        hint: decide_next 给的难度提示（1/2/3），仅在挑题时参考难易排序。

    Returns:
        dict | None: 选中的题目 dict；无可问题目时返回 None。
    """
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
    """LangGraph 节点函数：挑出下一题放进 current_question。

    - 有题可问 → {"current_question": {...}}
    - 问完了 → {"current_question": None}（路由函数据此走向 END）
    """
    # 这个节点只读 state：挑题、计数都不改 plan / turns 里的内容，
    # 所以直接拿原列表，不复制（要 append / 替换元素的节点才需要 list() 复制一份）。
    plan = state.get("question_plan") or []
    turns = state.get("turns") or []
    question = _pick_question(plan, turns, state.get("next_difficulty"))
    # next_difficulty 是一次性提示：用掉就清空，否则会一直影响后面所有选题
    return {"current_question": question, "next_difficulty": None}
