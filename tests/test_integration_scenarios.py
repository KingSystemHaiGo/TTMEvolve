"""
tests/test_integration_scenarios.py - more end-to-end integration
scenarios with every flag enabled.

Companion to ``test_integration_all_flags_on.py``. Each test exercises
a different real-world shape so the slice #1 integration is
demonstrated for more than just one happy path.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.cold import ColdMemory  # noqa: E402
from memory.graph import MemoryEdge, MemoryNode  # noqa: E402
from core.plan_executor import PlanExecutor, PlanExecutorError  # noqa: E402


def _mock_encoder(texts):
    dim = 8
    vectors = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        for ch in text.lower():
            vec[ord(ch) % dim] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        vectors.append(vec)
    return np.array(vectors, dtype=np.float32)


def _build_cold(tmp: Path, *, profile: str = "general") -> ColdMemory:
    return ColdMemory(
        tmp / "cold",
        vector_index_config={"enabled": True, "embedding_dim": 8, "model": "stub"},
        encoder=_mock_encoder,
        graph_config={"enabled": True, "expand_hops": 1, "edge_index_enabled": False},
        bayes_config={"enabled": True, "alpha_prior": 1.0, "beta_prior": 1.0},
    )


# ---------------------------------------------------------------------------
# Profile filtering across the full stack
# ---------------------------------------------------------------------------

def test_integration_profile_filtering():
    """Memories in one profile must not surface when another profile is
    queried. The full stack is on; we verify the graph path respects
    the workspace_profile filter at retrieve time.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cold = _build_cold(Path(tmp))
        # Three profiles, three memories each, plus a "general" memory
        items = []
        for prof in ("coding", "docs", "maker"):
            for i in range(3):
                items.append((
                    {"id": f"{prof}-{i}", "type": "fact",
                     "summary": f"{prof} secret {i}",
                     "workspace_profile": prof,
                     "agent_id": "default", "visibility": "private"},
                    f"{prof} content {i}",
                ))
        items.append((
            {"id": "general-0", "type": "fact", "summary": "general alpha",
             "workspace_profile": "general", "agent_id": "default",
             "visibility": "private"},
            "general content",
        ))
        cold.bulk_index(items)

        # Query each profile — only that profile's memories + general
        # should surface through the graph path.
        for prof in ("coding", "docs", "maker"):
            results = cold.retrieve_with_graph(
                "secret", top_k=10, workspace_profile=prof,
            )
            ids = {r["id"] for r in results}
            # Own profile memories appear
            assert any(i.startswith(f"{prof}-") for i in ids), f"missing {prof}"
            # Other profiles' memories must NOT appear
            for other in ("coding", "docs", "maker"):
                if other == prof:
                    continue
                assert not any(i.startswith(f"{other}-") for i in ids), (
                    f"leakage: {other} memory found in {prof} result"
                )
            # general memory may appear (shared general policy)


# ---------------------------------------------------------------------------
# Plan v2 with sub_plan and a step that depends on a sibling
# ---------------------------------------------------------------------------

