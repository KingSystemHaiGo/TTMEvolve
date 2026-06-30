"""Typed sub-goal DAG for GoalLoop (Q4 / Slice B).

A parent goal can spawn multiple sub-goals that execute in parallel
when they have no dependencies. Each sub-goal has a *type* that
drives the per-type sub-loop (asset / code / scene / audio /
integration / test) and the agent the sub-goal is dispatched to.

Design rules:
- The DAG is built from a list of ``SubGoalSpec`` objects; the
  scheduler topologically sorts them and yields the sub-goals that
  are ready to run.
- Parallelism is bounded by ``max_concurrent`` so a parent goal
  does not accidentally spawn dozens of concurrent sub-agents.
- Sub-goal complexity is measured by *boundary signals* (number of
  acceptance criteria, dependency depth, cross-module impact) —
  not by source file size.
- No model names baked in: ``model_hint`` is a *capability* hint
  (``fast`` / ``balanced`` / ``deep``) the agent config maps to a
  real provider.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple


GOAL_DAG_VERSION = "goal-dag.v1"


class SubGoalType(str, Enum):
    """Type discriminator for a sub-goal. Drives the per-type sub-loop."""

    CODE = "code"
    ASSET = "asset"
    SCENE = "scene"
    AUDIO = "audio"
    INTEGRATION = "integration"
    TEST = "test"


# Capability hints. The agent config maps each hint to a real
# provider; the DAG itself never names a specific model.
HINT_FAST = "fast"
HINT_BALANCED = "balanced"
HINT_DEEP = "deep"
KNOWN_HINTS = {HINT_FAST, HINT_BALANCED, HINT_DEEP}

# Map a sub-goal type to a default capability hint. The runner
# can override per-sub-goal via ``SubGoalSpec.model_hint``.
DEFAULT_TYPE_HINT: Dict[SubGoalType, str] = {
    SubGoalType.CODE: HINT_BALANCED,
    SubGoalType.ASSET: HINT_FAST,
    SubGoalType.SCENE: HINT_BALANCED,
    SubGoalType.AUDIO: HINT_FAST,
    SubGoalType.INTEGRATION: HINT_DEEP,
    SubGoalType.TEST: HINT_BALANCED,
}


@dataclass
class SubGoalSpec:
    """One sub-goal in a parent goal's DAG.

    ``depends_on`` references sibling sub-goals by their ``sub_id``;
    the scheduler will not start this sub-goal until every
    dependency has completed successfully.
    """

    sub_id: str
    task: str
    type: SubGoalType
    depends_on: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)
    model_hint: str = HINT_BALANCED
    assigned_agent: str = ""
    artifacts_expected: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complexity_score(self) -> int:
        """Cheap complexity heuristic. Used to size the work estimate
        on the goal's evidence and to flag sub-goals that may need
        further decomposition. The signals are *boundary* signals,
        not source-size signals."""
        score = 1
        score += len(self.acceptance)
        score += len(self.depends_on)
        if self.assigned_agent:
            score += 1
        if self.type in {SubGoalType.INTEGRATION, SubGoalType.CODE}:
            score += 1
        if self.model_hint == HINT_DEEP:
            score += 1
        return score

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the spec to a JSON-safe dict for evidence / events."""
        return {
            "sub_id": self.sub_id,
            "task": self.task,
            "type": self.type.value,
            "depends_on": list(self.depends_on),
            "acceptance": list(self.acceptance),
            "model_hint": self.model_hint,
            "assigned_agent": self.assigned_agent,
            "artifacts_expected": list(self.artifacts_expected),
            "metadata": dict(self.metadata),
            "complexity": self.complexity_score(),
        }


