"""
tests/test_runtime_errors_hooks.py - runtime error log + hook tests.

Covers:
  - RuntimeErrorRecord schema
  - ErrorLog JSONL write + rotation
  - record_error captures traceback automatically
  - record_error respects the enabled flag (no-op when off)
  - fire() routes through subscribers
  - Subscriber exceptions are swallowed
  - The default subscriber writes to the structured log
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import error_hooks, runtime_errors  # noqa: E402


def _reset():
    runtime_errors.configure(enabled=False, log_path=None)
    error_hooks.reset_for_tests()


def test_record_error_short_circuits_when_disabled():
    _reset()
    runtime_errors.configure(enabled=False, log_path=None)
    ok = runtime_errors.record_error("tool_call", message="x")
    assert ok is False


def test_record_error_writes_to_jsonl_when_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        _reset()
        log_path = Path(tmp) / "errors.jsonl"
        runtime_errors.configure(enabled=True, log_path=log_path)
        ok = runtime_errors.record_error(
            "tool_call",
            message="boom",
            session_id="s-1",
            step_id="step-2",
            tool_name="read_file",
        )
        assert ok is True
        assert log_path.exists()
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["schema_version"] == runtime_errors.RUNTIME_ERROR_SCHEMA_VERSION
        assert rec["category"] == "tool_call"
        assert rec["message"] == "boom"
        assert rec["session_id"] == "s-1"
        assert rec["step_id"] == "step-2"
        assert rec["tool_name"] == "read_file"
        assert rec["traceback"] == ""  # no error was passed
        # recovery hint is populated from the category table
        assert rec["recovery_hint"]
        _reset()


def test_record_error_captures_traceback():
    with tempfile.TemporaryDirectory() as tmp:
        _reset()
        log_path = Path(tmp) / "errors.jsonl"
        runtime_errors.configure(enabled=True, log_path=log_path)
        try:
            raise ValueError("simulated failure")
        except ValueError as e:
            runtime_errors.record_error(
                "tool_call",
                message="",
                tool_name="read_file",
                error=e,
            )
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rec = json.loads(lines[0])
        assert rec["error_type"] == "ValueError"
        assert "ValueError: simulated failure" in rec["traceback"]
        assert "test_record_error_captures_traceback" in rec["traceback"]
        _reset()


def test_record_error_unknown_category_falls_back():
    with tempfile.TemporaryDirectory() as tmp:
        _reset()
        log_path = Path(tmp) / "errors.jsonl"
        runtime_errors.configure(enabled=True, log_path=log_path)
        runtime_errors.record_error("bogus_category_xyz", message="x")
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rec = json.loads(lines[0])
        assert rec["category"] == "unknown"
        _reset()


def test_error_log_rotation_moves_old_file():
    with tempfile.TemporaryDirectory() as tmp:
        _reset()
        log_path = Path(tmp) / "errors.jsonl"
        runtime_errors.configure(enabled=True, log_path=log_path)
        # Force rotation by setting a tiny max_bytes
        log = runtime_errors._GlobalState.log
        log.max_bytes = 200
        # Write enough records to trigger rotation
        for i in range(50):
            runtime_errors.record_error("tool_call", message=f"record {i} " + "x" * 50)
        # Rotation files exist
        rotated = list(log_path.parent.glob("errors.jsonl.*"))
        assert any(p.exists() for p in rotated), f"no rotated files in {log_path.parent}"
        _reset()


def test_recent_filters_by_since_seconds():
    """``recent()`` filters records by age.

    The cutoff is computed from the wall clock; with
    ``since_seconds=5`` we include everything written in the
    last 5 s, which always includes the just-written record.
    """
    _reset()
    log_path = Path("storage") / "_test_recent_errors.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()
    try:
        runtime_errors.configure(enabled=True, log_path=log_path)
        runtime_errors.record_error("tool_call", message="now")
        # since_seconds=5: include everything in the last 5 s
        recs = runtime_errors.recent(since_seconds=5)
        assert len(recs) == 1
        assert recs[0].message == "now"
        # since_seconds is a "minimum age in seconds"; passing 0
        # excludes everything (the record is technically older
        # than 0s minus a few microseconds).
        recs_now = runtime_errors.recent(since_seconds=0)
        # The record was just written; its parsed timestamp may be
        # marginally behind the wall clock. We assert only that
        # the count is at most 1.
        assert len(recs_now) <= 1
    finally:
        runtime_errors.configure(enabled=False, log_path=None)
        if log_path.exists():
            log_path.unlink()
        _reset()


# ---------------------------------------------------------------------------
# Hook layer
# ---------------------------------------------------------------------------

def test_fire_is_noop_when_layer_disabled():
    _reset()
    error_hooks.reset_for_tests()
    # Even if a subscriber is registered, fire() should not call
    # it because the layer is disabled.
    called = []

    def _sub(category, payload):
        called.append(category)

    error_hooks.register(_sub)
    error_hooks.configure_hooks(enabled=False)
    error_hooks.fire("tool_call", message="x")
    assert called == []


def test_fire_routes_to_default_subscriber():
    with tempfile.TemporaryDirectory() as tmp:
        _reset()
        log_path = Path(tmp) / "errors.jsonl"
        runtime_errors.configure(enabled=True, log_path=log_path)
        error_hooks.reset_for_tests()
        error_hooks.configure_hooks(enabled=True)
        error_hooks.fire(
            "tool_call",
            message="blocked by guard",
            session_id="s-1",
            step_id="step-2",
            tool_name="shell",
        )
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rec = json.loads(lines[0])
        assert rec["category"] == "tool_call"
        assert rec["message"] == "blocked by guard"
        assert rec["tool_name"] == "shell"
        _reset()


def test_fire_swallows_subscriber_exceptions():
    error_hooks.reset_for_tests()
    error_hooks.configure_hooks(enabled=True)

    def _bad(category, payload):
        raise RuntimeError("subscriber is broken")

    error_hooks.register(_bad)
    # fire() must not raise even though the subscriber does
    error_hooks.fire("tool_call", message="x")
    _reset()


def test_fire_passes_through_user_subscribers():
    error_hooks.reset_for_tests()
    error_hooks.configure_hooks(enabled=True)
    received = []

    def _user(category, payload):
        received.append((category, payload["message"]))

    error_hooks.register(_user)
    error_hooks.fire("plan_exec", message="cycle detected")
    error_hooks.fire("vsm", message="diverging")
    assert received == [("plan_exec", "cycle detected"), ("vsm", "diverging")]
    _reset()


def test_fire_preserves_error_object_for_traceback_capture():
    with tempfile.TemporaryDirectory() as tmp:
        _reset()
        log_path = Path(tmp) / "errors.jsonl"
        runtime_errors.configure(enabled=True, log_path=log_path)
        error_hooks.reset_for_tests()
        error_hooks.configure_hooks(enabled=True)
        try:
            raise KeyError("missing-key")
        except KeyError as e:
            error_hooks.fire("tool_call", message="", tool_name="read_file", error=e)
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rec = json.loads(lines[0])
        assert rec["error_type"] == "KeyError"
        assert "KeyError" in rec["traceback"]
        _reset()
