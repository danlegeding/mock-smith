"""图里流动的"那一袋数据"（state）。

在 LangGraph 里，节点之间不直接互相传参，而是共享同一个 state：
每个节点返回一个字典，框架帮你把字典**合并**进 state，下一个节点就能读到。

`total=False` 的意思是：这些键不要求一开始就全部存在。
- 图开始时只有 `jd_text` / `resume_text`；
- `parse_inputs` 跑完才出现 `jd_profile` / `resume_profile`；
- `match_gap` 跑完才出现 `gap_map`；
- `plan_questions` 跑完才出现 `question_plan`。

⚠️ 只有写在这个类里的键才会被保留：节点返回了一个没声明的键，LangGraph 不会报错，
而是直接丢掉。排查"节点明明 return 了，下游读不到"的时候先看这里。

为什么字段都写成 dict / list[dict] 而不是 Pydantic 对象：
state 要整个存进数据库（checkpointer），数据库只认能变成 JSON 的普通数据。
Pydantic 对象在节点里用，出了节点就 model_dump() 成 dict。
"""

from __future__ import annotations

from typing import Any, TypedDict


class InterviewState(TypedDict, total=False):
    """一场模拟面试的全部数据。按"哪个节点产出的"分组看。"""

    # ---- 进图时就有（用户给的原文）
    jd_text: str
    resume_text: str

    # ---- parse_inputs 产出
    jd_profile: dict[str, Any]
    resume_profile: dict[str, Any]

    # ---- match_gap 产出
    gap_map: list[dict[str, Any]]

    # ---- plan_questions 产出
    question_plan: list[dict[str, Any]]  # 题池，主流程从这里挑题

    # ---- select_question 产出（每轮被覆盖）
    current_question: dict[str, Any] | None  # None 表示没题可问了 → 路由到 END

    # ---- ask 产出（每轮追加一条）
    turns: list[dict[str, Any]]  # 每轮问答（Turn 的 model_dump；答完由 evaluate_answer 补 score）

    # ---- decide_next 产出（每轮覆盖）
    decision: dict[str, Any]  # 最近一次决策：action + reason（追问时 current_question 已被填好）
    next_difficulty: int | None  # 难度提示，select_question 消费一次后清空

    # ---- D8 产出：面试结束后的报告
    report: dict[str, Any]

    # 说明：追加型字段（turns）没有用 Annotated[..., operator.add] 的 reducer，
    # 而是在节点里自己拼好整份列表再返回——本轮只有 ask 一个节点写 turns，
    # 用 reducer 反而容易因为"重放"多算一次。
