"""Commit-state history for side-effecting tool calls."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class CommitStateStore:
    """Append-only local view of write-like tool outcomes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, observation: Dict[str, Any]) -> None:
        key = observation.get("idempotency_key")
        if not key:
            return
        payload = {
            "idempotency_key": key,
            "tool": observation.get("tool"),
            "committed": observation.get("committed"),
            "observed_at": observation.get("observed_at", time.time()),
            "path": observation.get("path"),
            "error_type": observation.get("error_type"),
            "error": observation.get("error"),
            "reconcile_status": observation.get("reconcile_status"),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def latest(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        found: Optional[Dict[str, Any]] = None
        for item in self.all():
            if item.get("idempotency_key") == idempotency_key:
                found = item
        return found

    def all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        items: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items


RemoteCommitResolver = Callable[[Dict[str, Any]], Dict[str, Any]]


def reconcile_observation(
    project_root: Path,
    observation: Dict[str, Any],
    remote_resolver: Optional[RemoteCommitResolver] = None,
) -> Dict[str, Any]:
    """Best-effort local reconciliation for uncertain side effects.

    Remote Maker side effects need provider-specific task/file ids. Until those
    are available, keep them unknown rather than pretending a retry is safe.
    """

    if observation.get("committed") is not None:
        observation.setdefault("reconcile_status", "not_needed")
        return observation

    tool = str(observation.get("tool", ""))
    path = observation.get("path")
    if tool in {"modify_file", "delete_file"} and isinstance(path, str):
        target = Path(project_root) / path
        if tool == "modify_file":
            observation["committed"] = target.exists()
        elif tool == "delete_file":
            observation["committed"] = not target.exists()
        observation["reconcile_status"] = "verified_local"
        observation["observed_at"] = time.time()
        return observation

    if callable(remote_resolver):
        try:
            remote_result = remote_resolver(dict(observation)) or {}
        except Exception as e:
            observation["reconcile_status"] = "remote_lookup_failed"
            observation["reconcile_hint"] = f"Remote commit lookup failed: {e}"
            observation["observed_at"] = time.time()
            return observation
        if remote_result:
            for key, value in remote_result.items():
                if key in {"idempotency_key", "tool"}:
                    continue
                observation[key] = value
            observation.setdefault("observed_at", time.time())
            if observation.get("committed") is not None:
                return observation
            if observation.get("reconcile_status"):
                return observation

    observation["reconcile_status"] = "unknown"
    observation.setdefault("reconcile_hint", "No local verifier is available for this tool yet.")
    observation["observed_at"] = time.time()
    return observation
