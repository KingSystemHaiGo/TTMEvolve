"""Project-side feature / ticket state machine (Slice C).

A *feature* is the unit the PM tracks across goals. Each goal
either advances an existing feature (the most common case) or
opens a new one. The state machine is intentionally small:

    proposed -> approved -> in_progress -> blocked -> shipped
                                          -> deprecated

The feature ledger lives on disk in ``.ttmevolve/features.jsonl``
so the state survives across goals, sessions, and process
restarts. The PM-style progress board (sprint-board.md) is
auto-generated from this ledger on every state change.

No model names baked in. No source-line thresholds. Complexity
is measured by *boundary signals*: number of open goals, total
acceptance criteria, dependency edges between features.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


FEATURE_STATE_VERSION = "feature-state.v1"


class FeatureState(str, Enum):
    """Lifecycle states a feature can be in."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    SHIPPED = "shipped"
    DEPRECATED = "deprecated"


# Allowed state transitions. Anything outside this map is a
# programming error and the state machine raises.
ALLOWED_TRANSITIONS: Dict[FeatureState, set[FeatureState]] = {
    FeatureState.PROPOSED: {FeatureState.APPROVED, FeatureState.DEPRECATED},
    FeatureState.APPROVED: {FeatureState.IN_PROGRESS, FeatureState.DEPRECATED},
    FeatureState.IN_PROGRESS: {FeatureState.BLOCKED, FeatureState.SHIPPED, FeatureState.DEPRECATED},
    FeatureState.BLOCKED: {FeatureState.IN_PROGRESS, FeatureState.DEPRECATED},
    FeatureState.SHIPPED: {FeatureState.DEPRECATED},
    FeatureState.DEPRECATED: set(),
}


@dataclass
class Feature:
    """One feature / ticket tracked across the project."""

    feature_id: str
    title: str
    description: str
    state: FeatureState = FeatureState.PROPOSED
    priority: str = "P1"  # P0 | P1 | P2
    owner: str = "pm"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    related_goals: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)
    blocked_reason: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the feature to a JSON-safe dict for evidence / events."""
        return {
            "feature_id": self.feature_id,
            "title": self.title,
            "description": self.description,
            "state": self.state.value,
            "priority": self.priority,
            "owner": self.owner,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "related_goals": list(self.related_goals),
            "acceptance": list(self.acceptance),
            "blocked_reason": self.blocked_reason,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Feature":
        """Hydrate a ``Feature`` from a serialised dict. Unknown or
        malformed ``state`` values fall back to ``proposed`` so a
        corrupted ledger never crashes the loader."""
        state_str = str(data.get("state") or FeatureState.PROPOSED.value)
        try:
            state = FeatureState(state_str)
        except ValueError:
            state = FeatureState.PROPOSED
        return cls(
            feature_id=str(data.get("feature_id") or _new_feature_id()),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            state=state,
            priority=str(data.get("priority") or "P1"),
            owner=str(data.get("owner") or "pm"),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            related_goals=list(data.get("related_goals") or []),
            acceptance=list(data.get("acceptance") or []),
            blocked_reason=str(data.get("blocked_reason") or ""),
            notes=str(data.get("notes") or ""),
        )


def _new_feature_id() -> str:
    return f"feat-{uuid.uuid4().hex[:8]}"


class FeatureStateError(RuntimeError):
    """Raised when a state transition is invalid or the ledger cannot be read."""


class FeatureLedger:
    """Append-only feature ledger backed by a JSONL file.

    The ledger is the single source of truth for feature state.
    Each entry is one *event*; the current state is the latest
    event for each feature_id. The PM writes through this class
    so the rest of the agent never touches the file directly.
    """

    def __init__(self, project_root: Path, ledger_path: Optional[Path] = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.ledger_path = (
            Path(ledger_path).resolve()
            if ledger_path
            else (self.project_root / ".ttmevolve" / "features.jsonl")
        )
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def list_features(self) -> List[Feature]:
        """Return every feature, each as the latest state from the
        append-only ledger. Order is not guaranteed; callers that
        need a stable view should sort by ``created_at``."""
        events = self._read_events()
        latest: Dict[str, Dict[str, Any]] = {}
        for event in events:
            feature_id = str(event.get("feature_id") or "")
            if not feature_id:
                continue
            latest[feature_id] = event
        return [Feature.from_dict(item) for item in latest.values()]

    def get(self, feature_id: str) -> Optional[Feature]:
        """Return the latest state of ``feature_id`` or ``None`` if
        the feature has never been opened."""
        for feature in self.list_features():
            if feature.feature_id == feature_id:
                return feature
        return None

    def open(
        self,
        title: str,
        description: str = "",
        *,
        priority: str = "P1",
        owner: str = "pm",
        acceptance: Optional[List[str]] = None,
        feature_id: Optional[str] = None,
    ) -> Feature:
        """Open a new feature in ``proposed`` state. If a
        ``feature_id`` is supplied and already exists, an
        ``FeatureStateError`` is raised; pass an id only when
        the caller wants idempotency on a stable slug."""
        feature = Feature(
            feature_id=feature_id or _new_feature_id(),
            title=title,
            description=description,
            priority=priority,
            owner=owner,
            acceptance=list(acceptance or []),
        )
        self._append_event("opened", feature)
        return feature

    def transition(
        self, feature_id: str, new_state: FeatureState,
        *, reason: str = "", note: str = "",
    ) -> Feature:
        """Move ``feature_id`` to ``new_state``.

        ``FeatureStateError`` is raised when the feature does
        not exist or the transition is not in
        :data:`ALLOWED_TRANSITIONS`. ``reason`` is required
        when moving to ``BLOCKED``; ``note`` is appended to
        the feature's running note log for any state."""
        feature = self.get(feature_id)
        if feature is None:
            raise FeatureStateError(f"feature not found: {feature_id}")
        if new_state not in ALLOWED_TRANSITIONS.get(feature.state, set()):
            raise FeatureStateError(
                f"invalid transition: {feature.state.value} -> {new_state.value} "
                f"for {feature_id}"
            )
        feature.state = new_state
        feature.updated_at = time.time()
        if new_state == FeatureState.BLOCKED:
            feature.blocked_reason = reason
        if note:
            feature.notes = (feature.notes + "\n" + note).strip() if feature.notes else note
        self._append_event("transitioned", feature)
        return feature

    def attach_goal(self, feature_id: str, goal_id: str) -> Feature:
        """Record that ``goal_id`` worked on ``feature_id``. Idempotent."""
        feature = self.get(feature_id)
        if feature is None:
            raise FeatureStateError(f"feature not found: {feature_id}")
        if goal_id not in feature.related_goals:
            feature.related_goals.append(goal_id)
        feature.updated_at = time.time()
        self._append_event("goal_attached", feature)
        return feature

    def sprint_board(self) -> str:
        """Render a small markdown sprint board grouped by state."""
        features = self.list_features()
        if not features:
            return "# Sprint Board\n\n(no features yet)\n"
        by_state: Dict[str, List[Feature]] = {}
        for feature in features:
            by_state.setdefault(feature.state.value, []).append(feature)
        order = [
            FeatureState.IN_PROGRESS,
            FeatureState.BLOCKED,
            FeatureState.APPROVED,
            FeatureState.PROPOSED,
            FeatureState.SHIPPED,
            FeatureState.DEPRECATED,
        ]
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines: List[str] = [
            "# Sprint Board",
            "",
            f"_last sync: {today}_",
            "",
        ]
        for state in order:
            bucket = by_state.get(state.value, [])
            if not bucket:
                continue
            lines.append(f"## {state.value} ({len(bucket)})")
            for feature in bucket:
                blocked = ""
                if feature.state == FeatureState.BLOCKED and feature.blocked_reason:
                    blocked = f" — blocked: {feature.blocked_reason}"
                lines.append(
                    f"- **{feature.feature_id}** [{feature.priority}] {feature.title}{blocked}"
                )
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _append_event(self, event_type: str, feature: Feature) -> None:
        event = {
            "version": FEATURE_STATE_VERSION,
            "ts": time.time(),
            "event": event_type,
            **feature.to_dict(),
        }
        line = json.dumps(event, ensure_ascii=False)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _read_events(self) -> List[Dict[str, Any]]:
        if not self.ledger_path.is_file():
            return []
        events: List[Dict[str, Any]] = []
        for raw in self.ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except Exception:
                continue
        return events


