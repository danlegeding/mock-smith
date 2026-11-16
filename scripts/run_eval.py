"""评测脚本：拿 gold 集检验 AI 评分跟人工评分的一致性。

跑法（项目根目录）：
    python scripts/run_eval.py                 # 跑全部 10 条
    python scripts/run_eval.py --limit 3       # 只跑前 3 条，先看看通不通
    python scripts/run_eval.py --out data/eval/report.json

指标口径：
- Spearman ρ：把「AI 分」和「人工分」各自排名后算相关系数（不依赖 scipy，自己排）。
  1.0 = 排序完全一致；0 = 无关；负数 = 反着排。样本 10 条时，ρ ≥ 0.7 算可用。
- MAE：平均绝对误差，单位是「分」（满分 5）。
- 档位一致率：AI 分按 <2 → bad、<4 → ok、其余 good 映射回三档，跟人工标注对比。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph.nodes.evaluate_answer import evaluate_answer  # noqa: E402
from src.log import get_logger  # noqa: E402
from src.model import LEVEL_TO_SCORE, Question, QuestionKind  # noqa: E402
from src.model.gold import load_gold_set  # noqa: E402

logger = get_logger("run_eval")

GOLD_DIR = ROOT / "src" / "eval" / "gold"
JD_FOR_EVAL = {"role_title": "AI Agent 开发实习生", "seniority": "intern"}


def _state_for(item) -> dict:
    """把一条 gold 拼成 evaluate_answer 能吃的 state：只有一个回合，答案就是待评文本。"""
    question = Question(
        text=item.question_text,
        dimension=item.scoring_dimension,
        difficulty=item.question_difficulty,
        evidence_ref="gold",
        kind=QuestionKind.SCENARIO,
    )
    turn = {
        "question": question.model_dump(mode="json"),
        "answer": item.candidate_answer,
        "score": None,
        "skipped": False,
    }
    return {"jd_profile": JD_FOR_EVAL, "current_question": turn["question"], "turns": [turn]}


def _predict(item) -> dict:
    """跑一次评分节点，返回这一条的预测结果。"""
    state = _state_for(item)
    out = evaluate_answer(state)
    score = (out.get("turns") or [{}])[0].get("score") if out.get("turns") else None
    if not score:
        return {"pred": None, "valid": False, "quote": "", "comment": "没拿到评分"}
    return {
        "pred": float(score["avg"]),
        "valid": bool(score["valid"]),
        "quote": score["dimension_scores"] and next(iter(score["dimension_scores"].values())).get("evidence_quote", ""),
        "comment": next(iter(score["dimension_scores"].values())).get("comment", "") if score["dimension_scores"] else "",
    }


def _ranks(values: list[float]) -> list[float]:
    """平均秩（并列取平均），用于 Spearman。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


def _spearman(xs: list[float], ys: list[float]) -> float:
    return _pearson(_ranks(xs), _ranks(ys))


def _level_of(score: float) -> str:
    if score < 2:
        return "bad"
    if score < 4:
        return "ok"
    return "good"


def main() -> int:
    parser = argparse.ArgumentParser(description="用 gold 集评测 AI 评分的一致性")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0 = 全部）")
    parser.add_argument("--out", default="", help="把明细写成 JSON 的路径")
    args = parser.parse_args()

    items = load_gold_set(GOLD_DIR)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("没有 gold 样本可评。")
        return 1

    rows = []
    for i, item in enumerate(items, 1):
        logger.info("[%d/%d] %s（%s / 人工 %s）", i, len(items), item.question_id, item.scoring_dimension.value, item.human_quality_level)
        result = _predict(item)
        human = LEVEL_TO_SCORE[item.human_quality_level]
        rows.append(
            {
                "id": item.question_id,
                "dimension": item.scoring_dimension.value,
                "human_level": item.human_quality_level,
                "human_score": human,
                **result,
            }
        )
        logger.info(
            "        AI %s 分 / 人工 %s 分%s",
            "—" if result["pred"] is None else f"{result['pred']:.1f}",
            human,
            "" if result["valid"] else "（无有效证据）",
        )

    valid_rows = [r for r in rows if r["pred"] is not None and r["valid"]]
    print("\n" + "=" * 72)
    print(f"{'样本':<10}{'维度':<22}{'人工':<8}{'AI':<8}{'档位一致'}")
    print("-" * 72)
    for r in rows:
        pred = "—" if r["pred"] is None else f"{r['pred']:.1f}"
        same = "✓" if r["pred"] is not None and _level_of(r["pred"]) == r["human_level"] else ""
        print(f"{r['id']:<10}{r['dimension']:<22}{r['human_score']:<8.0f}{pred:<8}{same}")
    print("=" * 72)

    print(f"样本数      {len(rows)}")
    print(f"有效评分    {len(valid_rows)}/{len(rows)}")
    if len(valid_rows) >= 2:
        xs = [r["pred"] for r in valid_rows]
        ys = [float(r["human_score"]) for r in valid_rows]
        rho = _spearman(xs, ys)
        mae = sum(abs(x - y) for x, y in zip(xs, ys)) / len(valid_rows)
        exact = sum(1 for r in valid_rows if _level_of(r["pred"]) == r["human_level"])
        order = {"bad": 0, "ok": 1, "good": 2}
        gaps = [abs(order[_level_of(r["pred"])] - order[r["human_level"]]) for r in valid_rows]
        print(f"Spearman ρ  {rho:.3f}   （10 条样本时 ρ ≥ 0.70 算可用）")
        print(f"MAE         {mae:.2f}   （满分 5 分）")
        print(f"档位完全一致 {exact}/{len(valid_rows)}")
        print(f"档位相差一档 {gaps.count(1)}/{len(valid_rows)}   相差两档 {gaps.count(2)}/{len(valid_rows)}")
    else:
        print("有效样本不足 2 条，跳过统计。")

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n明细已写入 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
