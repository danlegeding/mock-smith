"""报告侧：面试结束后的产出。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import Dimension


class Strength(BaseModel):
    """一条亮点。"""

    point: str = Field(min_length=1, description="一句话说明强在哪")
    evidence_quote: str = Field(min_length=1, description="支撑这个结论的候选人原话，逐字照抄")


class Weakness(BaseModel):
    """一条弱项。"""

    point: str = Field(min_length=1, description="一句话说明弱在哪")
    evidence_quote: str = Field(min_length=1, description="支撑这个结论的候选人原话，逐字照抄")
    suggestion: str = Field(default="", description="一条可执行的改进建议")


class ReportDraft(BaseModel):
    """报告里"由模型写"的那部分；均分和结论词由代码算，不在这里。"""

    overall: str = Field(min_length=1, description="一句话总体判断：是否建议推进 + 最主要原因")
    strengths: list[Strength] = Field(default_factory=list, max_length=3, description="亮点，最多 3 条")
    weaknesses: list[Weakness] = Field(default_factory=list, max_length=3, description="弱项，最多 3 条")
    gap_conclusion: str = Field(default="", description="对照 JD 缺口的结论，2-3 句")
    next_steps: list[str] = Field(
        min_length=3, max_length=3, description="正好 3 条可执行建议，按优先级排"
    )


class Report(BaseModel):
    """面试结束后的结构化报告。"""

    overall: str = Field(min_length=1, description="总体结论，一句话，明确说是否建议推进")
    dimension_summary: dict[Dimension, float] = Field(
        default_factory=dict, description="各维度均分，key 是维度英文值"
    )
    strengths: list[Strength] = Field(default_factory=list, description="亮点，必须引用候选人原话")
    weaknesses: list[Weakness] = Field(default_factory=list, description="弱项，必须引用原话并给建议")
    gap_conclusion: str = Field(default="", description="对照 JD 的缺口结论，2-3 句")
    next_steps: list[str] = Field(min_length=3, max_length=3, description="正好 3 条可执行建议，按优先级排")
