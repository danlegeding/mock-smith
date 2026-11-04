"""数据契约（src/model/）的验收测试 —— 这是「契约」，不是我给的参考答案。

跑法：
    conda activate interview-agent
    cd "D:\\Python——project\\mock-interview"
    python scripts/test_schemas.py

全 PASS 才算 src/model/ 写对了。某个 FAIL 就照着提示改，别看 _solutions。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# 让人能直接 `python scripts/test_schemas.py`：否则 sys.path 里只有 scripts/，
# import src 会失败。这是脚本类文件的标准写法。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from src.model import (
    DIMENSIONS,
    AnswerScore,
    DimensionScore,
    GapItem,
    JDProfile,
    Question,
    Report,
    ResumeProfile,
    TurnOut,
)

results: list[tuple[str, bool, str]] = []


def ok(name: str, fn) -> None:
    """期望 fn() 正常执行，且返回 True。"""
    try:
        assert fn() is not False
        results.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {str(exc).strip().splitlines()[0][:110]}"
        results.append((name, False, detail))


def bad(name: str, fn, why: str) -> None:
    """期望 fn() 必须报错。"""
    try:
        fn()
    except Exception:  # noqa: BLE001
        results.append((name, True, ""))
        return
    results.append((name, False, f"本该报错（{why}）却通过了"))


# ---------------------------------------------------------------- 正例

GOOD_JD = {
    "role_title": "AI Agent 开发实习生",
    "seniority": "intern",
    "must_skills": [{"id": "s1", "name": "Python", "weight": 5}],
    "nice_skills": [{"id": "s2", "name": "pgvector", "weight": 3}],
    "responsibilities": ["参与 Agent 后端开发"],
    "domain_keywords": ["知识库"],
}

GOOD_RESUME = {
    "projects": [
        {
            "id": "p1",
            "name": "知识库问答 Agent",
            "tech_stack": ["Python"],
            "my_role": "负责检索链路",
            "result": "召回率 0.62 -> 0.81",
        }
    ],
    "skills": ["Python"],
    "experiences": [{"id": "e1", "title": "后端实习", "description": "接口优化"}],
    "education": "某大学 软件工程 大二",
}


def _jd_ok() -> bool:
    jd = JDProfile(**GOOD_JD)
    # 光能构造不算过，字段得真在
    assert jd.role_title == "AI Agent 开发实习生"
    assert len(jd.must_skills) == 1 and jd.must_skills[0].name == "Python"
    assert jd.must_skills[0].weight == 5
    assert jd.nice_skills[0].id == "s2"
    return True


def _resume_ok() -> bool:
    rs = ResumeProfile(**GOOD_RESUME)
    assert rs.projects[0].my_role == "负责检索链路"
    assert rs.experiences[0].title == "后端实习"
    return True


def _answer_valid_true() -> bool:
    s = AnswerScore(
        dimension_scores={
            "tech_depth": {
                "score": 4,
                "evidence_quote": "我们用 Redis 做分布式锁",
                "comment": "有取舍",
            }
        }
    )
    assert s.valid is True, "有 evidence_quote 时 valid 必须是 True"
    assert abs(s.avg - 4.0) < 1e-6
    return True


def _answer_valid_false() -> bool:
    s = AnswerScore(
        dimension_scores={"tech_depth": {"score": 5, "evidence_quote": "   "}}
    )
    assert s.valid is False, "evidence_quote 是空白时 valid 必须是 False"
    return True


def _dimensions_len() -> bool:
    assert len(DIMENSIONS) == 5, f"DIMENSIONS 应该有 5 项，现在 {len(DIMENSIONS)}"
    return True


def _question_opening() -> bool:
    q = Question(
        text="讲讲你做的检索链路",
        dimension="tech_depth",
        evidence_ref="p1",
        kind="opening",
    )
    assert q.anchor_quote is None
    assert q.difficulty in (1, 2, 3)
    return True


def _report_ok() -> bool:
    r = Report(
        overall="建议推进",
        next_steps=["补一次", "补两次", "补三次"],
        strengths=[{"point": "检索讲得清楚", "evidence_quote": "召回率 0.62 到 0.81"}],
    )
    assert len(r.next_steps) == 3
    return True


def _turnout_kind() -> bool:
    t = TurnOut(session_id="s1", type="question", question=None, turn_index=0)
    assert t.type == "question"
    return True


# ---------------------------------------------------------------- 反例（该拦住的）

bad(
    "JD 缺 must_skills 被拦",
    lambda: JDProfile({k: v for k, v in GOOD_JD.items() if k != "must_skills"}),
    "must_skills 是必填",
)
bad(
    "JD 的 must_skills 是空列表被拦",
    lambda: JDProfile({**GOOD_JD, "must_skills": []}),
    "至少 1 项",
)
bad(
    "JD 缺 responsibilities 被拦",
    lambda: JDProfile({k: v for k, v in GOOD_JD.items() if k != "responsibilities"}),
    "responsibilities 是必填",
)
bad(
    "简历缺 projects 被拦",
    lambda: ResumeProfile({k: v for k, v in GOOD_RESUME.items() if k != "projects"}),
    "projects 是必填",
)
bad(
    "followup 缺 anchor_quote 被拦",
    lambda: Question(
        text="刚才说的锁怎么续期？",
        dimension="tech_depth",
        evidence_ref="p1",
        kind="followup",
    ),
    "追问必须锚定上一轮原话",
)
bad(
    "问题超过 60 字被拦",
    lambda: Question(
        text="这是一句特别长的问题" * 10,
        dimension="tech_depth",
        evidence_ref="p1",
    ),
    "text ≤ 60 字",
)
bad(
    "Question 缺 evidence_ref 被拦",
    lambda: Question(text="讲讲你的项目", dimension="tech_depth"),
    "evidence_ref 是必填",
)
bad(
    "未知维度被拦",
    lambda: AnswerScore(dimension_scores={"瞎编的维度": {"score": 3, "evidence_quote": "x"}}),
    "维度必须来自 Dimension",
)
bad(
    "分数 6 被拦",
    lambda: DimensionScore(score=6, evidence_quote="x"),
    "score 1-5",
)
bad(
    "分数 0 被拦",
    lambda: DimensionScore(score=0, evidence_quote="x"),
    "score 1-5",
)
bad(
    "priority 6 被拦",
    lambda: GapItem(skill="Python", match_level="strong", evidence="x", priority=6),
    "priority 1-5",
)
bad(
    "next_steps 只有 2 条被拦",
    lambda: Report(overall="ok", next_steps=["a", "b"]),
    "必须正好 3 条",
)
bad(
    "TurnOut.type 只能是 question/report",
    lambda: TurnOut(session_id="s1", type="瞎写", turn_index=0),
    "type 是 Literal",
)

# ---------------------------------------------------------------- 正例执行

ok("JD 能正确构造（字段都得在）", _jd_ok)
ok("简历能正确构造", _resume_ok)
ok("有证据时 valid=True", _answer_valid_true)
ok("无证据时 valid=False", _answer_valid_false)
ok("DIMENSIONS 有 5 项", _dimensions_len)
ok("opening 可以没有 anchor_quote", _question_opening)
ok("报告 3 条建议能构造", _report_ok)
ok("TurnOut 能构造", _turnout_kind)

# ---------------------------------------------------------------- 汇总

passed = sum(1 for _, good, _ in results if good)
failed = [r for r in results if not r[1]]
for name, good, detail in results:
    print(f"  {'PASS' if good else 'FAIL'}  {name}" + (f"  <- {detail}" if detail else ""))

print()
print(f"结果：{passed}/{len(results)} 通过")
if failed:
    print("还没通过：")
    for name, _, detail in failed:
        print(f"  - {name}：{detail}")
    sys.exit(1)
print("全绿，src/model/ 的契约实现对了。可以进下一个文件了。")
