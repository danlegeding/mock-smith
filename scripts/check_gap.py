"""D4 验收：match_gap 有没有把「有 / 沾边 / 没有」判对。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.graph.nodes.match_gap import match_gap  # noqa: E402

JD_PATH = ROOT / "data" / "jds" / "01-ai-agent-intern.md"
RESUME_PATH = ROOT / "data" / "resumes" / "sample-02-medium.md"
CACHE_DIR = ROOT / ".cache" / "parse"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def _parse_cached(path: Path, kind: str) -> dict:
    """解析一次就存盘，之后直接读缓存（只按文件修改时间失效）。"""
    from src.graph.nodes.parse_inputs import extract_jd_profile, extract_resume_profile

    cache = CACHE_DIR / f"{kind}-{path.stem}.json"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return json.loads(cache.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    profile = extract_jd_profile(text) if kind == "jd" else extract_resume_profile(text)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return profile.model_dump(mode="json")


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def find_gap(gaps: list[dict], keyword: str) -> dict | None:
    """按关键字找一条（关键字出现在技能名里就算）。"""
    for gap in gaps:
        if _norm(keyword) in _norm(gap["skill"]):
            return gap
    return None


def main() -> int:
    jd_text = JD_PATH.read_text(encoding="utf-8")
    resume_text = RESUME_PATH.read_text(encoding="utf-8")

    jd_profile = _parse_cached(JD_PATH, "jd")
    resume_profile = _parse_cached(RESUME_PATH, "resume")

    n_must = len(jd_profile.get("must_skills", []))
    n_nice = len(jd_profile.get("nice_skills", []))
    print(f"JD must={n_must} nice={n_nice} | 简历 skills={len(resume_profile.get('skills', []))}")
    print("-" * 78)

    state = {
        "jd_profile": jd_profile,
        "resume_profile": resume_profile,
        "resume_text": resume_text,
    }
    out = match_gap(state)
    gaps = out["gap_map"]

    # 人眼先看一遍
    for gap in gaps:
        print(
            f"{gap['skill']:<28} {gap['match_level']:<8} p={gap['priority']} "
            f"evidence={gap['evidence']!r}"
        )
    print("-" * 78)

    check("返回的是 list[dict]", isinstance(gaps, list) and all(isinstance(g, dict) for g in gaps), str(type(gaps)))
    check("gap_map 非空", len(gaps) > 0, f"共 {len(gaps)} 条")

    # ① 覆盖性：JD 的每一条必须项都要有对应的一行
    gap_names = [_norm(g["skill"]) for g in gaps]
    missing_rows = [
        s["name"]
        for s in jd_profile.get("must_skills", [])
        if not any(_norm(s["name"]) in name or name in _norm(s["name"]) for name in gap_names)
    ]
    check("JD 的 must_skills 一条不漏", not missing_rows, f"漏了：{missing_rows}")

    # ② 不许重复：同一个技能不能出两行，否则"该问的"会被重复计数
    check("技能不重复", len(gap_names) == len(set(gap_names)), "有重复技能行")

    # ③ evidence 不许编：空串，或者原文里真的存在
    fake = [
        g["skill"]
        for g in gaps
        if g["evidence"] and g["evidence"] not in resume_text
    ]
    check("evidence 必须是简历原文的片段（不许编）", not fake, f"编造：{fake}")

    # ④ empty evidence ⇔ missing（双向）
    bad_pairs = [
        g["skill"]
        for g in gaps
        if (g["evidence"] == "") != (g["match_level"] == "missing")
    ]
    check("evidence 为空 ⇔ 判 missing", not bad_pairs, f"不一致：{bad_pairs}")

    # ⑤ 几条固定答案（契约）
    python_gap = find_gap(gaps, "python")
    check("Python → strong", python_gap is not None and python_gap["match_level"] == "strong", str(python_gap))

    docker_gap = find_gap(gaps, "docker")
    check("Docker → strong（简历技能区写了 Docker）", docker_gap is not None and docker_gap["match_level"] == "strong", str(docker_gap))

    pg_gap = find_gap(gaps, "postgres")
    check(
        "PostgreSQL → weak（简历只有 MySQL，属于沾边）",
        pg_gap is not None and pg_gap["match_level"] == "weak",
        f"实际 {pg_gap}（如果是 missing，说明 RELATED 表里没写 mysql）",
    )

    lg_gap = find_gap(gaps, "langgraph")
    check(
        "LangGraph → weak（简历只有 LangChain，属于沾边）",
        lg_gap is not None and lg_gap["match_level"] == "weak",
        f"实际 {lg_gap}（如果是 strong，说明简历里『正在学习 LangGraph』被误当成技能）",
    )

    # ⑥ 不是所有项都判 strong（否则等于没判）
    levels = {g["match_level"] for g in gaps}
    check("档位不是清一色 strong", len(levels) >= 2, f"出现档位：{sorted(levels)}")

    # ⑦ 优先级：must 的平均优先级要高于 nice
    must_avg = sum(g["priority"] for g in gaps if g["match_level"]) / max(len(gaps), 1)
    check("priority 在 1-5", all(1 <= g["priority"] <= 5 for g in gaps), "")
    del must_avg

    # ⑧ 每条都要给追问角度
    no_angle = [g["skill"] for g in gaps if not g.get("probe_angle")]
    check("probe_angle 都不为空", not no_angle, f"空：{no_angle}")

    # ⑨ 排序：priority 降序
    priorities = [g["priority"] for g in gaps]
    check("按 priority 降序排序", priorities == sorted(priorities, reverse=True), str(priorities))

    # ⑩ 可 JSON 序列化（state 要写进 checkpointer）
    try:
        json.dumps(out, ensure_ascii=False)
        check("结果可 JSON 序列化", True)
    except TypeError as exc:
        check("结果可 JSON 序列化", False, str(exc))

    passed = sum(1 for _, ok, _ in results if ok)
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ← {detail}" if not ok and detail else ""))
    print(f"\n{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
