"""缺口分析侧：match_gap 节点的产出。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import MatchLevel


class GapItem(BaseModel):
    """一条「JD 要求 vs 简历」的比对结果。"""

    skill: str = Field(min_length=1, description="JD 里的哪一项要求（技能名）")
    match_level: MatchLevel = Field(description="strong 有且对得上 / weak 沾边 / missing 完全没提")
    evidence: str = Field(
        default="",
        description="从简历里逐字复制的原文片段；简历没提就留空，不许编",
    )
    priority: int = Field(ge=1, le=5, description="该问的优先级 1-5，越高越该问")
    probe_angle: str = Field(default="", description="建议的考察角度，如'让他讲一致性方案'")
