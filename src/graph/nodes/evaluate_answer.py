"""节点 6：evaluate_answer —— 用 agent 给一轮回答打分。

## 为什么这一层是 agent，而不是一次结构化调用

一次 `call_json(AnswerScore)` 也能出分数，但那样模型只能"凭印象"打分、凭印象编引文。
这里给了它两个工具：

- `get_rubric(dimension)`：去取这个维度的 1/3/5 分锚点 —— 分数要有据可依
- `verify_quote(quote)`：核对引文是否真的在回答原文里 —— 引文要有据可查

于是它必须自己规划：取锚点 → 试引文 → 被工具打回 → 换一段 → 再试 → 够了才给分。
**调几次工具、要不要重试，由模型根据回答质量自己决定**，这是代码预先写不出来的。

## 代码仍然负责的部分（别指望模型兜底）

1. 跳过的题不评分（省钱、也符合语义）
2. 只保留当前维度的分数（`get` 取当前维度，其余不读）
3. 出节点后用同一套规则**再核一遍**引文：模型说"核对过"不算数
4. 拿不到结构化结果时，记一个"无证据 1 分"，不让流程崩

第 3 条是这一层最关键的设计：agent 的自我审查能提高质量，但不能当作正确性保证。
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from src.graph.checks import quote_in_answer, verify_quote_detail
from src.graph.nodes.parse_inputs import render_prompt
from src.graph.rubrics import rubric_text
from src.graph.state import InterviewState, JDProfileDict, QuestionDict
from src.graph.trace import tool_callbacks
from src.llm import get_chat_model
from src.model import AnswerScore, Dimension, DimensionScore, DIMENSION_LABELS


def _render_user_message(question: QuestionDict, answer: str, jd: JDProfileDict) -> str:
    """拼给评分 agent 的用户消息：岗位、维度、题目、回答原文。"""
    dimension = Dimension(question["dimension"])
    return "\n".join(
        [
            f"岗位：{jd.get('role_title', '?')}（{jd.get('seniority', '?')}）",
            f"考察维度：{dimension.value}（{DIMENSION_LABELS[dimension]}）",
            f"题目难度：{question['difficulty']}（1 简单 / 2 中等 / 3 深入）",
            f"题目类型：{question['kind']}",
            f"问题：{question['text']}",
            "",
            "候选人回答原文（引文必须逐字来自下面这段）：",
            "<<<",
            answer,
            ">>>",
            "",
            f"请只评 {dimension.value} 这一个维度，按流程先 get_rubric 再 verify_quote。",
        ]
    )


def evaluate_answer(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：评这一轮，把分数写回 turns[-1]["score"]。"""
    turns = list(state.get("turns") or [])
    if not turns:
        return {}

    turn = turns[-1]
    question = turn["question"]
    dimension = Dimension(question["dimension"])

    if turn.get("skipped"):
        print("  [evaluate] 这一轮是跳过，不评分")
        return {}

    answer = turn["answer"]

    def get_rubric(dimension: str) -> str:
        """获取某个考察维度在 1 分 / 3 分 / 5 分上的可观察行为锚点。

        打分前先取锚点，把分数对齐到具体行为描述，而不是凭印象给分。

        Args:
            dimension: 维度的英文值，例如 "tech_depth"、"project_authenticity"。
                可用值见 Dimension 枚举；传错不报错，会返回可用维度列表。

        Returns:
            str: 三个分数档对应的行为描述；维度非法时返回错误提示字符串。
        """
        try:
            return rubric_text(Dimension(dimension))
        except ValueError:
            return f"未知维度 {dimension}，可用维度：{[d.value for d in Dimension]}"

    def verify_quote(quote: str) -> str:
        """核对一段引文是否逐字出现在候选人回答原文里（忽略标点与空白差异）。

        在把某句话写进 evidence_quote 之前必须调用。注意：出节点后系统会用同一套规则
        再复查一次，所以这里没核对通过的引文最终会被丢掉。

        Args:
            quote: 引文片段，必须来自候选人回答原文，建议至少 4 个字。

        Returns:
            str: 核对结果。命中时说明匹配位置；未命中时说明失败原因并提示重新截取。
        """
        return verify_quote_detail(quote, answer)

    agent = create_agent(
        model=get_chat_model(temperature=0),
        tools=[get_rubric, verify_quote],
        system_prompt=render_prompt("evaluate_answer.md"),
        response_format=AnswerScore,
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content=_render_user_message(question, answer, state.get("jd_profile", {})))]},
        config={"callbacks": tool_callbacks()},
    )
    score: AnswerScore | None = result.get("structured_response")

    if score is None:
        print("  [evaluate] 没拿到结构化评分，记一个无证据低分")
        score = AnswerScore(
            dimension_scores={
                dimension: DimensionScore(score=1, evidence_quote="", comment="本轮评分失败，无证据")
            }
        )

    # 一场只认一个维度：只取当前维度的评分，其余不管
    item = score.dimension_scores.get(dimension)

    # 确定性复检：模型说核对过不算数，这里按同一套规则再核一遍
    if item is not None and item.evidence_quote and not quote_in_answer(item.evidence_quote, answer):
        print(f"  [evaluate] 引文复检未通过，丢弃维度 {dimension.value}（模型声称核对过，但原文里没有）")
        item = None

    checked = AnswerScore(
        dimension_scores={} if item is None else {dimension: item},
        signals=score.signals,
    )
    # 拼一个新 dict 再替换，而不是 turn["score"] = ...：
    # turns 是浅拷贝，元素 dict 与 state 里是同一个对象，原地改会串改 state。
    turns[-1] = {**turn, "score": checked.model_dump(mode="json")}

    if item is None:
        print(f"  [evaluate] {DIMENSION_LABELS[dimension]}: 无有效评分（证据核验失败）")
    else:
        mark = "有效" if checked.valid else "无证据"
        print(
            f"  [evaluate] {DIMENSION_LABELS[dimension]}: {item.score} 分（{mark}）"
            f" avg={checked.avg:.1f}"
        )
    return {"turns": turns}