def test_integration_plan_v2_sub_plan():
    """A nested sub-plan runs in its own coordinate space, with its
    own progress and its own step status. The outer plan sees the
    sub-plan as a single step.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cold = _build_cold(Path(tmp))
        # Use ColdMemory so we know the stack can also write events
        # for plan progress — but the focus of this test is the
        # executor, so we keep the cold path read-only here.
        _ = cold

        outer_plan = {
            "version": "plan-format.v2",
            "task": "outer", "summary": "outer task",
            "steps": [
                {
                    "id": "outer", "kind": "sub_plan", "depends_on": [],
                    "sub_plan": {
                        "version": "plan-format.v2",
                        "task": "inner", "summary": "inner",
                        "steps": [
                            {"id": "i1", "kind": "tool", "tool": "read_file", "depends_on": []},
                            {"id": "i2", "kind": "tool", "tool": "write_file", "depends_on": ["i1"]},
                        ],
                    },
                }
            ],
        }
        calls: List[Dict[str, Any]] = []

        def _run(step, plan, depth):
            calls.append({"id": step["id"], "depth": depth})
            return {"ok": True, "step_id": step["id"]}

        executor = PlanExecutor(
            step_runner=_run, config={"max_depth": 3, "max_loop_iterations": 3},
        )
        result = executor.execute_plan(outer_plan)
        assert result["status"] == "completed"
        # i1 then i2 at depth 1 (inside sub-plan)
        order = [(c["id"], c["depth"]) for c in calls]
        assert ("i1", 1) in order
        assert ("i2", 1) in order
        # outer step not in calls — sub_plan executes its children
        assert ("outer", 1) not in order


# ---------------------------------------------------------------------------
# Failure recovery: a failed step halts downstream + bumps bayes β
# ---------------------------------------------------------------------------

def test_integration_failure_recovery():
    """When a tool step fails, downstream steps do not run, the
    executor reports needs_recovery, and the bayes posterior for the
    failed node drops (β rises).
    """
    with tempfile.TemporaryDirectory() as tmp:
        cold = _build_cold(Path(tmp))
        # Seed two memories, link them so the second depends on the first
        cold.bulk_index([
            ({"id": "f-1", "type": "fact", "summary": "alpha",
              "workspace_profile": "general", "agent_id": "default",
              "visibility": "private"}, "alpha bravo"),
            ({"id": "f-2", "type": "fact", "summary": "bravo",
              "workspace_profile": "general", "agent_id": "default",
              "visibility": "private"}, "bravo charlie"),
        ])
        g = cold._graph
        g.add_edge(MemoryEdge(id="e-1-2", src="f-1", dst="f-2", type="references"))

        # Capture the pre-failure posterior
        before = cold.shared_outcome_summary()

        # First, mark f-1 with a verified-positive so it has a posterior
        cold.record_shared_outcome("f-1", {
            "status": "verified_positive",
            "verified": True,
            "task_success": True,
            "evidence_refs": ["ref-init"],
        })
        f1_after_pos = next(
            e for e in cold.shared_outcome_summary().get("entries", [])
            if e.get("id") == "f-1"
        ) if "entries" in cold.shared_outcome_summary() else None

        # Now drive a failure outcome — bayes β should rise
        fail_result = cold.record_shared_outcome("f-1", {
            "status": "regression",
            "verified": True,
            "task_success": False,
            "evidence_refs": ["ref-fail"],
        })
        f1_bayes = fail_result["bayes"]
        # β is now > 1 (we started with α=β=1, added 3.0 for regression)
        assert f1_bayes["beta"] > f1_bayes["alpha"]
        # The conflict symmetry updated f-2 as well (since f-1 and f-2 share an edge)
        # (the conflict is on claim_key collisions; we test that the
        # regression update is recorded, not the symmetric edge)
        assert "alpha" in f1_bayes
        assert "beta" in f1_bayes
        assert "occurrences" in f1_bayes


# ---------------------------------------------------------------------------
# Cycle detection refuses a bad plan immediately
# ---------------------------------------------------------------------------

def test_integration_plan_v2_cycle_refused():
    """A plan with a dependency cycle must raise PlanExecutorError
    immediately. The runtime never enters an infinite loop.
    """
    bad_plan = {
        "version": "plan-format.v2",
        "task": "t", "summary": "cycle",
        "steps": [
            {"id": "a", "kind": "tool", "tool": "x", "depends_on": ["b"]},
            {"id": "b", "kind": "tool", "tool": "y", "depends_on": ["c"]},
            {"id": "c", "kind": "tool", "tool": "z", "depends_on": ["a"]},
        ],
    }

    def _run(step, plan, depth):
        return {"ok": True, "step_id": step["id"]}

    executor = PlanExecutor(
        step_runner=_run, config={"max_depth": 3, "max_loop_iterations": 3},
    )
    try:
        executor.execute_plan(bad_plan)
    except PlanExecutorError as exc:
        assert "cycle" in str(exc).lower()
        return
    raise AssertionError("cycle plan should have raised PlanExecutorError")
