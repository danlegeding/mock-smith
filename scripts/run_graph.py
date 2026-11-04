"""命令行跑一次图的前半段：parse_inputs → match_gap → plan_questions。

为什么要有这个文件（它以后也不会被删）：
1. 面试现场演示：一条命令，不用起 API、不用开前端；
2. 改完 prompt / 判档规则，想立刻看效果，不用走整条 FastAPI 链路；
3. 看 state 到底长什么样 —— 排查"数据在哪一步丢了"最直接的地方。

跑法：
    conda activate interview-agent
    python scripts/run_graph.py                    # 第一次：解析 + 匹配 + 出题
    python scripts/run_graph.py                    # 再跑一次：直接从数据库续上，不重跑
    python scripts/run_graph.py --thread t2        # 换一个新会话
    python scripts/run_graph.py --limit 40         # 只看前 40 条缺口（缺口多了刷屏）

注意：同一个 thread_id 跑第二次时，图不会重跑，而是从 checkpointer 把上次的 state
读回来 —— 这就是"断点续跑"，后面多轮面试全靠它。
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import close_pool  # noqa: E402
from src.graph.build import build_persistent_graph  # noqa: E402
from src.model import DIMENSIONS, DIMENSION_LABELS  # noqa: E402


def main() -> int:
    parser = ArgumentParser(description="跑一次 parse→match→plan 的最小链路")
    parser.add_argument("--thread", default="demo-1", help="会话 id（同一个 id 会续跑）")
    parser.add_argument(
        "--jd",
        default=str(ROOT / "data" / "jds" / "01-ai-agent-intern.md"),
    )
    parser.add_argument(
        "--resume",
        default=str(ROOT / "data" / "resumes" / "sample-02-medium.md"),
    )
    parser.add_argument("--limit", type=int, default=26, help="缺口最多打印几条")
    args = parser.parse_args()

    graph = build_persistent_graph()
    config = {"configurable": {"thread_id": args.thread}}

    try:
        snapshot = graph.get_state(config)
        if snapshot.values:
            # 数据库里已经有这个会话 → 不重跑，直接看现有 state
            print(f"[续跑] thread={args.thread} 已有状态，跳过解析（断点续跑生效）")
            state = snapshot.values
        else:
            print(f"[新会话] thread={args.thread} 开始解析 JD + 简历 → 判档 → 出题……")
            state = graph.invoke(
                {
                    "jd_text": Path(args.jd).read_text(encoding="utf-8"),
                    "resume_text": Path(args.resume).read_text(encoding="utf-8"),
                },
                config=config,
            )

        jd = state.get("jd_profile", {})
        resume = state.get("resume_profile", {})
        gaps = state.get("gap_map", [])
        plan = state.get("question_plan", [])

        print()
        print(f"JD    : {jd.get('role_title', '?')} | 硬性要求 {len(jd.get('must_skills', []))} 条")
        print(f"候选人: {resume.get('education', '?')} | 技能 {len(resume.get('skills', []))} 项")
        print(f"缺口  : {len(gaps)} 条 | 题池 {len(plan)} 道")
        print("-" * 78)

        for gap in gaps[: args.limit]:
            print(
                f"{gap['skill']:<24} {gap['match_level']:<8} 优先 {gap['priority']}  "
                f"证据={gap['evidence']!r}"
            )
        if len(gaps) > args.limit:
            print(f"…… 还有 {len(gaps) - args.limit} 条没打印（--limit 调大）")

        counts: dict[str, int] = {}
        for gap in gaps:
            counts[gap["match_level"]] = counts.get(gap["match_level"], 0) + 1
        print("-" * 78)
        print("档位分布:", counts)

        print()
        print("=" * 78)
        print(f"题池（{len(plan)} 道，供主流程挑题）")
        print("=" * 78)
        for i, question in enumerate(plan, 1):
            label = DIMENSION_LABELS.get(question["dimension"], question["dimension"])
            print(
                f"{i:>2}. [{label:<6}] 难度{question['difficulty']} "
                f"{question['evidence_ref']:<4} {question['kind']:<9} {question['text']}"
            )

        # 维度覆盖：5 个维度都要有题，否则报告里会出现"沟通表达：未覆盖"
        covered = {question["dimension"] for question in plan}
        print("-" * 78)
        print("维度覆盖:", {DIMENSION_LABELS[d]: (d in covered) for d in DIMENSIONS})
        print(f"难度分布:", {d: sum(1 for q in plan if q["difficulty"] == d) for d in (1, 2, 3)})
        print(f"\nstate 里的字段: {sorted(state.keys())}")
        return 0
    finally:
        # 连接池是全局的，脚本退出前关掉，否则会有"没能及时停掉线程"的警告
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
