"""Verify portable runtime completeness for offline use.

Checks:
1. portable Python exists and runs
2. portable Node exists and runs, if present
3. key site-packages import through portable Python
4. Maker MCP stdio launcher exists, if present
5. portable/ size is under budget
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _python_exe() -> Path:
    if sys.platform.startswith("win"):
        return PROJECT_ROOT / "portable" / "python" / "python.exe"
    return PROJECT_ROOT / "portable" / "python" / "bin" / "python3"


def _node_exe() -> Path:
    if sys.platform.startswith("win"):
        return PROJECT_ROOT / "portable" / "node" / "node.exe"
    return PROJECT_ROOT / "portable" / "node" / "bin" / "node"


def _maker_mcp_stdio() -> Path:
    if sys.platform.startswith("win"):
        return PROJECT_ROOT / "portable" / "maker-mcp" / "taptap-maker.cmd"
    return PROJECT_ROOT / "portable" / "maker-mcp" / "taptap-maker.sh"


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def check_python() -> Tuple[bool, str]:
    py = _python_exe()
    if not py.exists():
        return False, f"portable Python missing: {py}"
    try:
        result = subprocess.run(
            [str(py), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, f"portable Python failed to run: {result.stderr}"
        return True, f"portable Python OK ({result.stdout.strip()})"
    except Exception as exc:
        return False, f"portable Python exception: {exc}"


def check_node() -> Tuple[bool, str]:
    node = _node_exe()
    if not node.exists():
        return True, "portable Node missing (optional, not required for backend)"
    try:
        result = subprocess.run(
            [str(node), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, f"portable Node failed: {result.stderr}"
        return True, f"portable Node OK ({result.stdout.strip()})"
    except Exception as exc:
        return False, f"portable Node exception: {exc}"


def check_site_packages() -> Tuple[bool, str]:
    py = _python_exe()
    if not py.exists():
        return False, "skip (no portable Python)"
    target = PROJECT_ROOT / "portable" / "python"
    if sys.platform.startswith("win"):
        site_dir = target / "Lib" / "site-packages"
    else:
        py_dir = next((target / "lib").glob("python*"), None)
        site_dir = py_dir / "site-packages" if py_dir else None
    if site_dir is None or not site_dir.exists():
        return False, f"site-packages missing: {site_dir}"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site_dir)
    result = subprocess.run(
        [str(py), "-c", "import fastapi, uvicorn, pydantic, httpx, requests"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return False, f"site-packages import failed: {result.stderr}"
    return True, "site-packages import OK (fastapi, uvicorn, pydantic, httpx, requests)"


def check_maker_mcp() -> Tuple[bool, str]:
    stdio = _maker_mcp_stdio()
    if not stdio.exists():
        return True, "Maker MCP stdio launcher missing (ok if remote-only)"
    return True, f"Maker MCP stdio OK: {stdio}"


def check_budget(max_bytes: int) -> Tuple[bool, str]:
    portable = PROJECT_ROOT / "portable"
    total = _dir_size(portable)
    if total == 0:
        return False, "portable/ directory empty or missing"
    mb = total / (1024 * 1024)
    if total > max_bytes:
        return False, f"portable/ size {mb:.1f}MB exceeds budget {max_bytes // (1024 * 1024)}MB"
    return True, f"portable/ size {mb:.1f}MB (budget {max_bytes // (1024 * 1024)}MB)"


def main(max_budget_mb: int = 500) -> int:
    print("=" * 60)
    print(f"TTMEvolve portable runtime verification (budget {max_budget_mb}MB)")
    print("=" * 60)
    checks: List[Tuple[bool, str]] = [
        check_python(),
        check_node(),
        check_site_packages(),
        check_maker_mcp(),
        check_budget(max_budget_mb * 1024 * 1024),
    ]
    failures = 0
    for ok, msg in checks:
        marker = "OK" if ok else "FAIL"
        print(f"  [{marker}] {msg}")
        if not ok:
            failures += 1
    print("=" * 60)
    if failures == 0:
        print("portable runtime verification passed (offline-ready)")
        return 0
    print(f"{failures} check(s) failed")
    return 1


if __name__ == "__main__":
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    raise SystemExit(main(budget))