@dataclass
class SubGoalResult:
    """One sub-goal's outcome after the scheduler has run it."""

    spec: SubGoalSpec
    status: str  # "done" | "needs_fix" | "blocked" | "skipped"
    output: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0
    error: str = ""

    @property
    def sub_id(self) -> str:
        """Convenience accessor mirroring the spec id."""
        return self.spec.sub_id

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the sub-goal result to a JSON-safe dict for evidence / events."""
        return {
            "sub_id": self.spec.sub_id,
            "task": self.spec.task,
            "type": self.spec.type.value,
            "depends_on": list(self.spec.depends_on),
            "acceptance": list(self.spec.acceptance),
            "model_hint": self.spec.model_hint,
            "status": self.status,
            "output": dict(self.output),
            "artifacts": list(self.artifacts),
            "elapsed_ms": round(self.elapsed_ms, 1),
            "error": self.error,
            "complexity": self.spec.complexity_score(),
        }


# A sub-goal runner is the per-type execution hook. It receives
# the spec and returns a SubGoalResult. GoalLoop injects a runner
# per type at goal construction time.
SubGoalRunner = Callable[[SubGoalSpec, str, str], SubGoalResult]


class GoalDAGError(RuntimeError):
    """Raised when the DAG cannot be built or executed safely."""


# ---------------------------------------------------------------------------
# DAG build and validation
# ---------------------------------------------------------------------------


def _validate_dag(specs: List[SubGoalSpec]) -> None:
    """Reject cycles, missing dependencies, duplicate sub-ids."""
    seen: Set[str] = set()
    for spec in specs:
        if spec.sub_id in seen:
            raise GoalDAGError(f"duplicate sub_id: {spec.sub_id}")
        seen.add(spec.sub_id)
    ids = {spec.sub_id for spec in specs}
    for spec in specs:
        for dep in spec.depends_on:
            if dep not in ids:
                raise GoalDAGError(
                    f"sub-goal {spec.sub_id} depends on unknown {dep}"
                )
    # Cycle detection via DFS coloring.
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {s.sub_id: WHITE for s in specs}

    def visit(node: str) -> None:
        if color[node] == GRAY:
            raise GoalDAGError(f"cycle detected involving {node}")
        if color[node] == BLACK:
            return
        color[node] = GRAY
        for dep in next(s for s in specs if s.sub_id == node).depends_on:
            visit(dep)
        color[node] = BLACK

    for spec in specs:
        if color[spec.sub_id] == WHITE:
            visit(spec.sub_id)


def topological_layers(specs: List[SubGoalSpec]) -> List[List[SubGoalSpec]]:
    """Return a list of layers where every sub-goal in layer N only
    depends on sub-goals in earlier layers. The caller can fan out
    within a layer (all sub-goals in the same layer are independent)."""
    _validate_dag(specs)
    layers: List[List[SubGoalSpec]] = []
    remaining = list(specs)
    completed: Set[str] = set()
    while remaining:
        ready = [
            spec for spec in remaining
            if all(dep in completed for dep in spec.depends_on)
        ]
        if not ready:
            raise GoalDAGError("DAG has unresolvable dependencies")
        layers.append(ready)
        completed.update(spec.sub_id for spec in ready)
        remaining = [s for s in remaining if s.sub_id not in completed]
    return layers


# ---------------------------------------------------------------------------
# Synchronous DAG executor. GoalLoop uses this when sub-agents are
# in-process. Tests use it directly.
# ---------------------------------------------------------------------------


class GoalDAGScheduler:
    """Run a DAG of sub-goals, bounded by ``max_concurrent``."""

    def __init__(
        self,
        runners: Dict[SubGoalType, SubGoalRunner],
        *,
        max_concurrent: int = 3,
    ) -> None:
        self.runners = dict(runners)
        self.max_concurrent = max(1, int(max_concurrent or 1))
        if not self.runners:
            raise GoalDAGError("at least one runner is required")

    def run(
        self,
        specs: List[SubGoalSpec],
        *,
        parent_goal_id: str,
        parent_session_id: str,
    ) -> List[SubGoalResult]:
        """Run the DAG synchronously, layer by layer.

        Independent sub-goals in the same layer are executed
        sequentially within a chunk of size ``max_concurrent``
        (the interface is synchronous — for true concurrency
        see ``AsyncGoalDAGScheduler``). Sub-goals whose
        dependencies did not complete in earlier layers are
        marked ``skipped`` and not dispatched to a runner.
        """
        import time
        layers = topological_layers(specs)
        results: Dict[str, SubGoalResult] = {}
        for layer in layers:
            # Skip sub-goals whose dependencies did not complete
            # successfully in earlier layers. This is what keeps a
            # failed asset sub-goal from triggering an integration
            # run on a half-built system.
            ready: List[SubGoalSpec] = []
            for spec in layer:
                if any(
                    results.get(dep) is None
                    or results[dep].status != "done"
                    for dep in spec.depends_on
                ):
                    results[spec.sub_id] = SubGoalResult(spec=spec, status="skipped")
                    continue
                ready.append(spec)
            chunk_size = self.max_concurrent
            for start in range(0, len(ready), chunk_size):
                chunk = ready[start : start + chunk_size]
                for spec in chunk:
                    runner = self.runners.get(spec.type)
                    if runner is None:
                        results[spec.sub_id] = SubGoalResult(
                            spec=spec,
                            status="blocked",
                            error=f"no runner for type {spec.type.value}",
                        )
                        continue
                    started = time.perf_counter()
                    try:
                        result = runner(spec, parent_goal_id, parent_session_id)
                    except Exception as exc:
                        result = SubGoalResult(
                            spec=spec,
                            status="blocked",
                            error=str(exc)[:400],
                        )
                    result.elapsed_ms = (time.perf_counter() - started) * 1000
                    results[spec.sub_id] = result
        return [results[spec.sub_id] for spec in specs]


# ---------------------------------------------------------------------------
# Async DAG executor. Used when sub-agents are async (e.g. wrapped
# around an actual Agent runner that returns a coroutine).
# ---------------------------------------------------------------------------


class AsyncGoalDAGScheduler:
    """Asynchronous version of the DAG scheduler. Each runner may
    return a coroutine that yields a SubGoalResult. Within a layer,
    sub-goals are awaited concurrently up to ``max_concurrent``."""

    def __init__(
        self,
        runners: Dict[SubGoalType, Callable[[SubGoalSpec, str, str], Awaitable[SubGoalResult]]],
        *,
        max_concurrent: int = 3,
    ) -> None:
        self.runners = dict(runners)
        self.max_concurrent = max(1, int(max_concurrent or 1))

    async def run(
        self,
        specs: List[SubGoalSpec],
        *,
        parent_goal_id: str,
        parent_session_id: str,
    ) -> List[SubGoalResult]:
        """Async counterpart of :meth:`GoalDAGScheduler.run`.

        Within a layer, ready sub-goals are awaited concurrently
        up to ``max_concurrent``. A failed dependency skips
        every sub-goal that depends on it.
        """
        import time
        layers = topological_layers(specs)
        results: Dict[str, SubGoalResult] = {}
        sem = asyncio.Semaphore(self.max_concurrent)

        async def _run_one(spec: SubGoalSpec) -> None:
            runner = self.runners.get(spec.type)
            if runner is None:
                results[spec.sub_id] = SubGoalResult(
                    spec=spec,
                    status="blocked",
                    error=f"no runner for type {spec.type.value}",
                )
                return
            started = time.perf_counter()
            try:
                async with sem:
                    result = await runner(spec, parent_goal_id, parent_session_id)
            except Exception as exc:
                result = SubGoalResult(
                    spec=spec,
                    status="blocked",
                    error=str(exc)[:400],
                )
            result.elapsed_ms = (time.perf_counter() - started) * 1000
            results[spec.sub_id] = result

        for layer in layers:
            ready: List[SubGoalSpec] = []
            for spec in layer:
                if any(
                    results.get(dep) is None
                    or results[dep].status != "done"
                    for dep in spec.depends_on
                ):
                    results[spec.sub_id] = SubGoalResult(spec=spec, status="skipped")
                    continue
                ready.append(spec)
            if ready:
                await asyncio.gather(*[_run_one(spec) for spec in ready])
        return [results[spec.sub_id] for spec in specs]


__all__ = [
    "GOAL_DAG_VERSION",
    "SubGoalType",
    "HINT_FAST",
    "HINT_BALANCED",
    "HINT_DEEP",
    "KNOWN_HINTS",
    "DEFAULT_TYPE_HINT",
    "SubGoalSpec",
    "SubGoalResult",
    "SubGoalRunner",
    "GoalDAGError",
    "GoalDAGScheduler",
    "AsyncGoalDAGScheduler",
    "topological_layers",
]
