"""
scripts/check_model.py — 检查本地模型文件是否存在

退出码 0：存在；1：不存在。
"""

from __future__ import annotations
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config


def main() -> int:
    config = Config(str(_PROJECT_ROOT / "config.json"))
    model_path = config.local_model_path()
    if model_path.exists():
        print(f"OK: {model_path}")
        return 0
    print(f"MISSING: {model_path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
