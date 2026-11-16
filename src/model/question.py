"""出题侧：一道面试题长什么样，以及它的硬约束。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .enums import Dimension, QuestionKind


class Question(BaseModel):
    """一道面试题。"""

    text: str = Field(min_length=2, max_length=60, description="问题文本，≤60 字，口语化，一次只问一件事")
    dimension: Dimension = Field(description="这道题主要考察哪个维度")
    difficulty: int = Field(default=2, ge=1, le=3, description="难度：1 简单 / 2 中等 / 3 深入")
    evidence_ref: str = Field(min_length=1, description="问题依据的 JD 技能 id 或简历条目 id，如 s1 / p2")
    anchor_quote: str | None = Field(
        default=None,
        description="kind=followup 时必填：上一轮回答里被追问的原话片段，必须逐字照抄",
    )
    kind: QuestionKind = Field(
        default=QuestionKind.OPENING,
        description="opening 主问题 / followup 追问（必须带 anchor_quote）/ scenario 情景题",
    )

    @model_validator(mode="after")
    def _followup_must_anchor(self) -> Question:
        """追问必须能指回上一轮回答的原话——这是"没在瞎问"的唯一证据。"""
        if self.kind == QuestionKind.FOLLOWUP and not (self.anchor_quote or "").strip():
            raise ValueError("kind=followup 时必须填 anchor_quote：引用上一轮回答里被追问的原话")
        return self


class QuestionPlan(BaseModel):
    """题池：plan_questions 节点的产出。"""

    questions: list[Question] = Field(min_length=1, description="题目池，按建议提问顺序排")
