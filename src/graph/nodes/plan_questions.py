"""节点 3：plan_questions —— 出题池。

输入：JD 结构 + 简历结构 + 缺口清单（match_gap 的产出）
输出：10 道题，每道题带"考哪个维度 / 多难 / 依据哪一条"。

## 这一层为什么要单独存在，而不是"问一题生成一题"

1. **可对比**：整池题一起生成，才能保证 5 个维度都覆盖到；一问一生成很容易
   一直逮着 Python 问 8 轮。
2. **可审查**：题池是写进 state 的数据，面试前可以人工看一眼，不合规的提前删掉。
3. **可复用**：追问是在题池之外临时生成的（followup），主问题从池里挑，
   池子被消耗掉就换维度，逻辑干净。

## 三种"别问"

- 判 `missing` 的技能不许出深挖题——人家没写过，问了只会得到"不太了解"。
  对这种只出**探底题**（难度 1）。
- 不许出 `followup`。追问必须基于候选人刚说的话，提前生成就是瞎问。
- 不许编简历里没有的项目；`evidence_ref` 必须能在"可引用 id"表里查到。

## 代码里做了什么、没做什么

- 做了什么：拼输入、调模型、**过滤掉 evidence_ref 不存在的题**（护栏 G1 的简化版）。
  模型偶尔会编 id（s99），这一层直接扔掉，不让脏数据流到下游。
- 没做什么：不帮模型想题。规则全在 `prompts/plan_questions.md` 里，
  改出题风格改那个文件就行，不用动代码。
"""

from __future__ import annotations

from typing import Any

from src.graph.checks import strip_internal_ids
from src.graph.nodes.parse_inputs import render_prompt
from src.graph.policy import active_dimensions
from src.graph.state import GapItemDict, InterviewState, JDProfileDict, ResumeProfileDict
from src.llm import call_json
from src.log import get_logger
from src.model import DIMENSION_LABELS, Question, QuestionPlan

logger = get_logger(__name__)

PLAN_SIZE = 10


def _build_evidence_ref_table(jd_profile: JDProfileDict, resume_profile: ResumeProfileDict) -> dict[str, str]:
    """列出"允许被引用的 id"：JD 的 s1/s2…、简历的 p1/p2…、e1/e2…

    evidence_ref 只能从这里选。这是最简单有效的一道护栏：模型编不出不存在的 id。
    """
    refs: dict[str, str] = {}
    for key, label in (("must_skills", "硬性要求"), ("nice_skills", "加分项")):
        for item in jd_profile.get(key, []):
            refs[item["id"]] = f"{label} | {item['name']}（权重 {item['weight']}）"
    for project in resume_profile.get("projects", []):
        refs[project["id"]] = f"简历项目 | {project['name']}"
    for exp in resume_profile.get("experiences", []):
        refs[exp["id"]] = f"简历经历 | {exp['title']}"
    return refs


def _render_user_message(
    jd_profile: JDProfileDict,
    resume_profile: ResumeProfileDict,
    gaps: list[GapItemDict],
    refs: dict[str, str],
) -> str:
    """把出题需要的材料拼成一段给模型看的文本（纯文本比 JSON 稳，模型读表格更准）。"""
    lines: list[str] = []

    lines.append("## 可引用 id（evidence_ref 只能从这些里选）")
    for ref_id, label in refs.items():
        lines.append(f"- {ref_id}: {label}")

    lines.append("")
    lines.append("## JD")
    lines.append(f"岗位：{jd_profile.get('role_title', '')}（{jd_profile.get('seniority', '')}）")
    lines.append("职责：")
    for i, duty in enumerate(jd_profile.get("responsibilities", []), 1):
        lines.append(f"{i}. {duty}")

    lines.append("")
    lines.append("## 本次要考的维度（只能从这些里出题）")
    for dimension in active_dimensions(resume_profile):
        lines.append(f"- {DIMENSION_LABELS[dimension]}（{dimension.value}）")

    lines.append("")
    lines.append("## 缺口清单（已判档：strong=简历里有 / weak=沾边 / missing=完全没提）")
    for gap in gaps:
        lines.append(
            f"- {gap['skill']} | {gap['match_level']} | 优先级 {gap['priority']} "
            f"| 证据: {gap['evidence'] or '（无）'}"
        )

    lines.append("")
    lines.append("## 候选人")
    lines.append(f"教育：{resume_profile.get('education', '')}")
    lines.append(f"技能：{'、'.join(resume_profile.get('skills', [])) or '（未填）'}")
    for project in resume_profile.get("projects", []):
        lines.append(
            f"项目 {project['id']}：{project['name']}｜技术：{', '.join(project.get('tech_stack', []))}"
            f"｜我的角色：{project.get('my_role', '') or '未写'}"
        )

    lines.append("")
    lines.append(f"请按规则生成 {PLAN_SIZE} 道题的题池。")
    return "\n".join(lines)


