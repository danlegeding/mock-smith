"""节点 7：decide_next —— 用 agent 决定下一步（整个项目里"自主规划"体现得最重的一层）。

## 和之前写死规则的区别

最初的设计是 6 条 if-else：轮数到顶 → 结束；答得空 → 降难度；答得好 → 追问……
问题是这些规则本身写死了"什么算好"。这一版把判断交给 agent，给它三个工具去**查清现状**：

- `coverage()`：每个维度问了几题、跳过几次、轮数用了多少
- `remaining_questions()`：题池里还剩哪些题
- `score_summary()`：每个维度当前平均分、有没有有效证据

agent 自己组合这些信息决定动作，并给出理由。它可以在"技术深度已有 4 分、还剩两条 missing 题、
已经 4 轮"这种局面里做出人一样的取舍——而这种组合状态空间是穷举不完的。

## 代码仍然握着的四条硬线（agent 不得越过）

1. 轮数到 `MAX_TURNS` 必须结束（不看 agent 意见）；跳过的不计入轮数
2. `deepen` 的 anchor_quote 必须逐字出现在上一轮回答里，否则降级成普通提问
3. 动作非法/拿不到结构化结果 → 退回 `next`（按题池顺序走），不让流程崩
4. 还有维度一次都没问过时不许 `end`（覆盖度由代码算，不信 agent 的「都齐了」）

这三点是"agent 做决策"和"系统能收场"之间的分界：**策略交给模型，兜底留给代码。**
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from src.graph.checks import quote_in_answer, strip_internal_ids
from src.graph.nodes.parse_inputs import render_prompt
from src.graph.policy import MAX_TURNS, active_dimensions, counted_turns
from src.graph.state import InterviewState, QuestionDict, TurnDict
from src.graph.trace import tool_callbacks
from src.llm import get_chat_model
from src.log import get_logger
from src.model import Dimension, DIMENSION_LABELS, Decision, DecideAction

logger = get_logger(__name__)


def _format_turn_history(turns: list[TurnDict]) -> str:
    """把已问的轮次压成几行文本，给决策 agent 看。"""
    lines: list[str] = []
    for i, turn in enumerate(turns, 1):
        question = turn["question"]
        label = DIMENSION_LABELS[Dimension(question["dimension"])]
        if turn.get("skipped"):
            lines.append(f"第{i}轮 [{label}] 难度{question['difficulty']} 跳过（回答『不太了解』）")
            continue
        score = turn.get("score") or {}
        parts = score.get("dimension_scores") or {}
        item = next(iter(parts.values()), None)
        if not item:
            lines.append(f"第{i}轮 [{label}] 难度{question['difficulty']} 回答={turn['answer'][:40]}… 无有效评分")
            continue
        mark = "有证据" if item.get("evidence_quote") else "无证据"
        lines.append(
            f"第{i}轮 [{label}] 难度{question['difficulty']} 得分 {item['score']}（{mark}）"
            f" 回答={turn['answer'][:40]}…"
        )
    return "\n".join(lines) or "（还没有问答）"


def decide_next_action(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：产出 decision（下一步动作 + 理由），并决定下一题是不是追问。"""
    turns = list(state.get("turns") or [])
    plan = list(state.get("question_plan") or [])
    jd = state.get("jd_profile", {})

    def coverage() -> str:
        """汇总当前面试进度：每个维度问了几题、跳过几次，以及已用轮数与轮数上限。

        决策前先调用，避免在某个维度反复打转，或漏掉一次都没问过的维度。

        Args:
            无。进度直接读当前会话状态，不需要传参数。

        Returns:
            str: 多行文本。首行为「已用轮数 x/上限」，其后每个维度一行，
            格式为「维度中文名(英文值) 问N题 跳过M次」。
        """
        asked: dict[str, int] = {}
        skipped: dict[str, int] = {}
        for turn in turns:
            key = turn["question"]["dimension"]
            asked[key] = asked.get(key, 0) + 1
            if turn.get("skipped"):
                skipped[key] = skipped.get(key, 0) + 1
        rows = [
            f"{DIMENSION_LABELS[d]}({d.value}) 问{asked.get(d.value, 0)}题 跳过{skipped.get(d.value, 0)}次"
            for d in active_dimensions(state.get("resume_profile") or {})
        ]
        skipped_total = sum(1 for turn in turns if turn.get("skipped"))
        head = f"已用轮数 {counted_turns(turns)}/{MAX_TURNS}"
        if skipped_total:
            head += f"（另有 {skipped_total} 题跳过，不计入轮数）"
        return head + "\n" + "\n".join(rows)

    def remaining_questions() -> str:
        """列出题池里还剩哪些题（尚未问过的），最多返回 8 条。

        用来确认还有哪些维度、哪些难度的题可用，避免重复问同一题或挑到不存在的题。

        Args:
            无。题池和已问记录都从当前会话状态读取。

        Returns:
            str: 剩余题目的多行清单，每行为「- [维度中文名] 难度N 题干」；
            题池已空时返回「题池已空，没有未问过的题」。
        """
        asked_texts = {turn["question"]["text"] for turn in turns}
        left = [q for q in plan if q["text"] not in asked_texts]
        if not left:
            return "题池已空，没有未问过的题"
        rows = [
            f"- [{DIMENSION_LABELS[Dimension(q['dimension'])]}] 难度{q['difficulty']} {q['text']}"
            for q in left[:8]
        ]
        return f"还剩 {len(left)} 题：\n" + "\n".join(rows)

    def score_summary() -> str:
        """按维度汇总当前平均分，并说明该维度的分数是否都有证据支撑。

        Args:
            无。评分从当前会话的 turns 里统计。

        Returns:
            str: 每个已评分维度一行，格式为「维度中文名: 平均X.X，证据齐全/有缺失」；
            还没有任何评分时返回「还没有任何评分」。
        """
        buckets: dict[str, list[tuple[int, bool]]] = {}
        for turn in turns:
            parts = (turn.get("score") or {}).get("dimension_scores") or {}
            for key, item in parts.items():
                buckets.setdefault(key, []).append((item["score"], bool(item.get("evidence_quote"))))
        if not buckets:
            return "还没有任何评分"
        rows = []
        for key, items in buckets.items():
            avg = sum(score for score, _ in items) / len(items)
            valid = all(ok for _, ok in items)
            rows.append(f"{DIMENSION_LABELS[Dimension(key)]}: 平均{avg:.1f}，证据{'齐全' if valid else '有缺失'}")
        return "\n".join(rows)

    agent = create_agent(
        model=get_chat_model(temperature=0),
        tools=[coverage, remaining_questions, score_summary],
        system_prompt=render_prompt("decide_next.md"),
        response_format=Decision,
    )
    used = counted_turns(turns)
    user = "\n".join(
        [
            f"岗位：{jd.get('role_title', '?')}（{jd.get('seniority', '?')}）",
            f"已用轮数：{used}/{MAX_TURNS}（跳过的不计入）",
            "",
            "## 已问答记录",
            _format_turn_history(turns),
            "",
            "请先查工具再决定下一步动作。",
        ]
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content=user)]},
        config={"callbacks": tool_callbacks()},
    )
    decision: Decision | None = result.get("structured_response")

    if decision is None:
        decision = Decision(action=DecideAction.NEXT, reason="没拿到结构化决策，按题池顺序继续")
        logger.info("  [decide] 没拿到结构化决策 → 退回 next")

    # 硬线 1：轮数到顶，必须结束（agent 说什么都不算）。跳过的不计轮数。
    if used >= MAX_TURNS and decision.action != DecideAction.END:
        decision = Decision(
            action=DecideAction.END,
            reason=f"已问满 {MAX_TURNS} 轮，强制结束（agent 原本想 {decision.action.value}）",
        )

    # 硬线 4：还有维度一次没问过就不许结束（轮数满了除外）。
    # d7-agent-3 实测：沟通表达 0 题，agent 给了 end，理由还写成「各维度齐全」——
    # 模型会给出听起来合理、事实错误的理由，所以覆盖度必须由代码算，不能信它的说法。
    if decision.action == DecideAction.END and used < MAX_TURNS:
        asked_dims = {turn["question"]["dimension"] for turn in turns}
        asked_texts = {turn["question"]["text"] for turn in turns}
        uncovered = [
            d.value
            for d in active_dimensions(state.get("resume_profile") or {})
            if d.value not in asked_dims
            and any(q["dimension"] == d.value and q["text"] not in asked_texts for q in plan)
        ]
        if uncovered:
            names = "、".join(DIMENSION_LABELS[Dimension(d)] for d in uncovered)
            logger.info("  [decide] 拦截提前结束：%s 还没问到 → 改为继续", names)
            decision = Decision(
                action=DecideAction.NEXT,
                reason=f"还没覆盖到的维度：{names}，覆盖不全不能结束 → 先补覆盖率",
            )

    current_question: QuestionDict | None = None
    next_difficulty: int | None = None

    if decision.action == DecideAction.DEEPEN and decision.followup is not None:
        last_answer = turns[-1]["answer"] if turns else ""
        anchor = decision.followup.anchor_quote or ""
        # 追问文本是模型自己写的，同样可能把内部 id（p1/s2）念进去 —— 出题节点清洗过，
        # 这条路径必须再洗一遍，否则「p1 那个项目里…」会直接怼到候选人脸上。
        followup_text = strip_internal_ids(decision.followup.text)
        # 硬线 2：追问必须真的引用上一轮原话，否则降级
        if quote_in_answer(anchor, last_answer) and len(followup_text) >= 2:
            followup = decision.followup.model_copy(update={"text": followup_text})
            current_question = followup.model_dump(mode="json")
        else:
            decision = Decision(
                action=DecideAction.NEXT,
                reason=f"追问引文不合法（原文没有『{anchor[:20]}』）→ 降级为按顺序问下一题",
            )
            logger.info("  [decide] 追问的 anchor_quote 不在上一轮回答里 → 降级为 next")

    if decision.action == DecideAction.RAISE_DIFFICULTY:
        next_difficulty = 3
    elif decision.action == DecideAction.LOWER_DIFFICULTY:
        next_difficulty = 1

    logger.info("  [decide] %s：%s", decision.action.value, decision.reason)

    return {
        "decision": decision.model_dump(mode="json"),
        "current_question": current_question,
        "next_difficulty": next_difficulty,
    }
