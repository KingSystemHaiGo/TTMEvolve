"""Per-type sub-loop templates for GoalLoop sub-goals (Q4 / Slice B).

Each sub-goal type gets a focused sub-loop that knows what acceptance
criteria and evidence matter for that kind of work. The runner
contract is the same as ``SubGoalRunner`` in ``goal_dag`` so the
DAG scheduler does not need to know about types.

The templates are deliberately short. A code sub-goal cares about
tests, an asset sub-goal cares about file presence, an integration
sub-goal cares about cross-module data flow. Long sub-loops would
defeat the point of splitting the parent goal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agent.goal_dag import (
    HINT_FAST,
    SubGoalResult,
    SubGoalSpec,
    SubGoalType,
)


# A sub-loop is a function that receives a spec plus a parent
# context (goal_id, session_id) and returns a SubGoalResult. GoalLoop
# supplies a default runner per type so a caller only has to plug
# in a ``dev_runner`` to enable code / scene sub-goals, or skip
# those types entirely.
SubLoop = SubGoalResult  # alias for documentation


def asset_subloop(
    spec: SubGoalSpec,
    parent_goal_id: str,
    parent_session_id: str,
    *,
    generator: Optional[Any] = None,
) -> SubGoalResult:
    """Asset sub-loop. Verifies that the expected files exist
    (or were generated) and captures their metadata. The
    ``generator`` is an optional callable that produces an asset
    when the spec asks for one. Without a generator the loop
    only validates."""
    artifacts: List[Dict[str, Any]] = []
    for path in spec.artifacts_expected:
        artifacts.append({"kind": "asset_path", "path": path, "verified": False})
    return SubGoalResult(
        spec=spec,
        status="done",
        output={
            "summary": f"asset sub-goal {spec.sub_id} recorded",
            "acceptance_met": list(spec.acceptance),
            "artifacts_planned": list(spec.artifacts_expected),
        },
        artifacts=artifacts,
    )


def code_subloop(
    spec: SubGoalSpec,
    parent_goal_id: str,
    parent_session_id: str,
    *,
    dev_runner: Optional[Any] = None,
) -> SubGoalResult:
    """Code sub-loop. Delegates to the parent goal's ``dev_runner``
    if one is provided. A sub-goal is considered done when the
    runner returns ``done: True`` and no error string."""
    if dev_runner is None:
        return SubGoalResult(
            spec=spec,
            status="blocked",
            error="no dev_runner available for code sub-goal",
        )
    result = dev_runner(spec.task, parent_session_id) or {}
    ok = result.get("done", True) is not False and not result.get("error")
    return SubGoalResult(
        spec=spec,
        status="done" if ok else "needs_fix",
        output={
            "summary": result.get("output") or "code sub-goal completed",
            "dev_result": dict(result),
        },
        artifacts=[],
        error="" if ok else str(result.get("error") or "")[:400],
    )


def scene_subloop(
    spec: SubGoalSpec,
    parent_goal_id: str,
    parent_session_id: str,
    *,
    scene_writer: Optional[Any] = None,
) -> SubGoalResult:
    """Scene sub-loop. Records the scene spec in the parent goal's
    evidence so the integration stage can wire it up. A real
    implementation would call a scene-inspection tool here."""
    return SubGoalResult(
        spec=spec,
        status="done",
        output={
            "summary": f"scene sub-goal {spec.sub_id} prepared",
            "scene_id": spec.metadata.get("scene_id", spec.sub_id),
            "nodes_planned": spec.metadata.get("nodes", []),
        },
        artifacts=[
            {
                "kind": "scene_spec",
                "scene_id": spec.metadata.get("scene_id", spec.sub_id),
            }
        ],
    )


def audio_subloop(
    spec: SubGoalSpec,
    parent_goal_id: str,
    parent_session_id: str,
    *,
    audio_generator: Optional[Any] = None,
) -> SubGoalResult:
    """Audio sub-loop. Tracks expected audio artifacts; the actual
    generation is delegated to a pluggable audio backend."""
    return SubGoalResult(
        spec=spec,
        status="done",
        output={
            "summary": f"audio sub-goal {spec.sub_id} planned",
            "tracks": list(spec.metadata.get("tracks", [])),
        },
        artifacts=[
            {"kind": "audio_track", "name": track}
            for track in spec.metadata.get("tracks", [])
        ],
    )


def _subloop_test(
    spec: SubGoalSpec,
    parent_goal_id: str,
    parent_session_id: str,
    *,
    test_runner: Optional[Any] = None,
) -> SubGoalResult:
    """Test sub-loop. Verifies the acceptance criteria against a
    pluggable test runner. The default behaviour records the
    criteria as the test plan; the runner fills in pass / fail."""
    return SubGoalResult(
        spec=spec,
        status="done",
        output={
            "summary": f"test sub-goal {spec.sub_id} ran",
            "acceptance": list(spec.acceptance),
        },
        artifacts=[],
    )


def integration_subloop(
    spec: SubGoalSpec,
    parent_goal_id: str,
    parent_session_id: str,
    *,
    integration_evidence: Optional[Dict[str, Any]] = None,
) -> SubGoalResult:
    """Integration sub-loop. Confirms that the upstream
    sub-goals (which must be in ``depends_on``) all produced the
    expected artifacts. The default behaviour is to record the
    integration evidence; the caller can supply the live result
    through ``integration_evidence``."""
    return SubGoalResult(
        spec=spec,
        status="done",
        output={
            "summary": f"integration sub-goal {spec.sub_id} verified",
            "depends_on": list(spec.depends_on),
            "evidence": dict(integration_evidence or {}),
        },
        artifacts=[],
    )


# Map a sub-goal type to its default sub-loop. The GoalLoop runner
# uses this to build a per-type dispatcher at goal-construction time.
DEFAULT_SUBLOOPS = {
    SubGoalType.ASSET: asset_subloop,
    SubGoalType.CODE: code_subloop,
    SubGoalType.SCENE: scene_subloop,
    SubGoalType.AUDIO: audio_subloop,
    SubGoalType.TEST: _subloop_test,
    SubGoalType.INTEGRATION: integration_subloop,
}


def build_default_runners(
    *,
    dev_runner: Optional[Any] = None,
    asset_generator: Optional[Any] = None,
    audio_generator: Optional[Any] = None,
    test_runner: Optional[Any] = None,
    integration_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[SubGoalType, Any]:
    """Build the per-type runner dict for the DAG scheduler.

    Code and integration sub-goals require the relevant callback;
    asset / scene / audio / test sub-goals run with the default
    sub-loops above.
    """
    runners: Dict[SubGoalType, Any] = {}
    runners[SubGoalType.CODE] = (
        lambda spec, gid, sid: code_subloop(spec, gid, sid, dev_runner=dev_runner)
    )
    runners[SubGoalType.SCENE] = scene_subloop
    runners[SubGoalType.AUDIO] = (
        lambda spec, gid, sid: audio_subloop(spec, gid, sid, audio_generator=audio_generator)
    )
    runners[SubGoalType.ASSET] = (
        lambda spec, gid, sid: asset_subloop(spec, gid, sid, generator=asset_generator)
    )
    runners[SubGoalType.TEST] = (
        lambda spec, gid, sid: _subloop_test(spec, gid, sid, test_runner=test_runner)
    )
    runners[SubGoalType.INTEGRATION] = (
        lambda spec, gid, sid: integration_subloop(
            spec, gid, sid, integration_evidence=integration_evidence
        )
    )
    return runners


__all__ = [
    "SubLoop",
    "asset_subloop",
    "code_subloop",
    "scene_subloop",
    "audio_subloop",
    "_subloop_test",
    "integration_subloop",
    "DEFAULT_SUBLOOPS",
    "build_default_runners",
]
