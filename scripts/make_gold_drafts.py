"""从真实的题池生成 gold 集的「填空骨架」——你只负责填回答和档位。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.graph.nodes.match_gap import match_gap  # noqa: E402
from src.graph.nodes.parse_inputs import parse_inputs  # noqa: E402
from src.graph.nodes.plan_questions import plan_questions  # noqa: E402

GOLD_DIR = ROOT / "src" / "eval" / "gold"
DRAFT_DIR = GOLD_DIR / "_drafts"

TEMPLATE = """\
# ---- 填空说明（填完删掉这段注释）----
# candidate_answer：你（或同学）针对这道题的真实回答，20 字以上，不要润色。
# human_quality_level：low（明显不足/只有概念）/ medium（达到实习水平）/ high（超出预期），三选一。
# human_evidence_quote：从你自己的回答里挑一句最能支撑档位的话，逐字照抄。
# annotation_note：一句话说明为什么标这一档。
# 填完把本文件挪到 src/eval/gold/ 下（文件名保持不变），再跑 scripts/check_gold.py。

schema_version: 1
question_id: {question_id}
question_text: {question_text}
scoring_dimension: {dimension}
question_difficulty: {difficulty}

# TODO: 换成你的真实回答（≥20 字）
candidate_answer: ""

# TODO: bad / ok / good 三选一
human_quality_level: ""

# TODO: 从上面回答里逐字挑一句
human_evidence_quote: ""

# TODO: 一句话说明
annotation_note: ""
"""


def build_state(jd_path: Path, resume_path: Path) -> dict:
    """跑「解析 → 匹配 → 出题」三个节点，拿到题池。不建图、不跑中断，最省事。"""
    state: dict = {
        "jd_text": jd_path.read_text(encoding="utf-8"),
        "resume_text": resume_path.read_text(encoding="utf-8"),
    }
    state.update(parse_inputs(state))
    state.update(match_gap(state))
    state.update(plan_questions(state))
    return state


def next_question_id(existing: list[Path], start: int) -> int:
    """接着已有编号往下排，避免覆盖手写好的 gold_001/002。"""
    used = set()
    for path in existing:
        tail = path.stem.removeprefix("gold_")
        if tail.isdigit():
            used.add(int(tail))
    number = start
    while number in used:
        number += 1
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 gold 集填空骨架")
    parser.add_argument("--jd", default=str(ROOT / "data" / "jds" / "01-ai-agent-intern.md"))
    parser.add_argument("--resume", default=str(ROOT / "data" / "resumes" / "sample-02-medium.md"))
    parser.add_argument("--count", type=int, default=8, help="生成几份骨架（从题池里取前 N 道）")
    parser.add_argument("--start", type=int, default=3, help="起始编号，默认从 gold_003 开始")
    args = parser.parse_args()

    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(GOLD_DIR.glob("*.yaml")) + list(DRAFT_DIR.glob("*.yaml"))
    number = next_question_id(existing, args.start)

    print(f"跑解析/匹配/出题（约 30~90 秒）… JD={Path(args.jd).name}")
    state = build_state(Path(args.jd), Path(args.resume))
    plan = state.get("question_plan") or []
    if not plan:
        print("题池为空，先检查 parse_inputs/match_gap/plan_questions 的日志。")
        return 1

    written = 0
    for question in plan[: args.count]:
        question_id = f"gold_{number:03d}"
        path = DRAFT_DIR / f"{question_id}.yaml"
        path.write_text(
            TEMPLATE.format(
                question_id=question_id,
                question_text=question["text"],
                dimension=question["dimension"],
                difficulty=question["difficulty"],
            ),
            encoding="utf-8",
        )
        print(f"  {path.name}  [{question['dimension']}] {question['text']}")
        number += 1
        written += 1

    print(f"\n已生成 {written} 份骨架 → {DRAFT_DIR}")
    print("接下来：逐个填 candidate_answer / human_quality_level / human_evidence_quote / annotation_note，")
    print("填完挪到 src/eval/gold/ 并跑 python scripts/check_gold.py。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
