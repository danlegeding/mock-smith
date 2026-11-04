"""一轮问答：把「问题 + 回答 + 评分」绑在一起，作为 state.turns 的元素。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .question import Question
from .score import AnswerScore


class Turn(BaseModel):
    """一问一答（skipped=True 表示跳过了这题，此时 score 为 None）。"""

    question: Question
    answer: str = Field(default="", description="候选人的回答原文；跳过时留空")
    score: AnswerScore | None = Field(default=None, description="跳过时为 None")
    skipped: bool = Field(default=False, description="用户是否跳过了这道题")
