"""评分侧：一轮回答的分数，以及"有没有证据"这个开关。"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from .enums import Dimension


class Signals(BaseModel):
    """从回答文本里抽出的客观信号，供 decide_next 用（只陈述，不判断好坏）。"""

    too_short: bool = Field(default=False, description="回答少于 15 字")
    off_topic: bool = Field(default=False, description="回答内容与问题无关")
    has_concrete_example: bool = Field(default=False, description="讲了具体做过的事，而不是'了解/用过'")
    has_numbers: bool = Field(default=False, description="回答里出现了数字（指标、量级、时间）")


class DimensionScore(BaseModel):
    """单个维度的得分。必须有证据，否则这个分数不可信。"""

    score: int = Field(ge=1, le=5, description="1 明显不足 / 3 达到实习水平 / 5 超出预期")
    evidence_quote: str = Field(
        default="",
        description="支撑这个分数的候选人原话，逐字照抄；找不到证据就留空（留空则该维度记无效）",
    )
    comment: str = Field(default="", description="一句话点评，说明为什么是这个分")


class AnswerScore(BaseModel):
    """一轮回答的评分。`valid` 和 `avg` 自动算，不要让模型或调用方传。"""

    dimension_scores: dict[Dimension, DimensionScore] = Field(
        description="维度 → 得分。key 必须是 Dimension 的英文值，禁止新造维度"
    )
    signals: Signals = Field(default_factory=Signals, description="客观信号")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def valid(self) -> bool:
        """所有已评维度都有非空 evidence_quote 才算有效。"""
        if not self.dimension_scores:
            return False
        return all((ds.evidence_quote or "").strip() for ds in self.dimension_scores.values())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avg(self) -> float:
        """已评维度的平均分；没评分时返回 0.0。"""
        if not self.dimension_scores:
            return 0.0
        return sum(ds.score for ds in self.dimension_scores.values()) / len(self.dimension_scores)
