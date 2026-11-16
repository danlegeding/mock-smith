"""图里流动的"那一袋数据"（state），以及它里面每一格装的是什么形状。"""

from __future__ import annotations

from typing import TypedDict


# 对应 src/model/profile.py


class SkillDict(TypedDict):
    """`SkillItem` 的 JSON 形态：JD 里的一条技能要求。"""

    id: str  # s1 / s2，被 Question.evidence_ref 引用
    name: str
    weight: int  # 1-5，岗位多看重它


class ProjectDict(TypedDict):
    """`ProjectItem` 的 JSON 形态：简历里的一个项目。"""

    id: str  # p1 / p2
    name: str
    tech_stack: list[str]
    my_role: str
    result: str  # 量化结果，没有就是空串


class ExperienceDict(TypedDict):
    """`ExperienceItem` 的 JSON 形态：实习 / 竞赛 / 开源经历。"""

    id: str  # e1 / e2
    title: str
    description: str


class JDProfileDict(TypedDict):
    """`JDProfile` 的 JSON 形态：把 JD 原文解析成的结构化岗位画像。"""

    role_title: str
    seniority: str  # Seniority 枚举值：intern / campus / social
    must_skills: list[SkillDict]
    nice_skills: list[SkillDict]
    responsibilities: list[str]
    domain_keywords: list[str]


class ResumeProfileDict(TypedDict):
    """`ResumeProfile` 的 JSON 形态：把候选人简历解析成的结构化画像。"""

    projects: list[ProjectDict]  # 可以没有项目
    skills: list[str]
    experiences: list[ExperienceDict]
    education: str


# 对应 src/model/gap.py


class GapItemDict(TypedDict):
    """`GapItem` 的 JSON 形态：JD 某项要求与简历的匹配结果。"""

    skill: str
    match_level: str  # MatchLevel 枚举值：strong / weak / missing
    evidence: str  # 简历/项目里能证明的原话，missing 时为空串
    priority: int  # 1-5，越高越该问
    probe_angle: str


# 对应 src/model/question.py


class QuestionDict(TypedDict):
    """`Question` 的 JSON 形态：一道面试题；也出现在 Turn / Decision.followup 里。"""

    text: str  # ≤60 字
    dimension: str  # Dimension 枚举值：tech_depth / project_authenticity / ...
    difficulty: int  # 1 简单 / 2 中等 / 3 深入
    evidence_ref: str  # 依据的 JD 技能 id 或简历条目 id
    anchor_quote: str | None  # 追问时必须有：上一轮回答里的原话片段
    kind: str  # QuestionKind 枚举值：opening / followup / scenario


# 对应 src/model/score.py


class SignalsDict(TypedDict):
    """`Signals` 的 JSON 形态：从回答里抽出来的客观信号。"""

    too_short: bool
    off_topic: bool
    has_concrete_example: bool
    has_numbers: bool


class DimensionScoreDict(TypedDict):
    """`DimensionScore` 的 JSON 形态：单个维度的得分 + 理由。"""

    score: int  # 1-5
    evidence_quote: str  # 支撑打分的候选人原话，逐字照抄
    comment: str


class AnswerScoreDict(TypedDict):
    """`AnswerScore` 的 JSON 形态：一次回答的完整评分。"""

    dimension_scores: dict[str, DimensionScoreDict]  # 键是 Dimension 枚举值
    signals: SignalsDict
    valid: bool  # 每个维度都有引文才为 True
    avg: float  # 各维度平均分


# 对应 src/model/turn.py、src/model/decision.py、src/model/report.py


class TurnDict(TypedDict):
    """`Turn` 的 JSON 形态：一轮问答 = 题目 + 回答 + 评分。"""

    question: QuestionDict
    answer: str  # 跳过时为空串
    score: AnswerScoreDict | None  # 跳过时为 None
    skipped: bool


class DecisionDict(TypedDict):
    """`Decision` 的 JSON 形态：decide_next 节点对"下一步做什么"的判断。"""

    action: str  # DecideAction 枚举值：next / deepen / raise_difficulty / ...
    reason: str
    followup: QuestionDict | None  # action=deepen 时带上追问题目


class StrengthDict(TypedDict):
    """`Strength` 的 JSON 形态。"""

    point: str
    evidence_quote: str


class WeaknessDict(TypedDict):
    """`Weakness` 的 JSON 形态。"""

    point: str
    evidence_quote: str
    suggestion: str


class ReportDict(TypedDict):
    """`Report` 的 JSON 形态：面试结束后的最终报告，同时落 reports 表。"""

    overall: str
    dimension_summary: dict[str, float]  # 键是 Dimension 枚举值，值是平均分
    strengths: list[StrengthDict]
    weaknesses: list[WeaknessDict]
    gap_conclusion: str
    next_steps: list[str]  # 正好 3 条




class InterviewState(TypedDict, total=False):
    """一场模拟面试的全部数据。按"哪个节点产出的"分组看。"""

    # ---- 进图时就有（用户给的原文）
    jd_text: str
    resume_text: str

    # ---- parse_inputs 产出
    jd_profile: JDProfileDict
    resume_profile: ResumeProfileDict

    # ---- match_gap 产出
    gap_map: list[GapItemDict]

    # ---- plan_questions 产出
    question_plan: list[QuestionDict]  # 题池，主流程从这里挑题

    # ---- select_question 产出（每轮被覆盖）
    current_question: QuestionDict | None  # None 表示没题可问了 → 路由到 END

    # ---- ask 产出（每轮追加一条）
    turns: list[TurnDict]  # 每轮问答（答完由 evaluate_answer 补 score）

    # ---- decide_next 产出（每轮覆盖）
    decision: DecisionDict  # 最近一次决策：action + reason（追问时 current_question 已被填好）
    next_difficulty: int | None  # 难度提示，select_question 消费一次后清空

    # ---- generate_report 产出：面试结束后的报告
    report: ReportDict

    # 说明：追加型字段（turns）没有用 Annotated[..., operator.add] 的 reducer，
    # 而是在节点里自己拼好整份列表再返回——本轮只有 ask 一个节点写 turns，
    # 用 reducer 反而容易因为"重放"多算一次。