def _filter_valid_questions(
    questions: list[Question],
    refs: dict[str, str],
    seen: set[str],
    only_dims: set[str] | None = None,
) -> list[Question]:
    """过滤 + 清洗一批题：evidence_ref 合法、题干干净、不重复。

    `only_dims` 不为空时只留这些维度的题（补题那一轮用）。
    """
    kept: list[Question] = []
    for question in questions:
        if only_dims is not None and question.dimension.value not in only_dims:
            continue
        if question.evidence_ref not in refs:
            continue
        cleaned = strip_internal_ids(question.text)
        if len(cleaned) < 4 or cleaned in seen:
            continue
        seen.add(cleaned)
        kept.append(question.model_copy(update={"text": cleaned}))
    return kept


def plan_questions(state: InterviewState) -> dict[str, Any]:
    """LangGraph 节点函数：出题池，返回 {"question_plan": [...]}。"""
    jd_profile = state["jd_profile"]
    resume_profile = state["resume_profile"]
    gaps = state.get("gap_map", [])

    refs = _build_evidence_ref_table(jd_profile, resume_profile)
    system_prompt = render_prompt("plan_questions.md")
    user_message = _render_user_message(jd_profile, resume_profile, gaps, refs)

    plan = call_json(QuestionPlan, system=system_prompt, user=user_message, temperature=0.5)
    seen: set[str] = set()
    # 第一轮也按"本次要考的维度"过滤：提示词里写了"只能从给定维度里选"，实测模型仍会
    # 自己补一个 project_authenticity（没有项目也照问"你做过什么小工具"）——同样靠代码兜底。
    allowed = {d.value for d in active_dimensions(resume_profile)}
    kept = _filter_valid_questions(plan.questions, refs, seen, only_dims=allowed)
    dropped = len(plan.questions) - len(kept)
    if dropped:
        logger.info("[plan_questions] 丢掉 %d 道题（id 不合法 / 题干为空 / 重复）", dropped)

    # 覆盖兜底：prompt 要求「每个维度至少 1 题」，但模型实测会漏（d7-agent-3 缺沟通表达）。
    # 漏了就再要一轮，只针对漏掉的维度补题——这是代码兜底，不是靠 prompt 自律。
    # 维度清单来自简历（没有项目就不考项目真实性），不是写死的 5 个。
    missing = [d for d in active_dimensions(resume_profile) if d not in {q.dimension for q in kept}]
    if missing:
        names = "、".join(f"{DIMENSION_LABELS[d]}({d.value})" for d in missing)
        logger.info("[plan_questions] 题池漏了维度：%s → 补一轮", names)
        extra_user = (
            f"{user_message}\n\n## 额外要求（第二轮补题）\n"
            f"第一轮漏掉了这些维度：{names}。\n"
            f"请**只**针对这些维度出题，每个维度 1-2 道，其余维度不要出。"
        )
        extra = call_json(QuestionPlan, system=system_prompt, user=extra_user, temperature=0.5)
        kept += _filter_valid_questions(extra.questions, refs, seen, only_dims={d.value for d in missing})

    counts: dict[str, int] = {}
    for question in kept:
        counts[question.dimension.value] = counts.get(question.dimension.value, 0) + 1
    logger.info("[plan_questions] 题池 %d 道：%s", len(kept), counts)

    return {"question_plan": [q.model_dump(mode="json") for q in kept[:PLAN_SIZE]]}
