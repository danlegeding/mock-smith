"""全项目的数据契约（Pydantic 模型），按用途拆成子模块。"""

from __future__ import annotations

from .api import AnswerIn, PdfUploadOut, SessionCreate, SessionCreated, TurnOut
from .decision import Decision
from .enums import (
    DIMENSIONS,
    DIMENSION_LABELS,
    DecideAction,
    Dimension,
    MatchLevel,
    QuestionKind,
    Seniority,
)
from .gap import GapItem
from .gold import LEVEL_TO_SCORE, GoldItem, QualityLevel
from .profile import ExperienceItem, JDProfile, ProjectItem, ResumeProfile, SkillItem
from .question import Question, QuestionPlan
from .report import Report, ReportDraft, Strength, Weakness
from .score import AnswerScore, DimensionScore, Signals
from .turn import Turn

__all__ = [
    # enums
    "Seniority",
    "MatchLevel",
    "Dimension",
    "QuestionKind",
    "DecideAction",
    "DIMENSIONS",
    "DIMENSION_LABELS",
    # profile
    "SkillItem",
    "ProjectItem",
    "ExperienceItem",
    "JDProfile",
    "ResumeProfile",
    # gap
    "GapItem",
    # gold
    "GoldItem",
    "QualityLevel",
    "LEVEL_TO_SCORE",
    # question
    "Question",
    "QuestionPlan",
    # decision
    "Decision",
    # score
    "Signals",
    "DimensionScore",
    "AnswerScore",
    # turn
    "Turn",
    # report
    "Strength",
    "Weakness",
    "Report",
    "ReportDraft",
    # api
    "SessionCreate",
    "SessionCreated",
    "AnswerIn",
    "TurnOut",
    "PdfUploadOut",
]



