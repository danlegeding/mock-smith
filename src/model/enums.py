"""枚举与常量：全项目的"词表"。"""

from __future__ import annotations

from enum import Enum


class Seniority(str, Enum):
    """岗位级别，影响出题难度基线。"""

    INTERN = "intern"  # 实习
    CAMPUS = "campus"  # 校招
    SOCIAL = "social"  # 社招


class MatchLevel(str, Enum):
    """简历与某项要求的匹配程度。"""

    STRONG = "strong"
    WEAK = "weak"
    MISSING = "missing"


class Dimension(str, Enum):
    """5 个考察维度。评分、覆盖度、报告全按这套 key 走。"""

    TECH_DEPTH = "tech_depth"  # 技术深度
    PROJECT_AUTHENTICITY = "project_authenticity"  # 项目真实性
    ENGINEERING_THINKING = "engineering_thinking"  # 工程思维
    COMMUNICATION = "communication"  # 沟通表达
    JOB_MATCH = "job_match"  # 岗位匹配


class QuestionKind(str, Enum):
    """问题类型。注意这里只描述「题从哪来」，不描述「问得深不深」。"""

    OPENING = "opening"  # 主问题（来自题池）
    FOLLOWUP = "followup"  # 基于上一轮回答的追问（必须引原话）
    SCENARIO = "scenario"  # 情景题


class DecideAction(str, Enum):
    """decide_next 的输出：下一步干什么。规则表见 DESIGN.md §3。"""

    NEXT = "next"  # 按计划问下一题
    DEEPEN = "deepen"  # 答得好 → 追问同一个点
    RAISE_DIFFICULTY = "raise_difficulty"  # 答得好且维度已覆盖 → 升难度
    LOWER_DIFFICULTY = "lower_difficulty"  # 答得空 → 降难度/换角度
    SWITCH_DIM = "switch_dim"  # 换一个维度问
    END = "end"  # 结束，出报告


#: 五个维度的中文名（写报告、拼 prompt 时用）。
DIMENSION_LABELS: dict[Dimension, str] = {
    Dimension.TECH_DEPTH: "技术深度",
    Dimension.PROJECT_AUTHENTICITY: "项目真实性",
    Dimension.ENGINEERING_THINKING: "工程思维",
    Dimension.COMMUNICATION: "沟通表达",
    Dimension.JOB_MATCH: "岗位匹配",
}

#: 覆盖度统计要遍历的维度列表。
DIMENSIONS: list[Dimension] = list(Dimension)
