"""验收脚本：gold 集的格式与覆盖度（不需要模型、不需要数据库，秒跑）。"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.model import DIMENSIONS, GoldItem  # noqa: E402
from src.model.gold import load_gold_item  # noqa: E402

GOLD_DIR = ROOT / "src" / "eval" / "gold"
LEVELS = ["bad", "ok", "good"]


def _squash(text: str) -> str:
    """去掉所有空白后比较，避免"照抄时换行位置不同"被误判为错。"""
    return "".join(text.split())


def main() -> int:
    parser = ArgumentParser(description="校验 gold 集格式与覆盖度")
    parser.add_argument("--dir", default=str(GOLD_DIR), help="gold 集目录")
    parser.add_argument("--target", type=int, default=10, help="目标条数（MVP 是 10 条）")
    args = parser.parse_args()

    gold_dir = Path(args.dir)
    files = sorted(gold_dir.glob("*.yaml"))
    if not files:
        print(f"✗ {gold_dir} 下没有 *.yaml —— gold 集还没开始标")
        return 1

    items: list[GoldItem] = []
    errors: list[str] = []
    seen: set[str] = set()

    for path in files:
        try:
            item = load_gold_item(path)
        except Exception as exc:  # noqa: BLE001 - 校验脚本要把所有问题一次性列完
            errors.append(f"{path.name}: {exc}")
            continue

        if item.question_id in seen:
            errors.append(f"{path.name}: question_id {item.question_id} 重复")
        seen.add(item.question_id)

        # 证据必须是候选人原话的子串：抄不准说明你没核对，标注就没意义了
        if item.human_evidence_quote and _squash(item.human_evidence_quote) not in _squash(
            item.candidate_answer
        ):
            errors.append(
                f"{path.name}: human_evidence_quote 不在 candidate_answer 里"
                f"（应为原话照抄）：{item.human_evidence_quote[:30]!r}"
            )

        items.append(item)
        preview = item.question_text.replace("\n", " ")[:24]
        print(
            f"✓ {path.stem:<10} {item.scoring_dimension.value:<22} "
            f"{item.human_quality_level:<4} {item.human_score:.1f}  「{preview}…」"
        )

    if errors:
        print()
        for message in errors:
            print(f"✗ {message}")
        print(f"\n结果：{len(errors)} 个格式错误，先修好再谈评测。")
        return 1

    # ---- 进度（不算失败）：还差哪些维度/档位/条数
    by_dimension = {d.value: 0 for d in DIMENSIONS}
    by_level = {level: 0 for level in LEVELS}
    for item in items:
        by_dimension[item.scoring_dimension.value] += 1
        by_level[item.human_quality_level] += 1

    missing_dims = [d for d, n in by_dimension.items() if n == 0]
    missing_levels = [level for level, n in by_level.items() if n == 0]

    print()
    print(f"条数      {len(items)}/{args.target}  {'✓' if len(items) >= args.target else '待补'}")
    print(f"维度覆盖  {len(by_dimension) - len(missing_dims)}/5  " + "  ".join(
        f"{d}×{n}" for d, n in by_dimension.items()
    ))
    if missing_dims:
        print(f"          缺：{', '.join(missing_dims)}")
    print(f"档位覆盖  {len(by_level) - len(missing_levels)}/3  " + "  ".join(
        f"{level}×{n}" for level, n in by_level.items()
    ))
    if missing_levels:
        print(f"          缺：{', '.join(missing_levels)}")

    print()
    if len(items) >= args.target and not missing_dims and not missing_levels:
        print(f"结果：{len(items)} 条格式全绿，覆盖度达标，可以跑评测了。")
    else:
        print("结果：格式全绿；标注还没标完（上面的「待补 / 缺」就是还差的部分）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
