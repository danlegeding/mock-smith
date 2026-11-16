"""节点 2：match_gap —— 把「JD 要什么」和「简历有什么」逐条对上。"""

from __future__ import annotations

import re
from typing import Any

from src.graph.state import InterviewState, JDProfileDict, ResumeProfileDict
from src.model import GapItem, MatchLevel

# ---------------------------------------------------------------- 人工知识表
# 左边是 JD 要的技能（已经统一成小写），右边是"简历里有它就算沾边"的技术。
# 判错一条就往这里加一行 —— 这是整个文件里唯一需要人工维护的知识。
RELATED: dict[str, tuple[str, ...]] = {
    "postgresql": ("mysql", "sql", "postgres"),
    "langgraph": ("langchain",),
    "asyncprogramming": ("fastapi", "asyncio"),
    "异步编程": ("fastapi", "asyncio"),
    "rag": ("retrievalqa", "向量", "embedding", "向量库"),
    "docker": ("dockerfile", "container", "容器"),
    "向量检索": ("pgvector", "embedding", "向量库", "milvus"),
}

# 每个档位默认的追问方向。为什么不写进 prompt 让模型自己想：
# "该不该问"是产品决策，要固定、可复现，不能让模型每次临场发挥。
PROBE = {
    MatchLevel.STRONG: "让他讲选型和踩坑的具体细节，验证是不是真做过",
    MatchLevel.WEAK: "问相邻概念的差别（迁移/等价物），确认不是只会念工具名",
    MatchLevel.MISSING: "先探底：这块接触过吗？没接触过就跳过，别硬问",
}


def _normalize_skill_name(name: str) -> str:
    """把技能名统一成"同名同姓"的样子：全小写、去掉空格和横线。"""
    return name.strip().lower().replace(" ", "").replace("-", "")


def _build_resume_skill_index(resume_profile: ResumeProfileDict) -> dict[str, str]:
    """把简历里提到的技术收成一张查询表：{统一后的名字: 简历原文里的写法}。"""
    index: dict[str, str] = {}
    for skill in resume_profile.get("skills", []):
        index.setdefault(_normalize_skill_name(skill), skill)
    for project in resume_profile.get("projects", []):
        for tech in project.get("tech_stack", []):
            index.setdefault(_normalize_skill_name(tech), tech)
    return index


def _lookup_related_terms(skill_norm: str) -> tuple[str, ...]:
    """拿着 JD 要的技能名，去 RELATED 里找沾边的技术；找不到就给空元组。"""
    for key, terms in RELATED.items():
        if key in skill_norm or skill_norm in key:
            return terms
    return ()


def _find_original_evidence(text: str, candidate: str) -> str:
    """回到简历原文里找出 candidate 的真实写法，返回那一段原文；找不到就返回空字符串。"""
    if not text or not candidate:
        return ""
    if candidate in text:
        return candidate
    pattern = r"\s*".join(re.escape(ch) for ch in candidate if not ch.isspace())
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _judge_match_level(skill: str, index: dict[str, str], text: str = "") -> tuple[MatchLevel, str]:
    """给 JD 的一条要求判档，返回 (档位, 证据)。"""

    target = _normalize_skill_name(skill)

    # ① strong：简历里直接有这个东西（允许 "Postgres" 和 "PostgreSQL" 这种长短差异）
    for name, evidence in index.items():
        if name in target or target in name:
            real = _find_original_evidence(text, evidence)
            if real:
                return MatchLevel.STRONG, real

    # ② weak：这个名字简历里没有，但有沾边的技术
    #    先查查询表（结构化字段里明确的），再查简历原文（项目描述里顺带提的）
    for term in _lookup_related_terms(target):
        if term in index:
            real = _find_original_evidence(text, index[term])
            if real:
                return MatchLevel.WEAK, real
        real = _find_original_evidence(text, term)
        if real:
            return MatchLevel.WEAK, real

    # ③ missing：一个证据都找不到。按规矩，这时候证据必须是空字符串
    return MatchLevel.MISSING, ""


def _weight_to_priority(weight: int, *, is_must: bool) -> int:
    """把 JD 里的权重（1-5）换成"该不该问"的优先级（1-5）。"""
    base = max(1, min(5, int(weight)))
    return base if is_must else max(1, base - 2)


def build_gap_map(
    jd_profile: JDProfileDict,
    resume_profile: ResumeProfileDict,
    resume_text: str = "",
) -> list[GapItem]:
    """把 JD 的必修项、加分项逐条跑一遍，拼出完整的缺口清单。"""
    index = _build_resume_skill_index(resume_profile)
    gaps: dict[str, GapItem] = {}

    # 必修项、加分项各跑一遍。同一个技能两边都出现时，以先跑的必修项为准
    for key, is_must in (("must_skills", True), ("nice_skills", False)):
        for item in jd_profile.get(key, []):
            skill = item["name"]
            norm = _normalize_skill_name(skill)
            if norm in gaps:
                continue
            level, evidence = _judge_match_level(skill, index, resume_text)
            gaps[norm] = GapItem(
                skill=skill,
                match_level=level,
                evidence=evidence,
                priority=_weight_to_priority(item.get("weight", 3), is_must=is_must),
                probe_angle=PROBE[level],
            )

    # 优先级高的排前面；优先级相同时保持 JD 原文顺序（sorted 遇到平手不会打乱原顺序）
    return sorted(gaps.values(), key=lambda gap: gap.priority, reverse=True)


def match_gap(state: InterviewState) -> dict[str, Any]:
    """LangGraph 的节点函数：进一个字典，出一个字典，里面只放"要更新的字段"。"""
    gaps = build_gap_map(
        state["jd_profile"],
        state["resume_profile"],
        state.get("resume_text", ""),
    )
    return {"gap_map": [gap.model_dump(mode="json") for gap in gaps]}
