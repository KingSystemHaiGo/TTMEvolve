"""
tests/test_resource_registry.py — 资源注册表测试
"""

from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.resource_registry import ResourceRegistry


def test_register_and_rollback():
    tmp = Path(tempfile.mkdtemp())
    try:
        reg = ResourceRegistry(tmp)
        r1 = reg.register("prompt_v1", "prompt", "hello world", source="test")
        assert r1.version == "v1"

        r2 = reg.register("prompt_v1", "prompt", "hello world v2", source="test")
        assert r2.version == "v2"
        assert r2.rollback_target == "v1"

        latest = reg.get("prompt_v1")
        assert latest.version == "v2"

        rolled = reg.rollback("prompt_v1")
        assert rolled.version == "v3"
        assert "v1" in rolled.source

        print("[PASS] register and rollback")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_register_and_rollback()
    print("[PASS] all resource registry tests")
