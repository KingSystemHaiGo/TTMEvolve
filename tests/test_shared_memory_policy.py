"""
tests/test_shared_memory_policy.py - multi-agent cold memory policy tests.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from llm.context_budget import ContextBudgetManager
from memory.cold import ColdMemory
from memory.manager import MemoryManager
from memory.shared_policy import SharedMemoryPolicy


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


def test_shared_policy_hides_other_agent_private_memory():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "a-private", "workspace_profile": "coding", "agent_id": "agent-a", "visibility": "private"},
            "shared-boundary private-token",
        )
        cold.index(
            {"id": "a-shared", "workspace_profile": "coding", "agent_id": "agent-a", "visibility": "shared"},
            "shared-boundary shared-token",
        )

        a_hits = cold.search("shared-boundary", workspace_profile="coding", agent_id="agent-a")
        b_hits = cold.search("shared-boundary", workspace_profile="coding", agent_id="agent-b")

        assert {hit["id"] for hit in a_hits} == {"a-private", "a-shared"}
        assert {hit["id"] for hit in b_hits} == {"a-shared"}


def test_shared_policy_can_disable_shared_reads_but_keep_public():
    policy = SharedMemoryPolicy.from_config(
        {"can_read_shared": False, "can_read_public": True},
        agent_id="agent-b",
    )
    assert policy.can_read(
        {"agent_id": "agent-a", "visibility": "shared", "workspace_profile": "docs"},
        "docs",
    ) is False
    assert policy.can_read(
        {"agent_id": "agent-a", "visibility": "public", "workspace_profile": "docs"},
        "docs",
    ) is True


def test_shared_policy_blocks_disallowed_write_profile():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={
                "enabled": False,
                "shared_memory": {
                    "profiles": {
                        "docs-agent": {"write_profiles": ["docs"]},
                    }
                },
            },
            encoder=_mock_encoder,
        )

        cold.index(
            {"id": "doc", "workspace_profile": "docs", "agent_id": "docs-agent"},
            "allowed docs write",
        )
        try:
            cold.index(
                {"id": "maker", "workspace_profile": "maker", "agent_id": "docs-agent"},
                "blocked maker write",
            )
        except PermissionError as exc:
            assert "cannot index maker" in str(exc)
        else:
            raise AssertionError("expected PermissionError for disallowed write profile")


def test_memory_manager_archives_agent_visibility_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = Config()
        cfg.data = {
            "llm": {"n_ctx": 8192, "reserve_tokens": 256},
            "memory": {"vector_index": {"enabled": False, "fallback_to_keyword": True}},
        }
        cfg._profiles = {}
        manager = MemoryManager(
            project_root=root / "project",
            storage_root=root / "storage",
            skills_dir=root / "skills",
            budget_manager=ContextBudgetManager(n_ctx=8192, reserve_tokens=256),
            config=cfg,
        )

        manager.archive_session(
            "session-a",
            "manager shared-memory handoff",
            workspace_profile="coding",
            agent_id="agent-a",
            visibility="shared",
        )
        hits = manager.recall(
            "shared-memory handoff",
            workspace_profile="coding",
            agent_id="agent-b",
        )

        assert hits[0]["id"] == "session-a"
        assert hits[0]["agent_id"] == "agent-a"
        assert hits[0]["visibility"] == "shared"


def test_verified_positive_outcome_promotes_private_memory_to_shared():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {
                "id": "lesson-1",
                "workspace_profile": "coding",
                "agent_id": "agent-a",
                "visibility": "private",
                "claim_key": "tool-validation-contract",
            },
            "tool validation failures must stay machine readable",
        )

        result = cold.record_shared_outcome(
            "lesson-1",
            {
                "status": "verified_positive",
                "verified": True,
                "task_success": True,
                "claim_key": "tool-validation-contract",
                "evidence_refs": ["pytest tests/test_tool_call_validation.py -q -> passed"],
            },
            now=100.0,
        )
        hits = cold.search(
            "tool validation",
            workspace_profile="coding",
            agent_id="agent-b",
        )

        assert result["decision"]["status"] == "promoted"
        assert result["entry"]["visibility"] == "shared"
        assert hits[0]["id"] == "lesson-1"

        reloaded = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        summary = reloaded.shared_outcome_summary()
        assert summary["visibility_counts"]["shared"] == 1
        assert summary["state_counts"]["promoted"] == 1


def test_positive_outcome_without_verified_evidence_stays_private():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "lesson-2", "workspace_profile": "coding", "agent_id": "agent-a"},
            "private until verified shared memory claim",
        )

        result = cold.record_shared_outcome(
            "lesson-2",
            {"status": "success", "task_success": True},
            now=100.0,
        )
        b_hits = cold.search(
            "private until verified",
            workspace_profile="coding",
            agent_id="agent-b",
        )

        assert result["decision"]["status"] == "insufficient_evidence"
        assert result["entry"]["visibility"] == "private"
        assert b_hits == []


def test_repeated_misleading_outcomes_demote_shared_memory():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {
                "id": "lesson-3",
                "workspace_profile": "coding",
                "agent_id": "agent-a",
                "visibility": "shared",
                "claim_key": "resume-claim",
            },
            "shared hot resume claim",
        )

        first = cold.record_shared_outcome(
            "lesson-3",
            {
                "status": "misleading",
                "verified": True,
                "evidence_refs": ["restart drill failed once"],
            },
            now=100.0,
        )
        second = cold.record_shared_outcome(
            "lesson-3",
            {
                "status": "misleading",
                "verified": True,
                "evidence_refs": ["restart drill failed twice"],
            },
            now=101.0,
        )
        b_hits = cold.search("hot resume", workspace_profile="coding", agent_id="agent-b")

        assert first["decision"]["status"] == "watch"
        assert second["decision"]["status"] == "demoted"
        assert second["entry"]["visibility"] == "private"
        assert b_hits == []


def test_stale_shared_outcome_demotes_memory():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {
                "id": "lesson-stale",
                "workspace_profile": "coding",
                "agent_id": "agent-a",
                "visibility": "shared",
                "shared_memory": {"state": "promoted", "last_verified_at": 100.0},
            },
            "stale shared memory rule",
        )

        result = cold.record_shared_outcome(
            "lesson-stale",
            {
                "status": "stale",
                "verified": True,
                "evidence_refs": ["age check exceeded retention window"],
            },
            now=200.0,
        )

        assert result["decision"]["status"] == "demoted"
        assert result["entry"]["visibility"] == "private"
        assert result["entry"]["shared_memory"]["demotion_reason"] == "stale"


def test_conflicting_shared_claim_blocks_promotion_and_records_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {
                "id": "existing",
                "workspace_profile": "coding",
                "agent_id": "agent-a",
                "visibility": "shared",
                "claim_key": "rag-budget",
            },
            "RAG warm recall p95 is below 50ms for fake embeddings",
        )
        cold.index(
            {
                "id": "candidate",
                "workspace_profile": "coding",
                "agent_id": "agent-b",
                "visibility": "private",
                "claim_key": "rag-budget",
            },
            "RAG warm recall p95 is below 5ms for fake embeddings",
        )

        result = cold.record_shared_outcome(
            "candidate",
            {
                "status": "verified_positive",
                "verified": True,
                "task_success": True,
                "claim_key": "rag-budget",
                "evidence_refs": ["pytest tests/test_rag_performance.py -q -> passed"],
            },
            now=100.0,
        )
        summary = cold.shared_outcome_summary()

        assert result["decision"]["status"] == "conflict"
        assert result["entry"]["visibility"] == "private"
        assert result["conflicts"][0]["claim_key"] == "rag-budget"
        assert cold.shared_conflicts(unresolved_only=True)[0]["status"] == "unresolved"
        assert summary["unresolved_conflict_count"] == 1


if __name__ == "__main__":
    test_shared_policy_hides_other_agent_private_memory()
    test_shared_policy_can_disable_shared_reads_but_keep_public()
    test_shared_policy_blocks_disallowed_write_profile()
    test_memory_manager_archives_agent_visibility_metadata()
    test_verified_positive_outcome_promotes_private_memory_to_shared()
    test_positive_outcome_without_verified_evidence_stays_private()
    test_repeated_misleading_outcomes_demote_shared_memory()
    test_stale_shared_outcome_demotes_memory()
    test_conflicting_shared_claim_blocks_promotion_and_records_conflict()
    print("\nAll shared memory policy tests passed.")
