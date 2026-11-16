"""评测侧：gold 集——人工标注的「标准答案」，用来检验 AI 评分准不准。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, computed_field

from .enums import Dimension

# 人工档位 → rubric 分数锚点（1/3/5）。改这个映射就等于改评测口径，别随手改。
QualityLevel = Literal["bad", "ok", "good"]

LEVEL_TO_SCORE: dict[str, float] = {"bad": 1.0, "ok": 3.0, "good": 5.0}


class GoldItem(BaseModel):
    """一条 gold 记录 = 一道题 + 一段回答 + 人工给出的档位与证据。"""

    schema_version: int = Field(default=1, ge=1, description="格式版本；以后加字段时靠它做兼容")
    question_id: str = Field(
        min_length=6,
        pattern=r"^gold_\d{3}$",
        description="唯一编号，必须和文件名一致，如 gold_001.yaml → gold_001",
    )
    question_text: str = Field(min_length=8, description="题目原文（面试官问的那句话）")
    scoring_dimension: Dimension = Field(
        description="这道题考哪个维度；必须是 Dimension 的英文值，禁止新造维度"
    )
    question_difficulty: int = Field(default=2, ge=1, le=3, description="题目难度：1 入门 / 2 常规 / 3 挑战")
    candidate_answer: str = Field(
        min_length=20, description="候选人回答原文。人工标注时不要润色——评测要的就是真实水平"
    )
    human_quality_level: QualityLevel = Field(
        description="人工档位：bad 明显不足 / ok 达到实习水平 / good 超出预期"
    )
    human_evidence_quote: str = Field(
        default="",
        description="人工挑出的、支撑这个档位的原话（从 candidate_answer 里逐字照抄）",
    )
    annotation_note: str = Field(default="", description="为什么标这一档，一句话说清")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def human_score(self) -> float:
        """档位对应的 1/3/5 分。评测时拿它和模型分比。"""
        return LEVEL_TO_SCORE[self.human_quality_level]


def load_gold_item(path: Path) -> GoldItem:
    """读一个 yaml 文件并校验。文件名和 question_id 不一致也算错（防止复制粘贴忘了改）。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: 顶层必须是 key: value 映射，实际读到 {type(raw).__name__}")

    item = GoldItem.model_validate(raw)
    if item.question_id != path.stem:
        raise ValueError(
            f"{path.name}: question_id={item.question_id!r} 必须等于文件名 {path.stem!r}"
        )
    return item


def load_gold_set(gold_dir: Path) -> list[GoldItem]:
    """读整个 gold 目录（按文件名排序，结果稳定、方便对比两次评测）。"""
    files = sorted(gold_dir.glob("*.yaml"))
    if not files:
        raise FileNotFoundError(f"{gold_dir} 下没有 *.yaml —— gold 集还没开始标？")
    return [load_gold_item(path) for path in files]
