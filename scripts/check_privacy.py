"""提交前隐私扫描：手机号、邮箱、真实姓名/学校/公司、API key。

用法：
    python scripts/check_privacy.py            # 扫 git 跟踪的文件（默认）
    python scripts/check_privacy.py --staged   # 只扫已暂存的文件

退出码 0 = 干净；1 = 命中，会打印文件名和行号（值本身打码）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (名字, 正则, 说明)
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("真实姓名", re.compile("\u66f9\u8d24\u4eae")),
    ("学校", re.compile("\u6e58\u6f6d\u5927\u5b66")),
    ("真实公司", re.compile("\u597d\u5b66\u661f\u57ce")),
    ("API Key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
]

# 允许的占位符：虚构样本里的 example 邮箱、其他 @example.com
ALLOW_PATTERNS = [
    re.compile(r"@example\.(com|org|net)$"),
    re.compile(r"^sk-(test|dummy|xxx)", re.IGNORECASE),
]

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".toml", ".txt", ".ini", ".cfg", ".sql", ".sh", ".ps1", ".env", ".example", ""}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".pdf", ".docx", ".xlsx", ".pkl"}


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def _targets(staged: bool) -> list[Path]:
    if staged:
        names = _git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    else:
        names = _git("ls-files")
    paths = []
    for name in names:
        path = ROOT / name
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix != "":
            continue
        if path.is_file():
            paths.append(path)
    return paths


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


def _allowed(value: str, rule: str) -> bool:
    if rule in {"邮箱", "API Key"}:
        return any(p.search(value) for p in ALLOW_PATTERNS)
    return False


def scan(staged: bool) -> int:
    hits: list[str] = []
    checked = 0
    for path in _targets(staged):
        checked += 1
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in RULES:
                for match in pattern.finditer(line):
                    value = match.group(0)
                    if _allowed(value, rule):
                        continue
                    hits.append(f"{rel}:{lineno}  [{rule}] {_mask(value)}")

    scope = "已暂存" if staged else "git 跟踪"
    if hits:
        print(f"隐私扫描失败：{scope}的 {checked} 个文件里命中 {len(hits)} 处\n")
        for hit in hits:
            print(f"  {hit}")
        print("\n修法：删掉/换成占位符，或把文件加进 .gitignore（真实简历、真实 JD 不要进仓库）。")
        return 1
    print(f"隐私扫描通过：{scope}的 {checked} 个文件，无手机号/邮箱/真名/学校/公司/密钥。")
    return 0


if __name__ == "__main__":
    sys.exit(scan(staged="--staged" in sys.argv))
