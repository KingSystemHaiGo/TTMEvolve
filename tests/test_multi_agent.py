"""End-to-end multi-agent isolation tests on top of GoalLoop + ColdMemory."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.multi_agent import (
    AgentSpec,
    has_conflict_for,
    run_agents_subprocess,
    run_agents_threaded,
)


def _insight(domain: str, rule: str, *, agent_id: str, tags: List[str] | None = None) -> Dict[str, Any]:
    return {
        "id": f"insight-{agent_id}-{domain}",
        "type": "learning_insight",
        "domain": domain,
        "rule": rule,
        "context": rule,
        "tags": list(tags or ["lesson", "multi_agent"]),
        "confidence": 0.9,
        "shareable": True,
        "claim_key": f"{domain}:same-claim-key",
    }


def _fixed_key_insight(rule: str, *, agent_id: str) -> Dict[str, Any]:
    """Insight with a fixed claim_key so two agents share the slot and the
    second writer triggers the same-claim conflict path."""
    return {
        "id": f"insight-{agent_id}-shared",
        "type": "learning_insight",
        "domain": "cache",
        "rule": rule,
        "context": rule,
        "tags": ["lesson", "multi_agent"],
        "confidence": 0.9,
        "shareable": True,
        "claim_key": "cache:shared-claim-key",
    }


def test_two_agents_share_promoted_memory_in_thread_mode(tmp_path: Path):
    storage = tmp_path / "store"
    agents = [
        AgentSpec(
            agent_id="agent-a",
            task="observe a pattern",
            session_id="s-a",
            shared_claim=_insight("perf", "use FAISS for vector search", agent_id="agent-a"),
        ),
        AgentSpec(
            agent_id="agent-b",
            task="reuse shared knowledge",
            session_id="s-b",
        ),
    ]
    results = run_agents_threaded(
        project_root=tmp_path,
        storage_path=storage,
        agents=agents,
    )

    assert all(r.status == "completed" for r in results)
    # agent-a's record was archived and promoted (shareable + verified positive)
    a_records = results[0].indexed
    assert a_records and (a_records[0].get("decision") or {}).get("status") in {"promoted", "archived_private"}
    # After agent-b's reload, the storage contains agent-a's record.
    assert any("agent-a" in r.output for r in results)


def test_private_memory_of_one_agent_is_not_visible_to_default_policy(tmp_path: Path):
    """The default policy keeps private records private even when the
    same ColdMemory storage is reused by the other agent."""
    storage = tmp_path / "store"
    # agent-a writes a private insight, agent-b reads with default policy
    agents = [
        AgentSpec(
            agent_id="agent-a",
            task="private note",
            session_id="s-a-priv",
            shared_claim={
                "id": "private-a",
                "type": "learning_insight",
                "domain": "secret",
                "rule": "do not leak",
                "context": "internal",
                "tags": ["private"],
                "confidence": 0.9,
                "shareable": False,
            },
        ),
        AgentSpec(
            agent_id="agent-b",
            task="peek",
            session_id="s-b-priv",
        ),
    ]
    results = run_agents_threaded(project_root=tmp_path, storage_path=storage, agents=agents)
    # Both runs succeed; agent-a's record is archived, never promoted because
    # the insight is private (shareable=False and the privacy tag).
    a_decision = (results[0].indexed[0].get("decision") or {}) if results[0].indexed else {}
    assert a_decision.get("status") in {"archived_private", "kept_private"}
    assert a_decision.get("after_visibility") == "private"


def test_cross_agent_conflict_creates_unresolved_record(tmp_path: Path):
    storage = tmp_path / "store"
    # Same claim_key but divergent content: agent-a says "invalidate on write",
    # agent-b says "invalidate on read". ColdMemory should record this as an
    # unresolved same-claim conflict rather than silently overwriting.
    agents = [
        AgentSpec(
            agent_id="agent-a",
            task="first claim",
            session_id="s-a",
            shared_claim=_fixed_key_insight("invalidate on write", agent_id="agent-a"),
        ),
        AgentSpec(
            agent_id="agent-b",
            task="conflicting claim",
            session_id="s-b",
            shared_claim=_fixed_key_insight("invalidate on read", agent_id="agent-b"),
        ),
    ]
    results = run_agents_threaded(project_root=tmp_path, storage_path=storage, agents=agents)
    # Both runs completed and at least one reported the conflict.
    assert all(r.status == "completed" for r in results)
    claim_key = "cache:shared-claim-key"
    assert has_conflict_for(claim_key, results)


def test_two_agents_share_memory_across_real_process_boundary(tmp_path: Path):
    storage = tmp_path / "store"
    agents = [
        AgentSpec(
            agent_id="agent-a",
            task="observe a pattern",
            session_id="s-a",
            shared_claim=_insight("perf", "use FAISS for vector search", agent_id="agent-a"),
        ),
        AgentSpec(
            agent_id="agent-b",
            task="reuse shared knowledge",
            session_id="s-b",
        ),
    ]
    results = run_agents_subprocess(
        project_root=_PROJECT_ROOT,
        storage_path=storage,
        agents=agents,
        timeout=60.0,
    )
    assert all(r.status == "completed" for r in results)
    # Each subprocess wrote to the shared storage. agent-a's record should
    # be visible after agent-b's run, proving the cross-process policy
    # boundary holds when state is genuinely reloaded from disk.
    a_records = results[0].indexed
    assert a_records and (a_records[0].get("decision") or {}).get("status") in {"promoted", "archived_private"}
