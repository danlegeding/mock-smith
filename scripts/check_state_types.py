"""校验 `src/graph/state.py` 里的 TypedDict 与 `src/model/` 的 Pydantic 模型是否对得上。"""

from __future__ import annotations

import inspect
import sys
from enum import Enum
from pathlib import Path
from typing import get_type_hints

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.graph import state  # noqa: E402
from src.graph.nodes import (  # noqa: E402
    ask,
    decide_next,
    evaluate_answer,
    generate_report,
    match_gap,
    parse_inputs,
    plan_questions,
    select_question,
)
from src.model import (  # noqa: E402
    AnswerScore,
    Decision,
    DimensionScore,
    ExperienceItem,
    GapItem,
    JDProfile,
    ProjectItem,
    Question,
    Report,
    ResumeProfile,
    Signals,
    SkillItem,
    Strength,
    Turn,
    Weakness,
)

# TypedDict ←→ Pydantic 模型
PAIRS = [
    (state.SkillDict, SkillItem),
    (state.ProjectDict, ProjectItem),
    (state.ExperienceDict, ExperienceItem),
    (state.JDProfileDict, JDProfile),
    (state.ResumeProfileDict, ResumeProfile),
    (state.GapItemDict, GapItem),
    (state.QuestionDict, Question),
    (state.SignalsDict, Signals),
    (state.DimensionScoreDict, DimensionScore),
    (state.AnswerScoreDict, AnswerScore),
    (state.TurnDict, Turn),
    (state.DecisionDict, Decision),
    (state.StrengthDict, Strength),
    (state.WeaknessDict, Weakness),
    (state.ReportDict, Report),
]

# 8 个节点的入口函数
NODES = [
    ("parse_inputs", parse_inputs.parse_inputs),
    ("match_gap", match_gap.match_gap),
    ("plan_questions", plan_questions.plan_questions),
    ("select_question", select_question.select_question),
    ("ask", ask.ask_question),
    ("evaluate_answer", evaluate_answer.evaluate_answer),
    ("decide_next", decide_next.decide_next_action),
    ("generate_report", generate_report.generate_report),
]


def model_keys(model: type) -> set[str]:
    """模型 dump 后会出现哪些键：普通字段 + computed_field。"""
    computed = set(getattr(model, "model_computed_fields", {}) or {})
    return set(model.model_fields) | computed


def main() -> int:
    failures: list[str] = []

    for typed_dict, model in PAIRS:
        dict_keys = set(typed_dict.__annotations__)
        expected = model_keys(model)
        name = f"{typed_dict.__name__} ↔ {model.__name__}"

        if dict_keys != expected:
            missing = sorted(expected - dict_keys)  # 模型有、state 忘了写
            extra = sorted(dict_keys - expected)  # state 多写了（模型可能改名/删了）
            failures.append(f"{name} 键不一致：缺 {missing}，多 {extra}")
            continue

        # 枚举字段在 JSON 里是字符串
        hints = get_type_hints(typed_dict)
        enum_fields = [
            field_name
            for field_name, field in model.model_fields.items()
            if isinstance(field.annotation, type) and issubclass(field.annotation, Enum)
        ]
        wrong = [field_name for field_name in enum_fields if hints.get(field_name) is not str]
        if wrong:
            failures.append(f"{name} 的枚举字段应标注 str：{wrong}")
            continue

        print(f"PASS {name}：{len(expected)} 个键" + (f"（其中枚举 {len(enum_fields)} 个）" if enum_fields else ""))

    # 8 个节点的 state 参数
    for node_name, function in NODES:
        hints = get_type_hints(function)
        annotation = hints.get("state")
        if annotation is not state.InterviewState:
            failures.append(f"节点 {node_name} 的 state 参数应标注 InterviewState，实际是 {annotation!r}")
        else:
            print(f"PASS 节点 {node_name}：state: InterviewState")

    print()
    if failures:
        print(f"FAIL：{len(failures)} 处不一致")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"全部通过（{len(PAIRS)} 组 TypedDict、{len(NODES)} 个节点）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
