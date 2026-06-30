"""Real multi-agent coordination on top of GoalLoop + ColdMemory.

This module turns the existing two-agent simulation into a reusable harness:
each agent is a GoalLoop instance with its own ``agent_id`` and
``SharedMemoryPolicy``, and they all share one ``ColdMemory`` storage path
on disk. Reads enforce policy at recall time; writes go through the
existing ``record_shared_outcome`` path so promoted/privatised/conflict
decisions are visible to every agent on the next reload.

The :class:`MultiAgentRunner` exposes two isolation modes:

- **thread**: each agent runs sequentially in the current process. ColdMemory
  is reloaded between agents to pick up writes from earlier ones.
- **subprocess**: each agent runs in a fresh Python interpreter, proving
  state really crosses a process boundary. Use this in CI to catch
  per-process state leaks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


MULTI_AGENT_VERSION = "multi-agent.v1"


@dataclass
class AgentSpec:
    agent_id: str
    task: str
    session_id: str
    shared_claim: Optional[Dict[str, Any]] = None  # private insight to archive
    can_read_private_other: bool = False


@dataclass
class AgentRunResult:
    agent_id: str
    task: str
    status: str
    output: str = ""
    indexed: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


DevRunnerFn = Callable[[str, str, str], Dict[str, Any]]


def _default_dev_runner_factory(
    agent_id: str, extra_index: Optional[Dict[str, Any]] = None
) -> DevRunnerFn:
    """Build a deterministic dev runner that indexes a single memory record.

    The runner uses the same ColdMemory storage path the runner owns so the
    rest of the project stays unchanged. ``extra_index`` lets the caller
    attach a specific insight (used for the cross-agent conflict scenario).
    """

    def _dev_runner(task: str, session_id: str, _agent_id: str = agent_id) -> Dict[str, Any]:
        insight = extra_index or {
            "id": f"insight-{session_id}",
            "type": "learning_insight",
            "domain": "default",
            "rule": f"Pattern observed by {_agent_id} for: {task[:60]}",
            "context": task,
            "tags": ["lesson", "multi_agent"],
            "confidence": 0.85,
            "shareable": True,
        }
        return {
            "session_id": session_id,
            "task": task,
            "done": True,
            "output": f"agent {_agent_id} completed: {task}",
            "trajectory": [
                {
                    "action": {"tool": "archive_insight"},
                    "observation": {"tool": "pytest", "output": "1 passed", "ok": True},
                }
            ],
            "iteration_count": 1,
            "_memory_index": insight,
        }

    return _dev_runner


def run_agents_threaded(
    *,
    project_root: Path,
    storage_path: Path,
    agents: List[AgentSpec],
    workspace_profile: str = "coding",
    approval_policy: str = "never",
    auto_post: bool = False,
    artifacts_root: Optional[Path] = None,
) -> List[AgentRunResult]:
    """Run each agent sequentially in the current process.

    Each agent gets a fresh ``ColdMemory`` instance pointing at the same
    storage path, so writes from one agent are visible to the next after
    a reload. This proves the policy boundary in single-process
    coordination.
    """
    from agent.goal_loop import GoalLoop
    from learning.shared_memory_bridge import archive_learning_insights_to_shared_memory
    from memory.shared_policy import SharedMemoryPolicy
    from memory.cold import ColdMemory

    results: List[AgentRunResult] = []
    for spec in agents:
        policy = SharedMemoryPolicy.from_config(
            {"default_visibility": "private"},
            agent_id=spec.agent_id,
        )
        # can_read_private_other is per-agent; rebuild the policy when the
        # spec asks for it (used by the cross-agent test).
        if spec.can_read_private_other:
            policy = SharedMemoryPolicy(
                agent_id=spec.agent_id,
                can_read_private_other=True,
            )
        cold = ColdMemory(storage_path=storage_path)
        dev_runner = _default_dev_runner_factory(spec.agent_id, spec.shared_claim)
        events: List[Dict[str, Any]] = []

        def _emit(event, _events=events):
            _events.append(event)

        try:
            loop = GoalLoop(
                project_root=project_root,
                emit=_emit,
                dev_runner=dev_runner,
                approval_policy=approval_policy,
                auto_post=auto_post,
                artifacts_root=artifacts_root,
            )
            result = loop.run(spec.task, session_id=spec.session_id)
            # _memory_index is stashed on the dev_runner return value; we
            # capture it as a top-level field on the GoalLoop result via a
            # side-channel emit so the threading harness can pick it up
            # without depending on the trajectory shape.
            insight = result.get("dev_memory_index") or spec.shared_claim
            bridge = archive_learning_insights_to_shared_memory(
                cold,
                session_id=spec.session_id,
                task=spec.task,
                insights=[insight] if insight else [],
                result=result,
                agent_id=spec.agent_id,
                workspace_profile=workspace_profile,
            )
            indexed = list(bridge.get("records") or [])
            # Reload from disk to surface any cross-agent state changes the
            # test wants to assert on.
            cold_reload = ColdMemory(storage_path=storage_path)
            conflicts = list(getattr(cold_reload, "_conflicts", []))
            results.append(
                AgentRunResult(
                    agent_id=spec.agent_id,
                    task=spec.task,
                    status="completed" if result.get("done") else "blocked",
                    output=str(result.get("output") or ""),
                    indexed=indexed,
                    conflicts=conflicts,
                )
            )
        except Exception as exc:
            results.append(
                AgentRunResult(
                    agent_id=spec.agent_id,
                    task=spec.task,
                    status="failed",
                    error=str(exc),
                )
            )
    return results


def run_agents_subprocess(
    *,
    project_root: Path,
    storage_path: Path,
    agents: List[AgentSpec],
    workspace_profile: str = "coding",
    python: Optional[str] = None,
    timeout: float = 120.0,
    artifacts_root: Optional[Path] = None,
) -> List[AgentRunResult]:
    """Run each agent in a fresh Python subprocess.

    This proves the policy boundary survives a real process boundary: each
    child loads ColdMemory from scratch, no shared in-process state is
    possible. The driver script lives at ``agent/_multi_agent_subprocess.py``
    and is invoked with environment variables for the spec.

    ``artifacts_root`` redirects per-agent GoalLoop writes
    (decisions, system-contracts, progress, sprint board, skill
    packs) to the given directory so the test does not pollute
    the real project. Defaults to ``project_root``.
    """
    driver = Path(__file__).resolve().parent / "_multi_agent_subprocess.py"
    spec_payload = {
        "project_root": str(project_root),
        "storage_path": str(storage_path),
        "artifacts_root": str(artifacts_root) if artifacts_root is not None else None,
        "workspace_profile": workspace_profile,
        "agents": [spec.__dict__ for spec in agents],
    }
    env = {
        **os.environ,
        "TTMEVOLVE_MULTI_AGENT_SPEC": json.dumps(spec_payload),
        "PYTHONPATH": str(project_root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    if artifacts_root is not None:
        # Also pass through the env var so the in-process GoalLoop
        # call inside the driver falls back to it if it cannot
        # parse the spec field.
        env["TTMEVOLVE_GOAL_ARTIFACTS_ROOT"] = str(artifacts_root)
    proc = subprocess.run(
        [python or sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(
            f"multi-agent subprocess failed: rc={proc.returncode} stderr={proc.stderr[-800:]}"
        )
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(
            f"could not parse subprocess output: {exc}; stdout={proc.stdout[-400:]}; stderr={proc.stderr[-400:]}"
        ) from exc
    return [
        AgentRunResult(
            agent_id=item.get("agent_id", ""),
            task=item.get("task", ""),
            status=item.get("status", "unknown"),
            output=item.get("output", ""),
            indexed=item.get("indexed", []),
            conflicts=item.get("conflicts", []),
            error=item.get("error"),
        )
        for item in payload.get("results", [])
    ]


def has_conflict_for(claim_key: str, results: List[AgentRunResult]) -> bool:
    """Return True if any result reports a conflict involving ``claim_key``."""
    needle = str(claim_key or "").strip()
    if not needle:
        return False
    for result in results:
        for conflict in result.conflicts:
            if not isinstance(conflict, dict):
                continue
            if needle in json.dumps(conflict, ensure_ascii=False):
                return True
            keys = conflict.get("claim_keys")
            if isinstance(keys, list) and needle in keys:
                return True
    return False
