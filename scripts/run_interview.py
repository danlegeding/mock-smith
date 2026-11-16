"""命令行跑一场模拟面试（D8 版本：出题 → 提问 → 评分 → 决策 → 报告）。"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langgraph.types import Command  # noqa: E402

from src.db import close_pool  # noqa: E402
from src.graph.build import build_persistent_graph  # noqa: E402
from src.graph.policy import MAX_TURNS  # noqa: E402
from src.model import DIMENSION_LABELS  # noqa: E402

# 假回答：故意写得"具体但不够深入"，用来观察流程，不代表评分效果（评分 D7 才有）
FAKE_ANSWERS = [
    "我用 LangChain 的 RetrievalQA 把检索和问答串起来，向量库用 Chroma，prompt 里塞 top3 文档",
    "接口加了 Pydantic 校验和统一异常处理，uvicorn 起服务，超时设了 30 秒",
    "我把重复的请求封装成函数，用 logging 记日志，关键地方加了 try/except",
    "客服项目主要是我做的意图识别和检索部分，数据库表是同组同学建的",
    "借阅记录用 MySQL 一张表，借书还书各一个接口，用一个状态字段控制",
    "先拆成规划、检索、回复三步，每步一个函数，中间用状态对象传数据",
    "先看日志里哪个接口慢，再看是不是数据库慢查询，最后看外部 API 有没有超时",
    "写了分组统计的 SQL，在时间字段上加了索引，查询从 2 秒降到 200 毫秒",
    "了解过一点，没实际做过，看过一些评测相关的文章",
]


def _pending_question(graph, config) -> dict | None:
    """图停在哪个 interrupt 上，就把那个问题取出来；没有就是跑完了。"""
    snapshot = graph.get_state(config)
    for task in snapshot.tasks:
        for item in task.interrupts:
            return item.value
    return None


def main() -> int:
    parser = ArgumentParser(description="跑一场模拟面试")
    parser.add_argument("--thread", default="itv-1", help="会话 id（同一个 id 会续跑）")
    parser.add_argument("--auto", action="store_true", help="用假回答自动跑完")
    parser.add_argument("--skip", type=int, default=0, help="第几题回答『不会』（1 起算）")
    parser.add_argument(
        "--jd", default=str(ROOT / "data" / "jds" / "01-ai-agent-intern.md")
    )
    parser.add_argument(
        "--resume", default=str(ROOT / "data" / "resumes" / "sample-02-medium.md")
    )
    args = parser.parse_args()

    graph = build_persistent_graph()
    config = {"configurable": {"thread_id": args.thread}}

    try:
        snapshot = graph.get_state(config)
        if not snapshot.values:
            print(f"[新会话] thread={args.thread} 解析 JD + 简历 → 判档 → 出题……")
            graph.invoke(
                {
                    "jd_text": Path(args.jd).read_text(encoding="utf-8"),
                    "resume_text": Path(args.resume).read_text(encoding="utf-8"),
                },
                config=config,
            )
        else:
            print(f"[续跑] thread={args.thread} 已有 {len(snapshot.values.get('turns') or [])} 轮记录")

        # 一轮 = 取问题 → 收回答 → resume（图自动往下走，直到下一个 interrupt）
        for round_no in range(1, MAX_TURNS + 2):
            payload = _pending_question(graph, config)
            if payload is None:
                break
            label = DIMENSION_LABELS.get(payload["dimension"], payload["dimension"])
            print(f"\n第 {round_no} 题 [{label}] 难度{payload['difficulty']}（{payload['kind']}）")
            print(f"  {payload['text']}")

            if args.auto:
                if args.skip == round_no:
                    reply: dict = {"skip": True}
                    print("  > （跳过：这块不太了解）")
                else:
                    reply = {"text": FAKE_ANSWERS[(round_no - 1) % len(FAKE_ANSWERS)]}
                    print(f"  > {reply['text']}")
            else:
                raw = input("  > 你的回答（直接回车 = 跳过）: ").strip()
                reply = {"text": raw} if raw else {"skip": True}

            graph.invoke(Command(resume=reply), config=config)

        state = graph.get_state(config).values
        turns = state.get("turns") or []

        print()
        print("=" * 78)
        print(f"面试结束：共 {len(turns)} 轮")
        print("=" * 78)
        for i, turn in enumerate(turns, 1):
            question = turn["question"]
            label = DIMENSION_LABELS.get(question["dimension"], question["dimension"])
            if turn["skipped"]:
                mark = "跳过"
            else:
                score = turn.get("score") or {}
                item = next(iter((score.get("dimension_scores") or {}).values()), None)
                if item is None:
                    mark = "未评"
                else:
                    evidence = "有证据" if item.get("evidence_quote") else "无证据"
                    mark = f"{item['score']}分({evidence})"
            print(f"{i:>2}. [{label:<6}] {mark:<12} {question['text'][:36]}")

        dims = [turn["question"]["dimension"] for turn in turns]
        print("-" * 78)
        print("问到的维度:", {DIMENSION_LABELS[d]: dims.count(d) for d in dict.fromkeys(dims)})

        report = state.get("report")
        if not report:
            print("\n（这次没有生成报告：可能还没走到收尾节点）")
            return 0

        print()
        print("=" * 78)
        print("报告")
        print("=" * 78)
        print("结论:", report["overall"])
        print("维度均分:", {DIMENSION_LABELS[d]: s for d, s in report["dimension_summary"].items()})
        for item in report["strengths"]:
            print(f"  + {item['point']}")
            print(f"    证据：{item['evidence_quote']}")
        for item in report["weaknesses"]:
            print(f"  - {item['point']}")
            print(f"    证据：{item['evidence_quote']}")
            print(f"    建议：{item['suggestion']}")
        print("缺口:", report["gap_conclusion"])
        print("下一步:")
        for i, step in enumerate(report["next_steps"], 1):
            print(f"  {i}. {step}")
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
