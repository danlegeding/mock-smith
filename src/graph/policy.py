"""面试流程的可调参数（policy）。"""

from __future__ import annotations

from src.model import Dimension

# 一场面试最多问几个问题（含追问；不含被跳过的）
MAX_TURNS = 6

# 同一个维度最多问几道主问题。超过就要换维度，避免一场面试全是技术深度
MAX_QUESTIONS_PER_DIM = 2

# 同一个维度被跳过几次就不再出题（用户说"不会"两回，再问就是为难人）
MAX_SKIPS_PER_DIM = 2


def counted_turns(turns: list[dict]) -> int:
    """计入 MAX_TURNS 的轮数：被跳过的那一轮不算。"""
    return sum(1 for turn in turns if not turn.get("skipped"))


def active_dimensions(resume_profile: dict) -> list[Dimension]:
    """这次面试该考哪些维度——由简历决定，不是常量。"""
    if resume_profile.get("projects"):
        return list(Dimension)
    return [dimension for dimension in Dimension if dimension is not Dimension.PROJECT_AUTHENTICITY]
