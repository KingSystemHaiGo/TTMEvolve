from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from learning.shared_memory_bridge import archive_learning_insights_to_shared_memory
from llm.mock_llm import MockLLM
from memory.cold import ColdMemory


def _cold_memory(root: Path) -> ColdMemory:
    return ColdMemory(
        root,
        vector_index_config={"enabled": False, "fallback_to_keyword": True},
    )


def _verified_result() -> Dict[str, Any]:
    return {
        "output": "verified",
        "trajectory": [
            {
                "action": {"tool": "execute_shell"},
                "observation": {
                    "ok": True,
                    "tool": "execute_shell",
                    "output": "pytest tests/test_tool_call_validation.py -q -> passed",
                },
            }
        ],
    }


def test_learning_bridge_archives_private_then_promotes_verified_shareable_insight():
    with tempfile.TemporaryDirectory() as tmp:
        cold = _cold_memory(Path(tmp))

        summary = archive_learning_insights_to_shared_memory(
            cold,
            session_id="session-a",
            task="keep tool validation machine readable",
            insights=[
                {
                    "memory_id": "lesson-tool-validation",
                    "domain": "tool_validation",
                    "rule": "tool validation failures must stay machine readable",
                    "context": "validated by pytest",
                    "tags": ["tool_validation", "lesson"],
                    "confidence": 0.9,
                    "claim_key": "tool-validation-contract",
                }
            ],
            result=_verified_result(),
            agent_id="agent-a",
            workspace_profile="coding",
            now=100.0,
        )

        b_hits = cold.search("machine readable", workspace_profile="coding", agent_id="agent-b")

        assert summary["counts"]["archived"] == 1
        assert summary["counts"]["promoted"] == 1
        assert summary["records"][0]["decision"]["status"] == "promoted"
        assert b_hits[0]["id"] == "lesson-tool-validation"
        assert b_hits[0]["visibility"] == "shared"


def test_learning_bridge_keeps_unverified_and_private_insights_private():
    with tempfile.TemporaryDirectory() as tmp:
        cold = _cold_memory(Path(tmp))

        summary = archive_learning_insights_to_shared_memory(
            cold,
            session_id="session-private",
            task="archive without leaking private or unverified claims",
            insights=[
                {
                    "memory_id": "lesson-unverified",
                    "domain": "memory",
                    "rule": "unverified shared memory claims must stay private",
                    "context": "no verification refs were produced",
                    "tags": ["memory", "lesson"],
                    "confidence": 0.92,
                    "claim_key": "unverified-memory-claim",
                },
                {
                    "memory_id": "lesson-private",
                    "domain": "memory",
                    "rule": "private-only user preference must stay private",
                    "context": "even successful tasks cannot share private tags",
                    "tags": ["memory", "private"],
                    "confidence": 0.99,
                    "claim_key": "private-memory-claim",
                },
            ],
            result={"output": "done", "trajectory": []},
            agent_id="agent-a",
            workspace_profile="coding",
            now=100.0,
        )

        b_hits = cold.search("must stay private", workspace_profile="coding", agent_id="agent-b")
        a_hits = cold.search("must stay private", workspace_profile="coding", agent_id="agent-a")

        assert summary["counts"]["archived"] == 2
        assert summary["counts"]["promoted"] == 0
        assert summary["counts"]["private"] == 2
        assert {record["decision"]["status"] for record in summary["records"]} == {
            "insufficient_evidence",
            "archived_private",
        }
        assert b_hits == []
        assert {hit["id"] for hit in a_hits} == {"lesson-unverified", "lesson-private"}


def test_two_agent_handoff_reads_shared_and_records_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        cold = _cold_memory(Path(tmp))

        first = archive_learning_insights_to_shared_memory(
            cold,
            session_id="agent-a-session",
            task="measure rag budget",
            insights=[
                {
                    "memory_id": "rag-a",
                    "domain": "rag",
                    "rule": "RAG warm recall p95 is below 50ms for fake embeddings",
                    "context": "verified by deterministic benchmark",
                    "tags": ["rag", "lesson"],
                    "confidence": 0.95,
                    "claim_key": "rag-budget",
                }
            ],
            result=_verified_result(),
            agent_id="agent-a",
            workspace_profile="coding",
            now=100.0,
        )

        b_handoff = cold.search("below 50ms", workspace_profile="coding", agent_id="agent-b")

        second = archive_learning_insights_to_shared_memory(
            cold,
            session_id="agent-b-session",
            task="remeasure rag budget",
            insights=[
                {
                    "memory_id": "rag-b",
                    "domain": "rag",
                    "rule": "RAG warm recall p95 is below 5ms for fake embeddings",
                    "context": "verified by deterministic benchmark",
                    "tags": ["rag", "lesson"],
                    "confidence": 0.95,
                    "claim_key": "rag-budget",
                }
            ],
            result=_verified_result(),
            agent_id="agent-b",
            workspace_profile="coding",
            now=101.0,
        )

        c_hits = cold.search("below 5ms", workspace_profile="coding", agent_id="agent-c")
        c_ids = {hit["id"] for hit in c_hits}
        conflicts = cold.shared_conflicts(unresolved_only=True)

        assert first["counts"]["promoted"] == 1
        assert b_handoff[0]["id"] == "rag-a"
        assert second["counts"]["promoted"] == 0
        assert second["counts"]["conflicts"] == 1
        assert second["records"][0]["decision"]["status"] == "conflict"
        assert "rag-b" not in c_ids
        assert conflicts[0]["claim_key"] == "rag-budget"
        assert conflicts[0]["candidate_id"] == "rag-b"


class _StaticReflection:
    def __init__(self, insights: List[Dict[str, Any]]):
        self.insights = insights

    def reflect(self, session_id: str, task: str, trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.insights]


def test_agent_learning_session_returns_shared_memory_summary():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "project_root": str(root / "project"),
                    "storage_root": str(root / "storage"),
                    "agent": {"id": "agent-a"},
                    "llm": {"provider": "mock"},
                    "sandbox": {"mode": "workspace-write"},
                    "approval": {"policy": "never"},
                    "memory": {"vector_index": {"enabled": False, "fallback_to_keyword": True}},
                    "learning": {
                        "skill_generation_enabled": False,
                        "shared_memory_outcomes_enabled": True,
                    },
                    "agents_md": {"dynamic_tools_enabled": False},
                }
            ),
            encoding="utf-8",
        )
        agent = TapMakerAgent(
            llm=MockLLM(),
            config=Config(config_path),
            connect_mcp=False,
        )
        try:
            agent.reflection = _StaticReflection(
                [
                    {
                        "memory_id": "agent-learning-memory",
                        "domain": "tool_validation",
                        "rule": "agent learning validates before sharing",
                        "context": "verified by focused pytest",
                        "tags": ["tool_validation", "lesson"],
                        "confidence": 0.9,
                        "claim_key": "agent-learning-share",
                    }
                ]
            )

            summary = agent._learn_from_session(
                "agent-learning-session",
                "verify learning shared memory bridge",
                _verified_result(),
            )
            b_hits = agent.memory_manager.cold.search(
                "validates before sharing",
                workspace_profile="general",
                agent_id="agent-b",
            )

            assert summary["insight_count"] == 1
            assert summary["shared_memory"]["counts"]["promoted"] == 1
            assert b_hits[0]["id"] == "agent-learning-memory"
        finally:
            agent.close()
