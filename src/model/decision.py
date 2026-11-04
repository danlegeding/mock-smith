"""决策侧：decide_next 的产出——下一步干什么、为什么、追问什么。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .enums import DecideAction
from .question import Question, QuestionKind


class Decision(BaseModel):
    """decide_next 的决策结果。

    `reason` 是必填的：一个说不出理由的决策，考核时没法辩护，
    面试官（和评测）也没法判断它是不是碰巧蒙对的。
    """

    action: DecideAction = Field(description="下一步动作：next / deepen / raise_difficulty / lower_difficulty / switch_dim / end")
    reason: str = Field(min_length=4, description="一句话说明为什么这么决定，必须引用具体依据（分数、信号、已问轮数）")
    followup: Question | None = Field(
        default=None,
        description="action=deepen 时必填：针对刚说完的那句话的追问（kind=followup，anchor_quote 逐字引用原话）",
    )

    @model_validator(mode="after")
    def _deepen_needs_followup(self) -> Decision:
        """要深挖就必须给出具体追问，不能只说「我想追问」。"""
        if self.action == DecideAction.DEEPEN:
            if self.followup is None:
                raise ValueError("action=deepen 时必须给 followup（具体的追问）")
            if self.followup.kind != QuestionKind.FOLLOWUP:
                raise ValueError("action=deepen 时 followup.kind 必须是 followup")
        if self.action != DecideAction.DEEPEN and self.followup is not None:
            raise ValueError("只有 action=deepen 时才允许带 followup")
        return self
