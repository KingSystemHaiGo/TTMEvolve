"""
scripts/prepare_offline_env.py — 预置离线运行环境（兼容入口）

桌面级软件应该即开即用。此脚本是对 build_embedded.py --mode=deps-only 的兼容包装，
会一次性准备好：
1. 所有 Python 依赖的 wheel 到 vendor/wheels/
2. 默认本地模型 MiniCPM5-1B-Q4_K_M.gguf 到 models/
3. embedding 模型到 vendor/embeddings/
4. Playwright Chromium 浏览器到 vendor/playwright/

并生成 vendor/manifest.json 和 .env.embedded 供启动脚本使用。

用法：
    python scripts/prepare_offline_env.py
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    build_script = _PROJECT_ROOT / "scripts" / "build_embedded.py"
    print("[prepare] Preparing offline environment for TTMEvolve...")
    print("[prepare] Delegating to build_embedded.py --mode=deps-only")
    try:
        result = subprocess.run(
            [sys.executable, str(build_script), "--mode", "deps-only"],
            cwd=str(_PROJECT_ROOT),
        )
        return result.returncode
    except KeyboardInterrupt:
        print("\n[prepare] Aborted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
