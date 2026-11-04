"""D3 验收：把 JD + 简历各解析一份，检查 profile 字段非空且合理。

跑法（在项目根目录）：
    python scripts/check_parse.py
    python scripts/check_parse.py --jd data/jds/02-ai-agent-develop.md --resume data/resumes/sample-01-strong.md

验收标准（DESIGN.md §9 的 D3）：喂一份 JD+简历，输出两个 profile，
字段非空且合理。这里把"合理"写成 7 条硬检查——不靠肉眼看。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让人能直接 python scripts/check_parse.py

from src.graph.nodes.parse_inputs import parse_inputs  # noqa: E402
from src.model import Seniority  # noqa: E402

fails: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd", default="data/jds/01-ai-agent-intern.md")
    ap.add_argument("--resume", default="data/resumes/sample-02-medium.md")
    args = ap.parse_args()

    jd_text = (ROOT / args.jd).read_text(encoding="utf-8")
    resume_text = (ROOT / args.resume).read_text(encoding="utf-8")
    print(f"JD     : {args.jd}")
    print(f"简历   : {args.resume}\n")

    # 走真正的节点函数：dict 进、dict 出，跟图里看到的行为完全一致
    out = parse_inputs({"jd_text": jd_text, "resume_text": resume_text})
    jd, resume = out["jd_profile"], out["resume_profile"]

    print("== JD profile ==")
    print(f"  role_title : {jd['role_title']}")
    print(f"  seniority  : {jd['seniority']}")
    print(f"  must_skills: {[(s['id'], s['name'], s['weight']) for s in jd['must_skills']]}")
    print(f"  nice_skills: {[(s['id'], s['name'], s['weight']) for s in jd['nice_skills']]}")
    print(f"  domain     : {jd['domain_keywords']}")
    print(f"  resp 条数  : {len(jd['responsibilities'])}")

    print("\n== 简历 profile ==")
    print(f"  education  : {resume['education']}")
    print(f"  skills     : {resume['skills']}")
    print(f"  projects   : {[(p['id'], p['name'], p['tech_stack']) for p in resume['projects']]}")
    print(f"  my_role    : {[(p['id'], p['my_role']) for p in resume['projects']]}")

    print("\n== 硬检查 ==")
    check(bool(jd["role_title"]), "role_title 非空")
    check(jd["seniority"] in {s.value for s in Seniority}, "seniority 是合法的枚举值")
    check(len(jd["must_skills"]) >= 1, "must_skills 至少 1 条")
    ids = [s["id"] for s in jd["must_skills"] + jd["nice_skills"]]
    check(len({s["name"].lower() for s in jd["must_skills"] + jd["nice_skills"]}) == len(
        jd["must_skills"] + jd["nice_skills"]), "技能没有重复项")
    check(all(1 <= s["weight"] <= 5 for s in jd["must_skills"] + jd["nice_skills"]), "weight 都在 1-5")
    check(len(set(ids)) == len(ids), "技能 id 不重复")
    check(len(jd["responsibilities"]) >= 1, "responsibilities 至少 1 条")
    check(len(resume["projects"]) >= 1, "简历至少有 1 个项目")
    pids = [p["id"] for p in resume["projects"]]
    check(len(set(pids)) == len(pids), "项目 id 不重复")
    check(all(p["name"] for p in resume["projects"]), "每个项目都有 name")

    # state 要能塞进 checkpointer，必须是可 JSON 序列化的 dict
    try:
        json.dumps(out, ensure_ascii=False)
        check(True, "返回的 dict 可以 JSON 序列化（能进 checkpointer）")
    except TypeError as exc:  # pragma: no cover
        print(f"  FAIL  返回的 dict 可以 JSON 序列化：{exc}")
        fails.append("json")

    print()
    if fails:
        print(f"结果：{len(fails)} 条没通过 → {fails}")
        return 1
    print("结果：全绿。D3 验收通过，可以进 D4（match_gap）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