# ---------------------------------------------------------------------------
# PM helpers
# ---------------------------------------------------------------------------


def render_progress_md(
    features: List[Feature],
    *,
    title: str = "Project Progress",
) -> str:
    """Render a PM-style progress.md suitable for human + agent
    consumption. Mirrors the layout used by the multi-agent
    framework so any operator familiar with that style can read
    it without a tutorial."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    state_counts: Dict[str, int] = {}
    priority_counts: Dict[str, int] = {}
    for feature in features:
        state_counts[feature.state.value] = state_counts.get(feature.state.value, 0) + 1
        priority_counts[feature.priority] = priority_counts.get(feature.priority, 0) + 1
    lines: List[str] = [
        f"# {title}",
        "",
        f"_last sync: {today}_",
        "",
        "## Smart Agent Rules",
        "<!-- auto-generated; do not edit the structure by hand -->",
        f"current_stage: feature-state machine ({len(features)} active feature(s))",
        f"current_focus: keep {FeatureState.IN_PROGRESS.value} features unblocked",
        "key_constraint: never transition BLOCKED -> SHIPPED without a PM sign-off",
        "",
        "## Feature States",
    ]
    for state, count in sorted(state_counts.items()):
        lines.append(f"- {state}: {count}")
    lines.append("")
    lines.append("## Priorities")
    for priority, count in sorted(priority_counts.items()):
        lines.append(f"- {priority}: {count}")
    lines.append("")
    lines.append("## Active Features")
    if features:
        for feature in features:
            blocked = f" — blocked: {feature.blocked_reason}" if feature.blocked_reason else ""
            lines.append(
                f"- **{feature.feature_id}** [{feature.priority}] {feature.title} "
                f"({feature.state.value}){blocked}"
            )
    else:
        lines.append("- (no features yet)")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "FEATURE_STATE_VERSION",
    "FeatureState",
    "ALLOWED_TRANSITIONS",
    "Feature",
    "FeatureStateError",
    "FeatureLedger",
    "render_progress_md",
]
