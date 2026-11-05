"""前端验收：不打开浏览器，也能验证 Streamlit 页面能跑起来。

原理：Streamlit 自带的 `AppTest` 会在进程内执行 `web/app.py`（和真实访问一样跑一遍脚本），
我们断言"没有异常 + 关键控件都在"。这样前端改动也有了一条命令的回归检查。

跑法（后端要开着）：
    python scripts/check_web.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "web" / "app.py"

sys.path.insert(0, str(ROOT / "web"))

from streamlit.testing.v1 import AppTest  # noqa: E402

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"{'[PASS]' if ok else '[FAIL]'} {name}" + (f"  ({detail})" if detail else ""))


def render_screen(**session_state) -> AppTest:
    """把前端状态直接塞进 session_state，再跑一遍脚本——不用真跑模型就能测每一屏。"""
    app = AppTest.from_file(str(APP), default_timeout=120)
    for key, value in session_state.items():
        app.session_state[key] = value
    app.run()
    return app


def main() -> int:
    start = AppTest.from_file(str(APP), default_timeout=120)
    start.run()

    check("① 开面页执行无异常", not start.exception, str(start.exception[:1]) if start.exception else "")
    check("开面页标题已渲染", any(h.value == "① 开一场面试" for h in start.header))
    check("有 JD / 简历两个下拉", len(start.selectbox) >= 2, f"{len(start.selectbox)} 个")
    check("开始按钮存在", any(b.label == "开始面试" for b in start.button))
    check(
        "侧边栏有后端状态",
        any("后端" in m.value for m in start.sidebar.markdown)
        or bool(start.sidebar.success)
        or bool(start.sidebar.error),
    )

    interview = render_screen(
        page="面试",
        session_id="fake-session",
        turn={
            "type": "question",
            "turn_index": 2,
            "question": {
                "text": "你在客服小助手里具体负责哪几块？",
                "dimension": "project_authenticity",
                "difficulty": 2,
                "evidence_ref": "p1",
                "anchor_quote": None,
                "kind": "opening",
            },
        },
        history=[],
    )
    check("② 面试页执行无异常", not interview.exception)
    check("面试页显示题号", any("第 3 题" in m.value for m in interview.markdown))
    check("面试页有两个按钮", any(b.label == "提交回答" for b in interview.button) and any(b.label == "跳过这题" for b in interview.button))

    report = render_screen(
        page="报告",
        report={
            "overall": "基础知识扎实，但缺少量化结果，建议暂缓推进。",
            "dimension_summary": {"tech_depth": 3.0, "job_match": 2.0},
            "strengths": [{"point": "RAG 链路清楚", "evidence_quote": "用 pgvector 存向量，召回 top5"}],
            "weaknesses": [{"point": "缺量化", "evidence_quote": "大概提升了一些", "suggestion": "补一个前后对比指标"}],
            "gap_conclusion": "岗位要 Docker，简历未体现。",
            "next_steps": ["补一个端到端可跑的 Docker 部署", "把项目指标写进简历", "准备 3 分钟项目讲解"],
        },
    )
    check("③ 报告页执行无异常", not report.exception)
    check("报告页标题已渲染", any(h.value == "③ 面试报告" for h in report.header))
    check("报告页有综合评分", any("综合评分" in str(m.label) for m in report.metric))
    check("报告页显示下一步", any("补一个端到端可跑的 Docker 部署" in m.value for m in report.markdown))

    records = render_screen(page="记录", records_transcript=None, records_report=None, records_pick=None)
    check("④ 记录页执行无异常", not records.exception)
    check("记录页标题已渲染", any(h.value == "④ 会话记录" for h in records.header))

    failed = [name for name, ok, _ in checks if not ok]
    print()
    if failed:
        print(f"结果：{len(checks) - len(failed)}/{len(checks)} 通过，失败：{', '.join(failed)}")
        return 1
    print(f"结果：{len(checks)}/{len(checks)} 全绿")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
