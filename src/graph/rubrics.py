"""5 个维度的行为锚点（rubric）。"""

from __future__ import annotations

from src.model import Dimension

#: 维度 → 1 分 / 3 分 / 5 分的可观察行为（2、4 分取中间）
RUBRICS: dict[Dimension, dict[int, str]] = {
    Dimension.TECH_DEPTH: {
        1: "只会说「了解/用过」，说不出怎么做的，也答不出边界",
        3: "能说清做了什么、用了什么技术，但取舍理由和边界条件要靠追问才出来",
        5: "能讲清实现方式、为什么这么选、遇到过什么坑、边界在哪",
    },
    Dimension.PROJECT_AUTHENTICITY: {
        1: "全是套话（「负责开发」「参与设计」），说不清自己具体做了哪块",
        3: "能说清自己负责的部分，但细节像背的，追问一层就模糊",
        5: "有具体场景、数字、卡点，追问细节不崩，能复述当时的判断过程",
    },
    Dimension.ENGINEERING_THINKING: {
        1: "只回答「能做」，不考虑失败、性能、验证",
        3: "能说出基本步骤，但缺异常处理、性能边界、怎么验证对不对",
        5: "主动提约束、失败模式、如何验证，能说清 trade-off",
    },
    Dimension.COMMUNICATION: {
        1: "答非所问，或者一句话带过、完全没展开",
        3: "听懂了问题、答在点上，但结构松散、重点靠听者自己找",
        5: "结论先行、分点清楚、长度合适，听一遍就懂",
    },
    Dimension.JOB_MATCH: {
        1: "岗位核心要求基本没接触过",
        3: "部分要求有对应经验，关键要求缺",
        5: "大部分要求都有直接经验，且能说清和岗位场景怎么结合",
    },
}


def rubric_text(dimension: Dimension) -> str:
    """把某个维度的锚点拼成给模型看的文本。"""
    anchors = RUBRICS[dimension]
    lines = [f"维度 {dimension.value} 的评分锚点："]
    for score in sorted(anchors):
        lines.append(f"- {score} 分：{anchors[score]}")
    lines.append("- 2 分、4 分：取相邻两档的中间水平")
    return "\n".join(lines)
