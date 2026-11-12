"""节点 2：match_gap —— 把「JD 要什么」和「简历有什么」逐条对上。

这是全项目第一个**不调大模型**的节点。输入已经是两份整理好的资料（profile），
"简历里写没写 Docker"就是个查表问题，用普通代码判就行——省钱、稳定、能写测试。
只有"相邻技术算不算沾边"这种说不清的地方，才需要一张人工维护的表（RELATED）。

## 判档标准（从上往下判，中了就停）

| 档位 | 什么情况 | 例子 |
|---|---|---|
| `strong` | 简历里有同一个东西 | JD 要 Docker，简历写了 Docker |
| `weak` | 没有同一个，但有沾边的 | 要 PostgreSQL，简历只有 MySQL |
| `missing` | 连沾边的都没有 → 证据必须是空字符串 | 要异步编程，简历一个字没提 |

档位为什么重要：它决定下一个节点**怎么问**。

- `strong`  → 往深里问："你们的一致性怎么保证的？"
- `weak`    → 换个问法："MySQL 和 PostgreSQL 的索引差别你了解吗？"
- `missing` → 先探底："这块接触过吗？"没接触过就别硬问

## 读这个文件之前

先认识三处 Python 写法（后面会反复出现）：

- `dict[str, str]` —— 一个字典：键是字符串，值也是字符串。
  例：`{"mysql": "MySQL 基础"}`，左边是统一过的名字，右边是简历原文的写法。
- `tuple[str, ...]` —— 一个元组，里面可以放任意多个字符串，比如 `("mysql", "sql")`。
- `x: str = ""` —— 参数默认值是空字符串（调用时不传就用它）。

文件从上到下就三件事：
① 造一张"简历里有什么"的查询表 → ② 拿 JD 每条要求去查 → ③ 按优先级排好。

## 两个已知局限（面试时主动讲，比被问出来好）

1. 用"包含"判断同名是个偷懒写法：`java` 会被 `javascript` 命中。
   要更稳就加词边界，或者把技能名统一成 ID。
2. RELATED 是人工知识表，没覆盖到的技术就自然落成 missing。
   扩表要靠评测结果——判错的样本就是你下一行该加的东西。
"""

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
    """把技能名统一成"同名同姓"的样子：全小写、去掉空格和横线。

    例："PostgreSQL" / "postgresql" / "Postgres-QL" 统一后都是 "postgresql"。
    不做这一步，明明同一个技术，也会因为一个字母大小写被判成"简历里没有"。
    """
    return name.strip().lower().replace(" ", "").replace("-", "")


def _build_resume_skill_index(resume_profile: ResumeProfileDict) -> dict[str, str]:
    """把简历里提到的技术收成一张查询表：{统一后的名字: 简历原文里的写法}。

    例：简历写 "MySQL 基础"，表里就是 {"mysql": "MySQL 基础"}。
    左边拿来比"有没有"，右边拿来当证据——证据必须是原文里真实存在的字，不能自己拼。

    收哪些地方：技能列表 + 每个项目的技术栈。
    项目描述里顺带提到的技术（比如"用 RetrievalQA 搭问答助手"）不在这里收，
    交给后面 _judge_match_level 去原文里直接搜。
    """
    index: dict[str, str] = {}
    for skill in resume_profile.get("skills", []):
        index.setdefault(_normalize_skill_name(skill), skill)
    for project in resume_profile.get("projects", []):
        for tech in project.get("tech_stack", []):
            index.setdefault(_normalize_skill_name(tech), tech)
    return index


def _lookup_related_terms(skill_norm: str) -> tuple[str, ...]:
    """拿着 JD 要的技能名，去 RELATED 里找沾边的技术；找不到就给空元组。

    为什么判断"包含"而不是"完全相等"：JD 原文可能写"熟悉 PostgreSQL 优先"，
    整理出来是 "postgresql优先"，它不是精确等于表里的 "postgresql"。
    """
    for key, terms in RELATED.items():
        if key in skill_norm or skill_norm in key:
            return terms
    return ()


def _find_original_evidence(text: str, candidate: str) -> str:
    """回到简历原文里找出 candidate 的真实写法，返回那一段原文；找不到就返回空字符串。

    为什么非要多这一步：模型解析简历时会把 "MySQL 基础" 整理成 "MySQL基础"（空格被吃掉）。
    拿这个去跟原文比对会失败，于是"证据"就站不住脚了。所以我不信模型给的写法，
    而是回原文、忽略空格再找一遍——找到什么就返回什么，那才是真证据。

    最后那行 pattern 的意思：把 candidate 的每个字之间都允许有 0 个或多个空格，
    再拿它去原文里搜（搜的时候不分大小写）。
    """
    if not text or not candidate:
        return ""
    if candidate in text:
        return candidate
    pattern = r"\s*".join(re.escape(ch) for ch in candidate if not ch.isspace())
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _judge_match_level(skill: str, index: dict[str, str], text: str = "") -> tuple[MatchLevel, str]:
    """给 JD 的一条要求判档，返回 (档位, 证据)。

    证据的规矩：要么是简历原文里真实存在的片段，要么是空字符串（判 missing 时必须为空）。
    """

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
    """把 JD 里的权重（1-5）换成"该不该问"的优先级（1-5）。

    规则：必修项直接用权重；加分项再降两档（权重 5 → 优先级 3）。
    为什么：加分项再重要，也不该排在必修项前面。

    两个 max/min 是在"夹住"结果，别让它跑出 1-5：太高会被压到 5，最低保底 1。
    """
    base = max(1, min(5, int(weight)))
    return base if is_must else max(1, base - 2)


def build_gap_map(
    jd_profile: JDProfileDict,
    resume_profile: ResumeProfileDict,
    resume_text: str = "",
) -> list[GapItem]:
    """把 JD 的必修项、加分项逐条跑一遍，拼出完整的缺口清单。

    resume_text 是简历原文，传进来有两个用处：
    一是把证据切回"原文里真实的那一段"；二是让 weak 能在项目描述里找沾边技术
    （例：简历写"用 RetrievalQA 搭问答助手"，JD 要 RAG → 该判 weak，不是 missing）。
    """
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
    """LangGraph 的节点函数：进一个字典，出一个字典，里面只放"要更新的字段"。

    为什么最后要 model_dump()：这些数据要存进数据库（checkpointer），
    数据库只认能变成 JSON 的普通数据，Pydantic 对象存不进去，得先转成 dict。
    """
    gaps = build_gap_map(
        state["jd_profile"],
        state["resume_profile"],
        state.get("resume_text", ""),
    )
    return {"gap_map": [gap.model_dump(mode="json") for gap in gaps]}
