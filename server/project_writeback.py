"""Safe project-control writeback planning and application.

The writeback path turns COS project-control evidence into append-only project
memory updates. It is intentionally explicit: GET can inspect the plan, while
POST with an apply flag is required before files are touched.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_WRITEBACK_VERSION = "project-writeback.v1"
ALLOWED_PROJECT_WRITEBACK_FILES = {
    "docs/memory-index.md",
    "docs/sprint-board.md",
    "docs/memory-health.md",
}
BLOCKING_CONTROL_STATUSES = {"blocked", "needs_confirmation"}


def build_project_writeback_plan(
    *,
    project_root: Path,
    session_id: str,
    project_state: Dict[str, Any],
    project_control: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build an append-only POST memory writeback plan."""
    root = Path(project_root).resolve()
    project_state = project_state if isinstance(project_state, dict) else {}
    project_control = project_control if isinstance(project_control, dict) else {}
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")

    blockers = _blocking_reasons(project_control)
    due_items = _due_items(project_control)
    base: Dict[str, Any] = {
        "version": PROJECT_WRITEBACK_VERSION,
        "session_id": session_id,
        "status": "instrumented",
        "applicable": False,
        "source": "project_control.memory_updates_due",
        "project_root": str(root),
        "timestamp": timestamp,
        "operations": [],
        "invalid_targets": [],
        "reason": "",
    }

    if blockers:
        return {
            **base,
            "status": "blocked",
            "reason": blockers[0],
            "blockers": blockers,
        }
    if not due_items:
        return {
            **base,
            "status": "no_updates_due",
            "reason": "project_control.memory_updates_due is empty",
        }

    operations: List[Dict[str, Any]] = []
    invalid_targets: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in due_items:
        gate = str(item.get("gate") or "POST")
        file_path = str(item.get("file") or "").strip()
        rel_path, target, error = _resolve_allowed_target(root, file_path)
        if error or rel_path is None or target is None:
            invalid_targets.append({
                "gate": gate,
                "file": file_path,
                "reason": error or "invalid target",
            })
            continue
        if rel_path in seen:
            continue
        seen.add(rel_path)
        marker = _marker(session_id=session_id, file_path=rel_path)
        existing = _read_text_if_exists(target)
        already_applied = marker in existing
        status = "already_applied" if already_applied else ("pending_append" if target.exists() else "pending_create")
        content = _render_writeback_content(
            marker=marker,
            timestamp=timestamp,
            session_id=session_id,
            gate=gate,
            file_path=rel_path,
            project_state=project_state,
            project_control=project_control,
        )
        operations.append({
            "action": "append",
            "status": status,
            "gate": gate,
            "file": rel_path,
            "marker": marker,
            "content": content,
        })

    if invalid_targets:
        return {
            **base,
            "status": "blocked",
            "reason": "One or more writeback targets are outside the allowed POST document set.",
            "invalid_targets": invalid_targets,
            "operations": [],
        }
    if not operations:
        return {
            **base,
            "status": "no_updates_due",
            "reason": "No valid writeback operations were produced.",
        }
    if all(operation.get("status") == "already_applied" for operation in operations):
        return {
            **base,
            "status": "already_applied",
            "applicable": False,
            "operations": operations,
            "reason": "All writeback markers already exist.",
        }
    return {
        **base,
        "status": "ready",
        "applicable": True,
        "operations": operations,
        "reason": "Ready for explicit append-only writeback.",
    }


