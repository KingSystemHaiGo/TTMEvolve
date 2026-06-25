"""build_all.py — 一键构建 portable runtime

按顺序执行：
1. download + extract Python embedded
2. download + extract Node embedded
3. install site-packages via pip
4. (optional) download Maker MCP stdio

每个 step 是独立脚本，可以单独重跑。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

STEPS = [
    ("Python embedded", SCRIPTS_DIR / "build_python.py"),
    ("Node embedded", SCRIPTS_DIR / "build_node.py"),
    ("site-packages (pip)", SCRIPTS_DIR / "build_site_packages.py"),
]


def main() -> int:
    for label, script in STEPS:
        print(f"\n{'=' * 60}\n[build_all] {label}\n{'=' * 60}")
        result = subprocess.run([sys.executable, str(script)], check=False)
        if result.returncode != 0:
            print(f"[build_all] {label} failed (exit {result.returncode})")
            return result.returncode
    print(f"\n[build_all] all steps passed")
    print(f"[build_all] next: python scripts/build-portable/verify_portable.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())