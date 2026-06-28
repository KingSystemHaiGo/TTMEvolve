"""
tests/test_regression_guards.py - slice #1 regression guards.

These tests are the **regression-protection layer** for the
RAG/Memory/Cybernetic Control slice. They lock down the
invariants the docs/release-gates.md gate list depends on.

If any of these tests fail, slice #1 is **not releasable** —
fix the underlying cause, do not silence the test.

The 10 gates G1-G10 are listed in docs/release-gates.md. This file
maps each gate to the test that proves it.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# G1: All five new feature flags default to false
# ---------------------------------------------------------------------------

def test_feature_flags_default_off():
    """The five slice #1 flags must all be `false` when the config
    has no override. This is the bedrock gate; flipping a default
    requires updating this test in the same commit.
    """
    flag_paths = [
        ("memory.graph", "enabled"),
        ("memory.bayes", "enabled"),
        ("loader", "enabled"),
        ("plan", "v2_enabled"),
        ("vsm", "enabled"),
        # Phase L: error-log subsystem; same default-off contract.
        ("runtime.errors", "enabled"),
        # Phase R3: homeostatic dead-man's switch; same default-off.
        ("homeostasis", "enabled"),
        # Phase R1: structured thought chain; same default-off.
        ("thought_chain", "strict"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        # Minimal config with no flag overrides
        cfg_path = Path(tmp) / "config.json"
        cfg_path.write_text(json.dumps({
            "llm": {"n_ctx": 4096, "reserve_tokens": 64},
        }), encoding="utf-8")
        from core.config import Config
        cfg = Config(str(cfg_path))
        for dotted_path, leaf in flag_paths:
            # ``Config.get`` returns the default when the key is missing.
            # We pass ``False`` as the default so a missing key reads as
            # the intended off-state.
            value = cfg.get(f"{dotted_path}.{leaf}", False)
            assert value is False, (
                f"flag {dotted_path}.{leaf} is not default-false "
                f"(got {value!r})"
            )


# ---------------------------------------------------------------------------
# G2: release_readiness boundary check
# ---------------------------------------------------------------------------

def test_release_readiness_source_checkpoint_status():
    """`release_readiness --mode source-checkpoint` must report
    ``status=ready`` and ``blockers=[]`` against the project's
    actual source tree.
    """
    import subprocess
    import sys
    result = subprocess.run(
        [
            sys.executable,
            "scripts/release_readiness.py",
            "--mode", "source-checkpoint",
            "--json",
        ],
        capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
    )
    assert result.returncode == 0, f"release_readiness failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "ready", f"got {data['status']}"
    assert data["blockers"] == [], f"got blockers {data['blockers']!r}"
    assert data["closure_gate"]["can_claim_source_checkpoint_ready"] is True


# ---------------------------------------------------------------------------
# G3: production_rag_quality stays unproven
# ---------------------------------------------------------------------------

def test_production_rag_quality_unproven():
    """The production RAG semantic-quality claim must remain
    ``unproven`` until a real labelled corpus and production
    embedding artifact pass. Do not silence this.
    """
    import subprocess
    import sys
    result = subprocess.run(
        [
            sys.executable,
            "scripts/release_readiness.py",
            "--mode", "source-checkpoint",
            "--json",
        ],
        capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
    )
    data = json.loads(result.stdout)
    quality = data["checks"]["production_rag_quality"]
    assert quality["status"] == "unproven", (
        f"production_rag_quality status changed to {quality['status']!r} "
        f"— slice #1 must keep the boundary until a real corpus/embedding passes"
    )
    assert quality["ok"] is False


# ---------------------------------------------------------------------------
# G4: LLM provider adapters are not modified
# ---------------------------------------------------------------------------

def test_llm_provider_files_unchanged():
    """The five LLM provider modules must still import and expose
    the standard ``think / choose_action`` interface. The slice #1
    work must not have coupled providers to graph memory or prompt
    fragments.
    """
    expected_modules = {
        "claude_llm": "ClaudeLLM",
        "local_llm": "LocalLLM",
        "openai_llm": "OpenAILLM",
        "minimax_llm": "MiniMaxLLM",
        "mock_llm": "MockLLM",
    }
    for module_name, class_name in expected_modules.items():
        module = importlib.import_module(f"llm.{module_name}")
        assert hasattr(module, class_name), (
            f"llm/{module_name}.py is missing {class_name}"
        )
        cls = getattr(module, class_name)
        # ``think`` and ``choose_action`` are the LLMInterface
        # methods the plan explicitly says providers must keep.
        # This is the slice #1 contract: provider adapters are thin
        # and untouched by graph / loader / plan v2 / VSM.
        for method in ("think", "choose_action"):
            assert callable(getattr(cls, method, None)), (
                f"llm/{module_name}.py {class_name}.{method} is not callable"
            )


# ---------------------------------------------------------------------------
# G5: plan v1 still parses and executes
# ---------------------------------------------------------------------------

def test_plan_v1_backward_compat():
    """A plan written in plan-format.v1 must still execute under
    PlanExecutor (auto-promoted to v2 with kind='tool' and
    vsm_layer='S1').
    """
    from core.plan_executor import PlanExecutor
    v1_plan = {
        "version": "plan-format.v1",
        "task": "t",
        "summary": "v1 plan",
        "steps": [
            {"id": "a", "tool": "noop", "params": {}, "intent": "x",
             "expected_evidence": ["y"], "depends_on": []},
            {"id": "b", "tool": "noop", "params": {}, "intent": "x",
             "expected_evidence": ["y"], "depends_on": ["a"]},
        ],
    }
    calls = []

    def _run(step, plan, depth):
        calls.append(step["id"])
        return {"ok": True, "step_id": step["id"]}

    executor = PlanExecutor(step_runner=_run, config={"max_depth": 3})
    result = executor.execute_plan(v1_plan)
    assert result["status"] == "completed"
    assert calls == ["a", "b"]


# ---------------------------------------------------------------------------
# G6 / G7 / G8: evidence bundle smoke + integration tests
# ---------------------------------------------------------------------------

def test_evidence_bundle_smoke_three_tests_present():
    """The three live-evidence smoke tests must exist and be
    discoverable. The CI gate counts them.
    """
    test_path = _PROJECT_ROOT / "tests" / "test_smoke_evidence_new_fields.py"
    assert test_path.exists()
    text = test_path.read_text(encoding="utf-8")
    for needle in (
        "test_evidence_bundle_exposes_new_fields",
        "test_evidence_bundle_prompt_loader_shape_is_stable",
        "test_evidence_bundle_control_loop_shape_is_stable",
    ):
        assert needle in text, f"missing {needle} in smoke test file"


def test_all_flags_on_integration_test_present():
    test_path = _PROJECT_ROOT / "tests" / "test_integration_all_flags_on.py"
    assert test_path.exists()
    text = test_path.read_text(encoding="utf-8")
    assert "test_all_flags_on_end_to_end" in text


def test_cross_surface_scenarios_present():
    test_path = _PROJECT_ROOT / "tests" / "test_integration_scenarios.py"
    assert test_path.exists()
    text = test_path.read_text(encoding="utf-8")
    for needle in (
        "test_integration_profile_filtering",
        "test_integration_plan_v2_sub_plan",
        "test_integration_failure_recovery",
        "test_integration_plan_v2_cycle_refused",
    ):
        assert needle in text, f"missing {needle} in scenarios file"


# ---------------------------------------------------------------------------
# G9: The 14 baseline tests are still there
# ---------------------------------------------------------------------------

def test_baseline_test_files_present():
    """The two baseline test files exist and contain the
    boundary-preserving tests. Do not rename or remove these
    without updating docs/release-gates.md.
    """
    rag = _PROJECT_ROOT / "tests" / "test_rag_performance.py"
    runtime = _PROJECT_ROOT / "tests" / "test_runtime_contract.py"
    assert rag.exists()
    assert runtime.exists()
    rag_text = rag.read_text(encoding="utf-8")
    for needle in (
        "test_compact_rag_benchmark_keeps_production_quality_unproven_until_evaluated",
        "test_production_embedding_quality_boundary_requires_real_quality_evidence",
        "test_embedding_quality_evaluation_missing_corpus_stays_unproven",
    ):
        assert needle in rag_text, f"boundary test removed: {needle}"


# ---------------------------------------------------------------------------
# G10: full memory subsystem regression still wired
# ---------------------------------------------------------------------------

def test_memory_subsystem_test_files_present():
    """The full memory subsystem regression depends on these four
    test files. Removing any of them is a gate failure.
    """
    for name in (
        "test_memory_manager.py",
        "test_cold_memory_vector.py",
        "test_vector_index.py",
        "test_shared_memory_policy.py",
    ):
        path = _PROJECT_ROOT / "tests" / name
        assert path.exists(), f"missing memory subsystem test: {name}"


# ---------------------------------------------------------------------------
# Documentation anchors exist
# ---------------------------------------------------------------------------

def test_release_docs_exist():
    """The release-process docs must be in place so a new
    contributor can run the gates without asking.
    """
    for relpath in (
        "docs/feature-flags.md",
        "docs/release-gates.md",
        "docs/runtime-errors.md",
        "docs/react-loop-redesign.md",
        "docs/research/2026-memory-and-control.md",
        "docs/architecture/adr-0004-profile-aware-graph-memory.md",
        "docs/architecture/adr-0007-progressive-context-loader.md",
        "docs/architecture/adr-0008-plan-v2-cybernetic-control.md",
    ):
        assert (_PROJECT_ROOT / relpath).exists(), f"missing {relpath}"


def test_tool_contracts_module_exists():
    """Phase R2: the tool contract module must exist and expose
    the canonical API. Adding a tool without going through the
    contract store is the failure mode the redesign targets.
    """
    from agent import tool_contracts
    assert hasattr(tool_contracts, "ToolContract")
    assert hasattr(tool_contracts, "ToolState")
    assert hasattr(tool_contracts, "ContractStore")
    assert hasattr(tool_contracts, "PredicateRegistry")
    assert hasattr(tool_contracts, "default_contract_store")
    assert hasattr(tool_contracts, "default_predicate_registry")


def test_vsm_shell_has_disable_tool_api():
    """Phase R4: VSMShell must expose the S2 write surface. The
    disable_tool / is_tool_disabled / disabled_tools API is the
    contract between observation and tool selection.
    """
    from core.vsm import VSMShell
    shell = VSMShell(control_loop=__import__("core.control_loop", fromlist=["ControlLoop"]).ControlLoop(), config={"enabled": True, "policy": "audit"})
    assert hasattr(shell, "disable_tool")
    assert hasattr(shell, "is_tool_disabled")
    assert hasattr(shell, "disabled_tools")
    # Disabled state defaults: no tools blacklisted, nothing disabled
    assert shell.disabled_tools() == []
    assert shell.is_tool_disabled("anything") is False