def apply_project_writeback_plan(project_root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a previously built writeback plan with path and marker checks."""
    root = Path(project_root).resolve()
    plan = plan if isinstance(plan, dict) else {}
    status = str(plan.get("status") or "")
    operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
    if status in {"blocked", "no_updates_due", "instrumented"} or not operations:
        return {
            "version": PROJECT_WRITEBACK_VERSION,
            "session_id": plan.get("session_id"),
            "status": status or "blocked",
            "applied_count": 0,
            "skipped_count": 0,
            "errors": [],
            "plan_status": status,
        }

    applied: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        file_path = str(operation.get("file") or "")
        rel_path, target, error = _resolve_allowed_target(root, file_path)
        if error or rel_path is None or target is None:
            errors.append({"file": file_path, "reason": error or "invalid target"})
            continue
        marker = str(operation.get("marker") or _marker(session_id=str(plan.get("session_id") or ""), file_path=rel_path))
        content = str(operation.get("content") or "")
        existing = _read_text_if_exists(target)
        if marker and marker in existing:
            skipped.append({"file": rel_path, "reason": "already_applied"})
            continue
        if not marker or marker not in content:
            errors.append({"file": rel_path, "reason": "operation content is missing its idempotency marker"})
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            _append_text(target, content)
        except Exception as exc:
            errors.append({"file": rel_path, "reason": str(exc)})
            continue
        applied.append({"file": rel_path, "marker": marker})

    if errors and applied:
        result_status = "partial"
    elif errors:
        result_status = "failed"
    elif applied:
        result_status = "applied"
    elif skipped:
        result_status = "already_applied"
    else:
        result_status = "no_updates_due"
    return {
        "version": PROJECT_WRITEBACK_VERSION,
        "session_id": plan.get("session_id"),
        "status": result_status,
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "plan_status": status,
    }


def compact_project_writeback(plan_or_result: Dict[str, Any]) -> Dict[str, Any]:
    """Return a small evidence-safe project-writeback summary."""
    value = plan_or_result if isinstance(plan_or_result, dict) else {}
    operations = value.get("operations") if isinstance(value.get("operations"), list) else []
    invalid = value.get("invalid_targets") if isinstance(value.get("invalid_targets"), list) else []
    return {
        "version": value.get("version") or PROJECT_WRITEBACK_VERSION,
        "session_id": value.get("session_id"),
        "status": value.get("status") or "missing",
        "applicable": bool(value.get("applicable", False)),
        "operation_count": len(operations),
        "files": [
            str(operation.get("file"))
            for operation in operations
            if isinstance(operation, dict) and operation.get("file")
        ],
        "invalid_target_count": len(invalid),
        "reason": value.get("reason") or "",
        "endpoint": value.get("endpoint") or (
            f"/sessions/{value.get('session_id')}/project-writeback"
            if value.get("session_id")
            else "/sessions/{session_id}/project-writeback"
        ),
    }


def _due_items(project_control: Dict[str, Any]) -> List[Dict[str, Any]]:
    due = project_control.get("memory_updates_due")
    if not isinstance(due, list):
        return []
    return [item for item in due if isinstance(item, dict)]


def _blocking_reasons(project_control: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    status = str(project_control.get("status") or "")
    if status in BLOCKING_CONTROL_STATUSES:
        reasons.append(f"project_control status is {status}")
    blockers = project_control.get("blockers")
    if isinstance(blockers, list):
        for blocker in blockers:
            if not isinstance(blocker, dict):
                continue
            if blocker.get("severity") == "blocker":
                reasons.append(str(blocker.get("detail") or blocker.get("id") or "project-control blocker"))
    verification = project_control.get("verification")
    if isinstance(verification, dict) and verification.get("status") == "blocked":
        reasons.append(str(verification.get("rule") or "project-control verification is blocked"))
    return reasons


def _resolve_allowed_target(root: Path, file_path: str) -> Tuple[Optional[str], Optional[Path], Optional[str]]:
    rel_path = _normalize_relative_path(file_path)
    if not rel_path:
        return None, None, "file path is empty or absolute"
    if rel_path not in ALLOWED_PROJECT_WRITEBACK_FILES:
        return rel_path, None, "target is not an allowed project writeback file"
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return rel_path, None, "target escapes project root"
    return rel_path, target, None


def _normalize_relative_path(file_path: str) -> Optional[str]:
    raw = str(file_path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or PureWindowsPath(raw).drive:
        return None
    parts = [part for part in raw.split("/") if part]
    if any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _marker(*, session_id: str, file_path: str) -> str:
    return (
        "<!-- TTMEVOLVE-PROJECT-WRITEBACK "
        f"session_id={session_id} file={file_path} version={PROJECT_WRITEBACK_VERSION} -->"
    )


def _render_writeback_content(
    *,
    marker: str,
    timestamp: str,
    session_id: str,
    gate: str,
    file_path: str,
    project_state: Dict[str, Any],
    project_control: Dict[str, Any],
) -> str:
    title = "Project Control Sprint Sync" if file_path == "docs/sprint-board.md" else "Project Control Memory Note"
    verification = project_control.get("verification") if isinstance(project_control.get("verification"), dict) else {}
    truth = project_control.get("truthfulness") if isinstance(project_control.get("truthfulness"), dict) else {}
    required_gates = _join(project_control.get("required_gates"))
    pending_gates = _join(project_control.get("pending_gates"))
    blockers = project_control.get("blockers") if isinstance(project_control.get("blockers"), list) else []
    blocker_summary = _blocker_summary(blockers)
    task = project_state.get("task") or project_control.get("current_focus") or "-"
    next_action = project_control.get("next_action") or project_state.get("next_action") or "-"
    lines = [
        marker,
        f"## {timestamp} {title}",
        "",
        "- source: `project_control`",
        f"- session_id: `{session_id}`",
        f"- gate: `{gate}`",
        f"- status: `{project_control.get('status') or '-'}`",
        f"- task: {task}",
        f"- next_action: {next_action}",
        f"- verification: `{verification.get('status') or '-'}`",
        f"- required_gates: {required_gates}",
        f"- pending_gates: {pending_gates}",
        f"- blockers: {blocker_summary}",
        f"- truthfulness: {truth.get('rule') or verification.get('rule') or 'Strong claims require evidence.'}",
        "",
    ]
    return "\n".join(lines)


def _join(value: Any) -> str:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return "-"
    items = [str(item) for item in value if item]
    return ", ".join(items) if items else "-"


def _blocker_summary(blockers: List[Any]) -> str:
    items: List[str] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        detail = blocker.get("detail") or blocker.get("id")
        if detail:
            items.append(str(detail))
    return "; ".join(items) if items else "-"


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _append_text(path: Path, content: str) -> None:
    existing = _read_text_if_exists(path)
    prefix = ""
    if existing and not existing.endswith("\n"):
        prefix = "\n"
    elif existing and not existing.endswith("\n\n"):
        prefix = "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + content.rstrip() + "\n")

