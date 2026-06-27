"""Bridge validated learning insights into cold shared-memory outcomes."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_SHAREABLE_TAGS = {
    "lesson",
    "skill",
    "expert_rescue",
    "shared_memory",
    "architecture",
    "rag",
    "memory",
    "tool_validation",
}
PRIVATE_TAGS = {"private", "secret", "credential", "personal", "user_private"}
VERIFICATION_TOOLS = {
    "execute_shell",
    "maker_build",
    "maker_build_current_directory",
    "pytest",
    "npm_build",
}


def archive_learning_insights_to_shared_memory(
    cold_memory: Any,
    *,
    session_id: str,
    task: str,
    insights: Iterable[Dict[str, Any]],
    result: Optional[Dict[str, Any]] = None,
    agent_id: str = "default",
    workspace_profile: str = "general",
    now: Optional[float] = None,
    min_confidence: float = 0.7,
) -> Dict[str, Any]:
    """Archive insights privately, then request sharing only with evidence."""
    result = result if isinstance(result, dict) else {}
    evidence = learning_outcome_evidence(session_id=session_id, result=result)
    records: List[Dict[str, Any]] = []
    for index, raw in enumerate(insights):
        if not isinstance(raw, dict):
            continue
        insight = dict(raw)
        memory_id = str(insight.get("memory_id") or insight.get("id") or f"learning-{session_id}-{index}")
        content = _insight_content(insight)
        if not content:
            continue
        claim_key = str(insight.get("claim_key") or _claim_key(insight))
        meta = {
            "id": memory_id,
            "type": "learning_insight",
            "workspace_profile": _workspace_profile(insight.get("workspace_profile") or workspace_profile),
            "agent_id": str(insight.get("agent_id") or agent_id),
            "visibility": "private",
            "claim_key": claim_key,
            "shared_memory": {
                "state": "pending_validation",
                "source": "learning",
                "source_session": session_id,
            },
        }
        cold_memory.index(meta, content)
        record = {
            "memory_id": memory_id,
            "claim_key": claim_key,
            "archived": True,
            "shareable": is_shareable_insight(insight, min_confidence=min_confidence),
            "decision": {
                "status": "archived_private",
                "after_visibility": "private",
                "reason": "Insight archived privately until shareable evidence is available.",
            },
            "conflicts": [],
        }
        if record["shareable"]:
            outcome = dict(evidence)
            outcome["claim_key"] = claim_key
            review = cold_memory.record_shared_outcome(memory_id, outcome, now=now)
            record["decision"] = review.get("decision", {})
            record["conflicts"] = review.get("conflicts", [])
        records.append(record)

    promoted = sum(1 for item in records if (item.get("decision") or {}).get("status") == "promoted")
    conflicts = sum(len(item.get("conflicts") or []) for item in records)
    private = sum(1 for item in records if (item.get("decision") or {}).get("after_visibility") == "private")
    return {
        "version": "learning-shared-memory.v1",
        "session_id": session_id,
        "task": task,
        "agent_id": agent_id,
        "workspace_profile": workspace_profile,
        "evidence": evidence,
        "records": records,
        "counts": {
            "archived": len(records),
            "promoted": promoted,
            "private": private,
            "conflicts": conflicts,
        },
    }


def learning_outcome_evidence(*, session_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    refs = _verification_refs(result.get("trajectory") or [])
    task_success = bool(result.get("output")) and not bool(result.get("cancelled"))
    verified = task_success and bool(refs)
    return {
        "status": "verified_positive" if verified else "success",
        "verified": verified,
        "task_success": task_success,
        "source_session": session_id,
        "evidence_refs": refs,
        "verification": {
            "artifact": f"session:{session_id}",
        },
    }


def is_shareable_insight(insight: Dict[str, Any], *, min_confidence: float = 0.7) -> bool:
    tags = {str(tag).strip().lower() for tag in insight.get("tags", []) if str(tag).strip()}
    if tags & PRIVATE_TAGS:
        return False
    try:
        confidence = float(insight.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    if confidence < float(min_confidence):
        return False
    if insight.get("shareable") is False:
        return False
    if insight.get("shareable") is True:
        return True
    return bool(tags & DEFAULT_SHAREABLE_TAGS)


def _verification_refs(trajectory: Iterable[Dict[str, Any]]) -> List[str]:
    refs: List[str] = []
    for step in trajectory:
        if not isinstance(step, dict):
            continue
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
        if observation.get("ok") is not True:
            continue
        tool = str(observation.get("tool") or action.get("tool") or "").strip()
        output = str(observation.get("output") or observation.get("stdout") or observation.get("summary") or "")
        marker = f"{tool} {output}".lower()
        if tool in VERIFICATION_TOOLS or " passed" in marker or "build" in marker or "verified" in marker:
            refs.append(_compact_ref(tool, output))
    return refs[:8]


def _compact_ref(tool: str, output: str) -> str:
    compact = " ".join(str(output or "").split())
    if len(compact) > 160:
        compact = compact[:157] + "..."
    return f"{tool or 'observation'}: {compact}" if compact else str(tool or "verified observation")


def _insight_content(insight: Dict[str, Any]) -> str:
    parts = [
        str(insight.get("rule") or "").strip(),
        str(insight.get("context") or "").strip(),
    ]
    tags = " ".join(str(tag) for tag in insight.get("tags", []) if tag)
    if tags:
        parts.append(tags)
    return "\n".join(part for part in parts if part)


def _claim_key(insight: Dict[str, Any]) -> str:
    domain = str(insight.get("domain") or "general").strip().lower()
    rule = re.sub(r"\s+", " ", str(insight.get("rule") or "").strip().lower())
    digest = hashlib.sha256(f"{domain}:{rule}".encode("utf-8")).hexdigest()[:16]
    return f"{domain}:{digest}"


def _workspace_profile(value: Any) -> str:
    profile = str(value or "general").strip().lower()
    return profile if profile in {"coding", "docs", "maker", "browser", "general"} else "general"
