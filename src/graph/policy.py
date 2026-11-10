"""面试流程的可调参数（policy）。

为什么单独放一个文件：这些数字是"产品决策"，不是"代码实现"。
面试官问"为什么是 6 轮不是 8 轮"，答案应该在这里能改，而不是埋在某个节点里。
以后做消融实验（改 MAX_TURNS 看报告质量），也是改这里。
"""

from __future__ import annotations

from src.model import Dimension

# 一场面试最多问几个问题（含追问；不含被跳过的）
MAX_TURNS = 6

# 同一个维度最多问几道主问题。超过就要换维度，避免一场面试全是技术深度
MAX_QUESTIONS_PER_DIM = 2

# 同一个维度被跳过几次就不再出题（用户说"不会"两回，再问就是为难人）
MAX_SKIPS_PER_DIM = 2


def active_dimensions(resume_profile: dict) -> list[Dimension]:
    """这次面试该考哪些维度——由简历决定，不是常量。

    没有项目就不考「项目真实性」：既没有素材，硬问只能问出"你做过什么"这种空题，
    还可能诱导模型编一个项目出来。少考一个维度，报告里就少一栏，如实反映"没考"。
    """
    if resume_profile.get("projects"):
        return list(Dimension)
    return [dimension for dimension in Dimension if dimension is not Dimension.PROJECT_AUTHENTICITY]
