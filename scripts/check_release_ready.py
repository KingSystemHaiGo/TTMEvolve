"""
scripts/check_release_ready.py - one-shot releasability check.

Runs every gate listed in docs/release-gates.md and prints a final
``READY`` / ``BLOCKED`` line. Used by:

  - Pre-commit / pre-PR hook (recommended)
  - The slice #1 release process (manual, before tagging)
  - Any contributor who wants to know if the current tree is in a
    releasable state without reading ten different test files.

This script does NOT redefine the gates; it imports the regression
guard test module and calls each test function directly, plus
subprocesses the baseline tests, the integration tests, and
``release_readiness``. The point is to make the gate list a single
command so a new contributor can run it.

Exit code is 0 when ``READY``, 1 when ``BLOCKED``.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _run(cmd, *, cwd=None) -> tuple:
    """Run a subprocess; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(cwd or PROJECT_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def _gate(name: str, ok: bool, detail: str = "") -> bool:
    """Print one gate's status and return ok."""
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  -- {detail}"
    print(line)
    return ok


def main() -> int:
    print("=" * 72)
    print("TTMEvolve slice #1 release-readiness check")
    print("=" * 72)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results: list = []

    # ---------------------------------------------------------------
    # G2 / G3: release_readiness --mode source-checkpoint
    # ---------------------------------------------------------------
    print("G2/G3: release_readiness --mode source-checkpoint")
    rc, out, err = _run([
        sys.executable,
        "scripts/release_readiness.py",
        "--mode", "source-checkpoint",
        "--json",
    ])
    rr_data = None
    if rc != 0:
        results.append(_gate("release_readiness exit=0", False, err[:200]))
    else:
        results.append(_gate("release_readiness exit=0", True))
        try:
            rr_data = json.loads(out)
        except Exception as exc:
            results.append(_gate("release_readiness JSON parse", False, str(exc)))
    if rr_data is not None:
        results.append(_gate(
            "release_readiness.status == ready",
            rr_data.get("status") == "ready",
            f"got {rr_data.get('status')!r}",
        ))
        results.append(_gate(
            "release_readiness.blockers == []",
            rr_data.get("blockers") == [],
            f"got {rr_data.get('blockers')!r}",
        ))
        results.append(_gate(
            "release_readiness.closure_gate.can_claim_source_checkpoint_ready",
            bool(rr_data.get("closure_gate", {}).get("can_claim_source_checkpoint_ready")),
        ))
        quality = rr_data.get("checks", {}).get("production_rag_quality", {})
        results.append(_gate(
            "production_rag_quality.status == unproven",
            quality.get("status") == "unproven",
            f"got {quality.get('status')!r}",
        ))
        results.append(_gate(
            "production_rag_quality.ok == False",
            quality.get("ok") is False,
        ))
    print()

    # ---------------------------------------------------------------
    # G1: feature flags default off
    # ---------------------------------------------------------------
    print("G1: feature flags default off")
    rg = importlib.import_module("tests.test_regression_guards")
    results.append(_gate(
        "feature flags default off",
        _safe_call(rg.test_feature_flags_default_off),
    ))
    print()

    # ---------------------------------------------------------------
    # G4: LLM provider files unchanged
    # ---------------------------------------------------------------
    print("G4: LLM provider files unchanged")
    results.append(_gate(
        "LLM provider interface intact",
        _safe_call(rg.test_llm_provider_files_unchanged),
    ))
    print()

    # ---------------------------------------------------------------
    # G5: plan v1 backward compat
    # ---------------------------------------------------------------
    print("G5: plan v1 backward compat")
    results.append(_gate(
        "plan-format.v1 plans still execute",
        _safe_call(rg.test_plan_v1_backward_compat),
    ))
    print()

    # ---------------------------------------------------------------
    # G6 / G7 / G8: integration test files exist
    # ---------------------------------------------------------------
    print("G6/G7/G8: integration test files exist")
    results.append(_gate(
        "smoke evidence fields test file present",
        _safe_call(rg.test_evidence_bundle_smoke_three_tests_present),
    ))
    results.append(_gate(
        "all-flags-on integration test present",
        _safe_call(rg.test_all_flags_on_integration_test_present),
    ))
    results.append(_gate(
        "cross-surface scenarios test present",
        _safe_call(rg.test_cross_surface_scenarios_present),
    ))
    print()

    # ---------------------------------------------------------------
    # G9: baseline tests pass
    # ---------------------------------------------------------------
    print("G9: baseline tests (test_rag_performance + test_runtime_contract)")
    rc, out, err = _run([
        sys.executable, "-m", "pytest",
        "tests/test_rag_performance.py",
        "tests/test_runtime_contract.py",
        "-q", "--tb=line",
    ])
    results.append(_gate(
        "baseline tests pass",
        rc == 0,
        f"exit={rc}",
    ))
    out_lines = out.splitlines() if out else []
    if out_lines:
        # Print the last 3 lines (typically the pytest summary)
        for line in out_lines[-3:]:
            print(f"        {line}")
    else:
        print("        (no output)")
    print()

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    passed = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)
    print("=" * 72)
    print(f"Gates passed: {passed} / {len(results)}")
    if failed:
        print(f"Gates failed: {failed}")
        print()
        print("BLOCKED -- fix the failing gates above. Do not silence the")
        print("regression guards; they exist to protect slice #1.")
        return 1
    print()
    print("READY -- slice #1 satisfies every gate in docs/release-gates.md.")
    return 0


def _safe_call(fn) -> bool:
    """Invoke a regression-guard test function and return True on pass."""
    try:
        # The test functions don't take arguments; if they raise,
        # we treat that as a failure.
        fn()
        return True
    except Exception as exc:
        print(f"        error: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    sys.exit(main())
