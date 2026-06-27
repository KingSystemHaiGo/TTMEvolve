"""Shared-memory promotion, demotion, and conflict rules."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Iterable, List, Tuple


POSITIVE_STATUSES = {
    "pass",
    "passed",
    "success",
    "succeeded",
    "verified",
    "verified_positive",
}
NEGATIVE_STATUSES = {
    "fail",
    "failed",
    "failure",
    "regression",
    "regressed",
    "contradicted",
}
MISLEADING_STATUSES = {"misleading", "misled", "wrong"}
STALE_STATUSES = {"stale", "expired"}
SHARED_VISIBILITIES = {"shared", "public"}


def review_shared_memory_outcome(
    entry: Dict[str, Any],
    evidence: Dict[str, Any],
    *,
    existing_records: Iterable[Dict[str, Any]] = (),
    now: float | None = None,
    misleading_threshold: int = 2,
    stale_after_seconds: float = 90 * 24 * 60 * 60,
) -> Dict[str, Any]:
    """Return an updated entry plus the decision evidence.

    Promotion is intentionally strict: a record can become shared only after
    verified positive task evidence and no unresolved conflict. Demotion is
    triggered by stale evidence, regression evidence, or repeated misleading
    outcomes.
    """
    timestamp = float(now if now is not None else time.time())
    source = dict(entry)
    proof = evidence if isinstance(evidence, dict) else {}
    shared_meta = source.get("shared_memory") if isinstance(source.get("shared_memory"), dict) else {}
    status = _normalize_status(proof.get("status") or proof.get("outcome") or proof.get("result"))
    claim_key = _claim_key(source, proof)
    source["claim_key"] = claim_key

    decision = {
        "status": "unchanged",
        "reason": "No verified shared-memory outcome was supplied.",
        "before_visibility": _normalize_visibility(source.get("visibility")),
        "after_visibility": _normalize_visibility(source.get("visibility")),
        "claim_key": claim_key,
        "verified": bool(proof.get("verified")),
        "task_success": bool(proof.get("task_success")) if "task_success" in proof else None,
        "evidence_refs": _evidence_refs(proof),
        "reviewed_at": timestamp,
    }

    conflicts: List[Dict[str, Any]] = []
    next_meta = dict(shared_meta)
    history = list(next_meta.get("outcomes") or [])
    history.append(_compact_outcome_record(proof, status, timestamp))
    next_meta["outcomes"] = history[-10:]
    next_meta["last_reviewed_at"] = timestamp
    next_meta["last_status"] = status

    if _is_verified_positive(proof, status):
        conflicts = find_shared_memory_conflicts(source, existing_records, now=timestamp)
        if conflicts:
            decision.update({
                "status": "conflict",
                "reason": "Promotion blocked by conflicting shared memory.",
            })
            next_meta["state"] = "conflict"
            next_meta["promotion_blocked"] = True
        else:
            source["visibility"] = "shared"
            next_meta["state"] = "promoted"
            next_meta["promotion_blocked"] = False
            next_meta["last_verified_at"] = timestamp
            next_meta["last_positive_evidence"] = _compact_evidence(proof)
            decision.update({
                "status": "promoted",
                "reason": "Verified positive task evidence allowed sharing.",
                "after_visibility": "shared",
            })
    elif _is_regression(proof, status):
        source["visibility"] = "private"
        next_meta["state"] = "demoted"
        next_meta["demotion_reason"] = status or "regression"
        next_meta["last_negative_evidence"] = _compact_evidence(proof)
        decision.update({
            "status": "demoted",
            "reason": "Regression or contradiction evidence demoted the record.",
            "after_visibility": "private",
        })
    elif _is_misleading(proof, status):
        misleading_count = int(next_meta.get("misleading_count") or 0) + 1
        next_meta["misleading_count"] = misleading_count
        next_meta["last_negative_evidence"] = _compact_evidence(proof)
        if misleading_count >= max(1, int(misleading_threshold)):
            source["visibility"] = "private"
            next_meta["state"] = "demoted"
            next_meta["demotion_reason"] = "repeated_misleading"
            decision.update({
                "status": "demoted",
                "reason": "Repeated misleading evidence reached the demotion threshold.",
                "after_visibility": "private",
            })
        else:
            next_meta["state"] = "watch"
            decision.update({
                "status": "watch",
                "reason": "Misleading evidence recorded below demotion threshold.",
            })
    elif _is_stale(source, proof, status, timestamp, stale_after_seconds):
        source["visibility"] = "private"
        next_meta["state"] = "demoted"
        next_meta["demotion_reason"] = "stale"
        decision.update({
            "status": "demoted",
            "reason": "Stale shared-memory evidence demoted the record.",
            "after_visibility": "private",
        })
    elif _looks_positive_but_unverified(proof, status):
        next_meta["state"] = "insufficient_evidence"
        decision.update({
            "status": "insufficient_evidence",
            "reason": "Positive outcome lacks verified task evidence.",
        })

    decision["after_visibility"] = _normalize_visibility(source.get("visibility"))
    source["shared_memory"] = next_meta
    return {
        "entry": source,
        "decision": decision,
        "conflicts": conflicts,
    }


def find_shared_memory_conflicts(
    candidate: Dict[str, Any],
    existing_records: Iterable[Dict[str, Any]],
    *,
    now: float | None = None,
) -> List[Dict[str, Any]]:
    timestamp = float(now if now is not None else time.time())
    claim_key = str(candidate.get("claim_key") or "").strip()
    if not claim_key:
        return []
    candidate_id = str(candidate.get("id") or "")
    candidate_summary = _normalize_summary(candidate.get("summary"))
    candidate_agent = str(candidate.get("agent_id") or candidate.get("source_agent") or "")
    conflicts: List[Dict[str, Any]] = []
    for record in existing_records:
        if not isinstance(record, dict):
            continue
        if str(record.get("id") or "") == candidate_id:
            continue
        if str(record.get("claim_key") or "").strip() != claim_key:
            continue
        if _normalize_visibility(record.get("visibility")) not in SHARED_VISIBILITIES:
            continue
        existing_agent = str(record.get("agent_id") or record.get("source_agent") or "")
        if existing_agent and candidate_agent and existing_agent == candidate_agent:
            continue
        if _normalize_summary(record.get("summary")) == candidate_summary:
            continue
        conflict = {
            "id": _conflict_id(claim_key, candidate_id, str(record.get("id") or "")),
            "status": "unresolved",
            "claim_key": claim_key,
            "candidate_id": candidate_id,
            "existing_id": record.get("id"),
            "candidate_agent_id": candidate_agent,
            "existing_agent_id": existing_agent,
            "candidate_summary_hash": _summary_hash(candidate.get("summary")),
            "existing_summary_hash": _summary_hash(record.get("summary")),
            "created_at": timestamp,
            "reason": "same_claim_different_summary",
        }
        conflicts.append(conflict)
    return conflicts


def shared_outcome_summary(index: Iterable[Dict[str, Any]], conflicts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    visibility_counts: Dict[str, int] = {}
    state_counts: Dict[str, int] = {}
    for entry in index:
        if not isinstance(entry, dict):
            continue
        visibility = _normalize_visibility(entry.get("visibility"))
        visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        meta = entry.get("shared_memory") if isinstance(entry.get("shared_memory"), dict) else {}
        state = str(meta.get("state") or "unreviewed")
        state_counts[state] = state_counts.get(state, 0) + 1
    conflict_items = [item for item in conflicts if isinstance(item, dict)]
    unresolved = [item for item in conflict_items if item.get("status") != "resolved"]
    return {
        "promotion_rule": "verified_positive_task_evidence_without_unresolved_conflict",
        "demotion_rule": "stale_or_regression_or_repeated_misleading_evidence",
        "default_visibility_rule": "private_until_verified",
        "visibility_counts": visibility_counts,
        "state_counts": state_counts,
        "conflict_count": len(conflict_items),
        "unresolved_conflict_count": len(unresolved),
    }


def _is_verified_positive(evidence: Dict[str, Any], status: str) -> bool:
    return (
        status in POSITIVE_STATUSES
        and evidence.get("verified") is True
        and evidence.get("task_success") is True
        and bool(_evidence_refs(evidence))
    )


def _is_regression(evidence: Dict[str, Any], status: str) -> bool:
    return status in NEGATIVE_STATUSES and (evidence.get("verified") is True or bool(_evidence_refs(evidence)))


def _is_misleading(evidence: Dict[str, Any], status: str) -> bool:
    return status in MISLEADING_STATUSES and (evidence.get("verified") is True or bool(_evidence_refs(evidence)))


def _is_stale(
    entry: Dict[str, Any],
    evidence: Dict[str, Any],
    status: str,
    now: float,
    stale_after_seconds: float,
) -> bool:
    if status in STALE_STATUSES:
        return evidence.get("verified") is True or bool(_evidence_refs(evidence))
    if not evidence.get("check_staleness"):
        return False
    meta = entry.get("shared_memory") if isinstance(entry.get("shared_memory"), dict) else {}
    last_verified_at = _float_or_none(meta.get("last_verified_at"))
    return last_verified_at is not None and now - last_verified_at > stale_after_seconds


def _looks_positive_but_unverified(evidence: Dict[str, Any], status: str) -> bool:
    return status in POSITIVE_STATUSES and not _is_verified_positive(evidence, status)


def _compact_outcome_record(evidence: Dict[str, Any], status: str, reviewed_at: float) -> Dict[str, Any]:
    return {
        "status": status or "unknown",
        "verified": bool(evidence.get("verified")),
        "task_success": evidence.get("task_success"),
        "evidence_refs": _evidence_refs(evidence)[:5],
        "reviewed_at": reviewed_at,
    }


def _compact_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": _normalize_status(evidence.get("status") or evidence.get("outcome") or evidence.get("result")),
        "evidence_refs": _evidence_refs(evidence)[:5],
        "verified": bool(evidence.get("verified")),
        "task_success": evidence.get("task_success"),
    }


def _evidence_refs(evidence: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    for key in ("evidence_refs", "commands", "tests"):
        value = evidence.get(key)
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, Iterable):
            refs.extend(str(item) for item in value if item)
    verification = evidence.get("verification")
    if isinstance(verification, dict):
        for key in ("command", "test", "artifact", "endpoint"):
            if verification.get(key):
                refs.append(str(verification[key]))
    return refs


def _claim_key(entry: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    raw = evidence.get("claim_key") or entry.get("claim_key")
    if raw:
        return str(raw).strip()
    return _summary_hash(entry.get("summary"))


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _normalize_visibility(value: Any) -> str:
    visibility = str(value or "private").strip().lower()
    return visibility if visibility in {"private", "shared", "public"} else "private"


def _normalize_summary(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _summary_hash(value: Any) -> str:
    return hashlib.sha256(_normalize_summary(value).encode("utf-8")).hexdigest()[:16]


def _conflict_id(claim_key: str, candidate_id: str, existing_id: str) -> str:
    payload = json.dumps(
        {
            "claim_key": claim_key,
            "candidate_id": candidate_id,
            "existing_id": existing_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None
