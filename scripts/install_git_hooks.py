"""把隐私扫描装成 git 钩子：pre-push 时自动跑，命中就拦下推送。

用法（只需一次）：
    python scripts/install_git_hooks.py

之后 `git push` 前会自动执行 scripts/check_privacy.py；
想临时跳过：`git push --no-verify`。
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".git" / "hooks" / "pre-push"

TEMPLATE = """#!/bin/sh
# 由 scripts/install_git_hooks.py 生成：推送前扫描隐私与密钥
"{python}" "{script}" || {{
  echo ""
  echo "✗ 推送被拦下：即将推送的内容里有隐私信息或密钥。"
  echo "  修好后再 push；确有需要可用 git push --no-verify 跳过。"
  exit 1
}}
"""


def main() -> int:
    if not (ROOT / ".git").is_dir():
        print("当前目录不是 git 仓库，无法安装钩子。")
        return 1

    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(
        TEMPLATE.format(
            python=Path(sys.executable).as_posix(),
            script=(ROOT / "scripts" / "check_privacy.py").as_posix(),
        ),
        encoding="utf-8",
        newline="\n",
    )
    HOOK.chmod(HOOK.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"已安装 pre-push 钩子：{HOOK}")
    print(f"解释器：{sys.executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
