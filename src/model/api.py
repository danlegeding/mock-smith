"""接口侧：FastAPI 的入参/出参（最后一周才接）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .question import Question
from .report import Report


class SessionCreate(BaseModel):
    """接口入参：开始一场面试。"""

    jd_text: str = Field(min_length=1, description="JD 原文")
    resume_text: str = Field(min_length=1, description="简历原文")


class SessionCreated(BaseModel):
    """接口出参：新建的 session。"""

    session_id: str = Field(description="会话 id，同时就是 LangGraph 的 thread_id")


class AnswerIn(BaseModel):
    """接口入参：回答一轮（skip 时 answer 留空）。"""

    session_id: str = Field(min_length=1, description="会话 id")
    answer: str = Field(default="", description="候选人回答；skip 时留空")


class TurnOut(BaseModel):
    """接口出参：一轮的结果——要么给下一题，要么给报告。"""

    session_id: str = Field(min_length=1, description="会话 id")
    type: Literal["question", "report"] = Field(description="question 表示还有下一题，report 表示面试结束")
    question: Question | None = Field(default=None, description="type=question 时给出")
    report: Report | None = Field(default=None, description="type=report 时给出")
    turn_index: int = Field(ge=0, description="当前是第几轮，从 0 开始")
