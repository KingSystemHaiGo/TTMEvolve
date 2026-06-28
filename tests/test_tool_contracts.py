"""
tests/test_tool_contracts.py - tool contract tests (Phase R2).

Covers:
  - ToolContract dataclass + to_dict shape
  - PredicateRegistry (register / evaluate / has / names)
  - ContractStore (register / get / set_state / evaluate_preconditions)
  - ToolState enum
  - Executor preflight (propose_action rejects when state != AVAILABLE
    or when preconditions fail) — the Issue-5 fix

The preflight is the most important behavior: a tool whose
preconditions are not satisfied must be rejected by
``propose_action`` before any side effect or sandbox call.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.tool_contracts import (  # noqa: E402
    ContractStore,
    PredicateRegistry,
    ToolContract,
    ToolState,
    TOOL_CONTRACT_VERSION,
)


# ---------------------------------------------------------------------------
# Dataclass / to_dict
# ---------------------------------------------------------------------------

def test_tool_contract_to_dict_is_serializable():
    c = ToolContract(
        name="read_file",
        purpose="read a file from the project root",
        preconditions=["path_exists"],
        postconditions=["returns_observation"],
        state=ToolState.AVAILABLE,
        side_effects=False,
        risk_level="low",
    )
    d = c.to_dict()
    assert d["schema_version"] == TOOL_CONTRACT_VERSION
    assert d["name"] == "read_file"
    assert d["state"] == "available"
    assert d["preconditions"] == ["path_exists"]
    # Round-trips through JSON
    json.dumps(d)


def test_tool_state_enum_values():
    assert ToolState.AVAILABLE.value == "available"
    assert ToolState.NEEDS_CONFIG.value == "needs_config"
    assert ToolState.UNAVAILABLE.value == "unavailable"
    assert ToolState.BUSY.value == "busy"


# ---------------------------------------------------------------------------
# PredicateRegistry
# ---------------------------------------------------------------------------

def test_predicate_registry_register_and_evaluate():
    reg = PredicateRegistry()
    reg.register("path_exists", lambda ctx: ctx.get("exists", False))
    reg.register("maker_ready", lambda ctx: bool(ctx.get("maker_ready", True)))
    assert reg.has("path_exists")
    assert reg.has("maker_ready")
    assert not reg.has("unknown_predicate")
    assert reg.evaluate("path_exists", {"exists": True}) is True
    assert reg.evaluate("path_exists", {"exists": False}) is False
    assert reg.evaluate("unknown_predicate", {}) is True  # fail open


def test_predicate_registry_evaluate_swallows_exceptions():
    reg = PredicateRegistry()

    def _bad(ctx):
        raise RuntimeError("predicate broken")

    reg.register("bad", _bad)
    # Must fail open (return True) so a broken predicate does not
    # block the runtime. The error is silently swallowed.
    assert reg.evaluate("bad", {}) is True


# ---------------------------------------------------------------------------
# ContractStore
# ---------------------------------------------------------------------------

def test_contract_store_register_and_get():
    store = ContractStore()
    c = ToolContract(name="x", purpose="test", state=ToolState.AVAILABLE)
    store.register(c)
    assert store.has("x")
    assert store.get("x") is c
    assert store.get_state("x") == ToolState.AVAILABLE
    assert not store.has("y")


def test_contract_store_set_state():
    store = ContractStore()
    store.register(ToolContract(name="x"))
    store.set_state("x", ToolState.NEEDS_CONFIG)
    assert store.get_state("x") == ToolState.NEEDS_CONFIG
    store.set_state("x", ToolState.AVAILABLE)
    assert store.get_state("x") == ToolState.AVAILABLE


def test_contract_store_evaluate_preconditions_lists_each():
    store = ContractStore()
    reg = PredicateRegistry()
    reg.register("a", lambda ctx: bool(ctx.get("a", True)))
    reg.register("b", lambda ctx: bool(ctx.get("b", False)))
    store.register(ToolContract(
        name="x",
        preconditions=["a", "b"],
    ))
    results = store.evaluate_preconditions("x", {}, reg)
    assert len(results) == 2
    by_name = {r["precondition"]: r["satisfied"] for r in results}
    assert by_name["a"] is True
    assert by_name["b"] is False


def test_contract_store_evaluate_preconditions_unknown_tool_returns_empty():
    store = ContractStore()
    reg = PredicateRegistry()
    assert store.evaluate_preconditions("ghost", {}, reg) == []


# ---------------------------------------------------------------------------
# Executor preflight (the Issue-5 fix)
# ---------------------------------------------------------------------------

def test_executor_rejects_tool_in_needs_config_state():
    """A tool with state=needs_config must be rejected by
    propose_action. This is the preflight hard block that fixes
    the 2026-06-28 Maker-not-ready issue.
    """
    from agent.tool_contracts import default_contract_store
    # Register a contract in needs_config state.
    default_contract_store.register(ToolContract(
        name="project_status",
        purpose="inspect project root",
        preconditions=[],
        state=ToolState.NEEDS_CONFIG,
    ))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            from core.executor import Executor
            from core.event_log import EventLog
            from core.version_manager import VersionManager
            log_path = Path(tmp) / "events.jsonl"
            ex = Executor(
                project_root=Path(tmp),
                event_log=EventLog(log_path),
                version_manager=VersionManager(project_root=Path(tmp), storage_path=Path(tmp) / "versions"),
                sandbox_mode="read-only",
                approval_policy="never",
            )
            result = ex.propose_action(
                session_id="s-1",
                tool_name="project_status",
                params={},
            )
            assert result["ok"] is False
            assert result["error_type"] == "precondition_not_satisfied"
            assert "needs_config" in result["error"]
    finally:
        # Reset the global state for the next test.
        default_contract_store.set_state("project_status", ToolState.AVAILABLE)
        # We do not unregister because the test might have left
        # the contract in place; subsequent tests must tolerate
        # the default AVAILABLE state.


def test_executor_rejects_tool_with_failing_precondition():
    """A tool whose precondition is not satisfied must be rejected."""
    from agent.tool_contracts import (
        default_contract_store,
        default_predicate_registry,
    )
    default_predicate_registry.register(
        "needs_maker_ready", lambda ctx: bool(ctx.get("maker_ready", False))
    )
    default_contract_store.register(ToolContract(
        name="maker_briefing",
        purpose="show Maker briefing",
        preconditions=["needs_maker_ready"],
        state=ToolState.AVAILABLE,
    ))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            from core.executor import Executor
            from core.event_log import EventLog
            from core.version_manager import VersionManager
            log_path = Path(tmp) / "events.jsonl"
            ex = Executor(
                project_root=Path(tmp),
                event_log=EventLog(log_path),
                version_manager=VersionManager(project_root=Path(tmp), storage_path=Path(tmp) / "versions"),
                sandbox_mode="read-only",
                approval_policy="never",
            )
            result = ex.propose_action(
                session_id="s-1",
                tool_name="maker_briefing",
                params={},
            )
            assert result["ok"] is False
            assert "needs_maker_ready" in str(result.get("failed_preconditions", []))
    finally:
        default_contract_store.set_state("maker_briefing", ToolState.AVAILABLE)


def test_executor_passes_through_tool_without_contract():
    """Tools without a contract must be unaffected. The preflight
    is opt-in; the legacy behavior runs unchanged.
    """
    # ``list_directory`` is not registered as a contract in the
    # default store (the existing executor registers the handler
    # directly). propose_action must not block it.
    with tempfile.TemporaryDirectory() as tmp:
        from core.executor import Executor
        from core.event_log import EventLog
        from core.version_manager import VersionManager
        log_path = Path(tmp) / "events.jsonl"
        ex = Executor(
            project_root=Path(tmp),
            event_log=EventLog(log_path),
            version_manager=VersionManager(project_root=Path(tmp), storage_path=Path(tmp) / "versions"),
            sandbox_mode="workspace-write",
            approval_policy="never",
        )
        result = ex.propose_action(
            session_id="s-1",
            tool_name="list_directory",
            params={"path": "."},
        )
        # Either ok (read executed) or a different error (e.g.
        # sandbox block on the test path) — but NOT a
        # precondition_not_satisfied error.
        assert result.get("error_type") != "precondition_not_satisfied"
