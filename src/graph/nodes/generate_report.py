"""节点 8：generate_report —— 面试结束后的收口，产出最终报告。"""

from __future__ import annotations

from typing import Any

from src.graph.checks import normalize, quote_in_answer
from src.graph.nodes.parse_inputs import render_prompt
from src.graph.state import GapItemDict, InterviewState, TurnDict
from src.llm import call_json
from src.log import get_logger
from src.model import DIMENSION_LABELS, Dimension, Report, ReportDraft

logger = get_logger(__name__)

MAX_ITEMS = 3  # 亮点 / 弱项各最多 3 条


def _dimension_averages(turns: list[TurnDict]) -> dict[str, float]:
    """按维度算均分（只统计评过分的轮次，跳过和未评不计入）。"""
    buckets: dict[str, list[int]] = {}
    for turn in turns:
        for key, item in ((turn.get("score") or {}).get("dimension_scores") or {}).items():
            buckets.setdefault(key, []).append(int(item["score"]))
    return {key: round(sum(scores) / len(scores), 1) for key, scores in buckets.items()}


def _verdict(averages: dict[str, float]) -> str:
    """推进结论：固定口径，模型只负责润色理由。"""
    if not averages:
        return "不建议推进"
    if min(averages.values()) >= 3.0 and max(averages.values()) >= 4.0:
        return "建议推进"
    if max(averages.values()) >= 3.0:
        return "谨慎推进"
    return "不建议推进"


VERDICTS = ("建议推进", "谨慎推进", "不建议推进")


def _with_verdict(verdict: str, text: str) -> str:
    """把代码算出的结论拼到开头；模型自己已经写了结论词就不重复拼。"""
    body = text.strip().lstrip("：:，,。 ")
    for word in VERDICTS:
        if body.startswith(word):
            return body
    return f"{verdict}：{body}"


def _answered_texts(turns: list[TurnDict]) -> list[str]:
    """所有非跳过轮次的回答原文，供引文核对用。"""
    return [turn["answer"] for turn in turns if not turn.get("skipped") and turn.get("answer")]


def _keep_quoted(items: list[Any], answers: list[str]) -> list[Any]:
    """只留下 evidence_quote 能在回答里逐字找到的条目。"""
    kept: list[Any] = []
    for item in items:
        quote: str = item.evidence_quote or ""
        if len(normalize(quote)) < 4:
            continue
        if any(quote_in_answer(quote, answer) for answer in answers):
            kept.append(item)
    return kept[:MAX_ITEMS]


def _render_gap_table(gap_map: list[GapItemDict]) -> str:
    """缺口表压成几行，让模型知道"岗位要什么、候选人缺什么"。"""
    if not gap_map:
        return "（没有缺口分析结果）"
    rows = []
    for gap in gap_map:
        level = gap.get("match_level", "?")
        if level == "strong":
            continue
        evidence = gap.get("evidence") or "无"
        rows.append(
            f"- {gap.get('skill', '?')}：{level}（优先级 {gap.get('priority', '?')}）证据：{evidence[:40]}"
        )
    return "\n".join(rows) or "（缺口表里没有 weak/missing 项）"


def _render_history(turns: list[TurnDict]) -> str:
    """问答记录，模型写报告的唯一素材。"""
    lines: list[str] = []
    for i, turn in enumerate(turns, 1):
        question = turn["question"]
        label = DIMENSION_LABELS[Dimension(question["dimension"])]
        if turn.get("skipped"):
            lines.append(f"第{i}轮 [{label}] 问：{question['text']}\n  答：（跳过）")
            continue
        parts = ((turn.get("score") or {}).get("dimension_scores") or {}).values()
        item = next(iter(parts), None)
        mark = f"{item['score']}分" if item else "未评"
        lines.append(f"第{i}轮 [{label}] 问：{question['text']}\n  答：{turn['answer']}\n  （评分 {mark}）")
    return "\n\n".join(lines) or "（没有问答记录）"


def _render_averages(averages: dict[str, float]) -> str:
    """维度均分，给模型写 overall / gap_conclusion 时参考。"""
    if not averages:
        return "（还没有任何有效评分）"
    return "\n".join(f"- {DIMENSION_LABELS[Dimension(key)]}: {score}" for key, score in averages.items())


def generate_report(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：把整场面试收成一份 Report，写进 state.report。"""
    if state.get("report"):
        return {}  # 已经生成过，续跑时不要重写

    turns = list(state.get("turns") or [])
    gap_map = list(state.get("gap_map") or [])
    jd = state.get("jd_profile", {})
    averages = _dimension_averages(turns)
    verdict = _verdict(averages)
    answers = _answered_texts(turns)

    user = "\n".join(
        [
            f"岗位：{jd.get('role_title', '?')}（{jd.get('seniority', '?')}）",
            "",
            "## 维度均分（代码统计，直接引用）",
            _render_averages(averages),
            "",
            "## JD 缺口（只列 weak / missing）",
            _render_gap_table(gap_map),
            "",
            "## 问答记录（写报告的唯一素材）",
            _render_history(turns),
            "",
            f"请注意：代码算出的结论是「{verdict}」，overall 要与之保持一致。",
        ]
    )
    draft: ReportDraft = call_json(
        ReportDraft,
        system=render_prompt("generate_report.md"),
        user=user,
        retries=2,
    )

    # 硬线 1：引文逐字核对，对不上的条目直接丢弃（宁可少写，不写假的）
    strengths = _keep_quoted(draft.strengths, answers)
    weaknesses = _keep_quoted(draft.weaknesses, answers)
    if draft.strengths and not strengths:
        logger.info("  [report] %d 条亮点引文核对失败，已丢弃", len(draft.strengths))
    if not answers:
        strengths = []

    # 硬线 2：均分与结论由代码定，模型只润色理由
    overall = _with_verdict(verdict, draft.overall)
    gap_conclusion = draft.gap_conclusion or _fallback_gap_conclusion(gap_map)

    report = Report(
        overall=overall,
        dimension_summary=averages,
        strengths=strengths,
        weaknesses=weaknesses,
        gap_conclusion=gap_conclusion,
        next_steps=draft.next_steps,
    )

    logger.info("  [report] %s；亮点 %d 条，弱项 %d 条", verdict, len(strengths), len(weaknesses))
    return {"report": report.model_dump(mode="json")}


def _fallback_gap_conclusion(gap_map: list[GapItemDict]) -> str:
    """模型没给缺口结论时，用缺口表兜一句，避免整份报告缺这块。"""
    missing = [gap["skill"] for gap in gap_map if gap.get("match_level") == "missing"]
    weak = [gap["skill"] for gap in gap_map if gap.get("match_level") == "weak"]
    parts = []
    if missing:
        parts.append(f"完全没提到的要求：{'、'.join(missing[:4])}")
    if weak:
        parts.append(f"只是沾边的要求：{'、'.join(weak[:4])}")
    return "；".join(parts) + "。" if parts else "岗位要求与现有经历的差距不大。"
