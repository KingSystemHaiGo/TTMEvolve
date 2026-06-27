"""
memory/cold.py — 冷记忆

长期归档：所有轨迹、知识、事件的摘要索引。
使用 JSON 文件作为源文件，向量索引（FAISS + sentence-transformers）作为检索后端，
向量不可用时自动降级为关键词匹配。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import json
import time

from .vector_index import TextChunk, VectorIndex
from .shared_policy import SharedMemoryPolicy
from .shared_outcome import review_shared_memory_outcome, shared_outcome_summary

_KNOWN_WORKSPACE_PROFILES = {"coding", "docs", "maker", "browser", "general"}
_DEFAULT_PROFILE_POLICIES: Dict[str, Dict[str, Any]] = {
    "general": {"include_general": True, "allow_fallback": False},
    "coding": {"include_general": True, "allow_fallback": True},
    "docs": {"include_general": True, "allow_fallback": True},
    "maker": {"include_general": True, "allow_fallback": True},
    "browser": {"include_general": True, "allow_fallback": True},
}


class ColdMemory:
    """冷记忆：长期归档与语义检索。"""

    def __init__(
        self,
        storage_path: Path,
        vector_index_config: Optional[Dict[str, Any]] = None,
        encoder: Optional[Any] = None,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.storage_path / "cold_index.json"
        self._conflicts_path = self.storage_path / "shared_memory_conflicts.json"
        self._index: List[Dict[str, Any]] = []
        self._conflicts: List[Dict[str, Any]] = []

        vi_cfg = vector_index_config or {}
        self._fallback_to_keyword = vi_cfg.get("fallback_to_keyword", True)
        self._profile_policies = _resolve_profile_policies(vi_cfg.get("profile_policies"))
        self._shared_policy_config = vi_cfg.get("shared_memory") if isinstance(vi_cfg.get("shared_memory"), dict) else {}
        self._vector_index = VectorIndex(
            namespace="cold_memory",
            storage_dir=self.storage_path,
            model_name=vi_cfg.get("model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            embedding_dim=vi_cfg.get("embedding_dim"),
            enabled=vi_cfg.get("enabled", True),
            encoder=encoder,
        )

        self._load()
        self._load_conflicts()
        if len(self._vector_index) == 0 and self._index:
            self.rebuild()

    def index(self, item: Dict[str, Any], content: str) -> None:
        self.bulk_index([(item, content)])

    def bulk_index(self, items: Sequence[Tuple[Dict[str, Any], str]]) -> int:
        entries: List[Dict[str, Any]] = []
        chunks: List[TextChunk] = []
        timestamp = time.time()
        for offset, (raw_item, content) in enumerate(items):
            item = dict(raw_item)
            write_policy = SharedMemoryPolicy.from_config(
                self._shared_policy_config,
                agent_id=str(item.get("agent_id") or item.get("source_agent") or "default"),
            )
            item = write_policy.apply_index_metadata(item)
            workspace_profile = _normalize_workspace_profile(
                item.get("workspace_profile") or item.get("profile")
            )
            if not write_policy.can_index(workspace_profile):
                raise PermissionError(f"Agent '{write_policy.agent_id}' cannot index {workspace_profile} memory.")
            extra = _shared_memory_extra_metadata(item)
            entry = {
                **extra,
                "id": item.get("id", f"{timestamp}-{offset}"),
                "type": item.get("type", "unknown"),
                "summary": content[:200],
                "timestamp": item.get("timestamp", timestamp),
                "workspace_profile": workspace_profile,
                "agent_id": item.get("agent_id", "default"),
                "visibility": item.get("visibility", "private"),
            }
            entries.append(entry)
            chunks.append(TextChunk(
                id=entry["id"],
                text=entry.get("summary", ""),
                source=entry.get("type", "unknown"),
                meta=dict(entry),
            ))

        if not entries:
            return 0
        self._index.extend(entries)
        self._save()
        self._vector_index.add(chunks)
        return len(entries)

    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace_profile: str = "general",
        allow_profile_fallback: Optional[bool] = None,
        agent_id: Optional[str] = None,
        shared_policy: Optional[SharedMemoryPolicy] = None,
    ) -> List[Dict[str, Any]]:
        profile = _normalize_workspace_profile(workspace_profile)
        policy = self.profile_policy(profile, top_k=top_k)
        effective_top_k = policy["top_k"]
        memory_policy = shared_policy or self.shared_policy(agent_id)
        filter_fn = _profile_filter(
            profile,
            include_general=policy["include_general"],
            shared_policy=memory_policy,
        )

        results = self._vector_index.search(query, top_k=effective_top_k, filter_fn=filter_fn)
        if results:
            return [chunk.meta for _, chunk in results if chunk.meta]

        if self._fallback_to_keyword:
            keyword_hits = self._keyword_search(
                query,
                effective_top_k,
                workspace_profile=profile,
                include_general=policy["include_general"],
                shared_policy=memory_policy,
            )
            if keyword_hits:
                return keyword_hits

        should_fallback = policy["allow_fallback"] if allow_profile_fallback is None else bool(allow_profile_fallback)
        if should_fallback and profile != "general":
            fallback_results = self._vector_index.search(
                query,
                top_k=effective_top_k,
                filter_fn=_shared_filter(memory_policy),
            )
            if fallback_results:
                return [chunk.meta for _, chunk in fallback_results if chunk.meta]
            if self._fallback_to_keyword:
                return self._keyword_search(
                    query,
                    effective_top_k,
                    shared_policy=memory_policy,
                )
        return []

    def profile_policy(self, workspace_profile: str = "general", top_k: int = 5) -> Dict[str, Any]:
        profile = _normalize_workspace_profile(workspace_profile)
        policy = dict(self._profile_policies.get(profile) or self._profile_policies["general"])
        policy["profile"] = profile
        policy["top_k"] = _positive_int(policy.get("top_k"), top_k)
        policy["include_general"] = bool(policy.get("include_general", profile != "general"))
        policy["allow_fallback"] = bool(policy.get("allow_fallback", profile != "general"))
        return policy

    def shared_policy(self, agent_id: Optional[str] = None) -> SharedMemoryPolicy:
        return SharedMemoryPolicy.from_config(
            self._shared_policy_config,
            agent_id=str(agent_id or "default"),
        )

    def record_shared_outcome(
        self,
        memory_id: str,
        evidence: Dict[str, Any],
        *,
        now: Optional[float] = None,
        misleading_threshold: int = 2,
        stale_after_seconds: float = 90 * 24 * 60 * 60,
    ) -> Dict[str, Any]:
        """Review a cold-memory record for promotion, demotion, or conflict."""
        for index, entry in enumerate(self._index):
            if str(entry.get("id")) != str(memory_id):
                continue
            review = review_shared_memory_outcome(
                entry,
                evidence,
                existing_records=self._index,
                now=now,
                misleading_threshold=misleading_threshold,
                stale_after_seconds=stale_after_seconds,
            )
            self._index[index] = review["entry"]
            for conflict in review.get("conflicts") or []:
                self._append_conflict(conflict)
            self._save()
            self._save_conflicts()
            self.rebuild()
            return {
                "memory_id": memory_id,
                "decision": review["decision"],
                "conflicts": review.get("conflicts") or [],
                "entry": dict(self._index[index]),
            }
        raise KeyError(f"Cold memory record not found: {memory_id}")

    def shared_conflicts(self, *, unresolved_only: bool = False) -> List[Dict[str, Any]]:
        if not unresolved_only:
            return [dict(item) for item in self._conflicts]
        return [
            dict(item)
            for item in self._conflicts
            if item.get("status") != "resolved"
        ]

    def shared_outcome_summary(self) -> Dict[str, Any]:
        return shared_outcome_summary(self._index, self._conflicts)

    def rebuild(self) -> None:
        """从 JSON 源文件重建向量索引。"""
        self._vector_index.clear()
        chunks = [
            TextChunk(
                id=entry["id"],
                text=entry.get("summary", ""),
                source=entry.get("type", "unknown"),
                meta=dict(entry),
            )
            for entry in self._index
        ]
        self._vector_index.add(chunks)

    def _keyword_search(
        self,
        query: str,
        top_k: int,
        workspace_profile: str = "general",
        include_general: bool = True,
        shared_policy: Optional[SharedMemoryPolicy] = None,
    ) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        profile = _normalize_workspace_profile(workspace_profile)
        memory_policy = shared_policy or self.shared_policy()
        hits = []
        for entry in self._index:
            if not _profile_matches_entry(entry, profile, include_general=include_general):
                continue
            if not memory_policy.can_read(entry, profile):
                continue
            score = 0
            if query_lower in entry.get("summary", "").lower():
                score += 1
            if query_lower in entry.get("type", "").lower():
                score += 1
            if score > 0:
                hits.append((score, entry))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in hits[:top_k]]

    def _save(self) -> None:
        self._index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_conflicts(self) -> None:
        self._conflicts_path.write_text(
            json.dumps(self._conflicts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            for entry in self._index:
                entry["workspace_profile"] = _normalize_workspace_profile(
                    entry.get("workspace_profile") or entry.get("profile")
                )
                entry["agent_id"] = str(entry.get("agent_id") or entry.get("source_agent") or "default")
                entry["visibility"] = str(entry.get("visibility") or "private")
        except Exception:
            self._index = []

    def _load_conflicts(self) -> None:
        if not self._conflicts_path.exists():
            return
        try:
            raw = json.loads(self._conflicts_path.read_text(encoding="utf-8"))
            self._conflicts = raw if isinstance(raw, list) else []
        except Exception:
            self._conflicts = []

    def _append_conflict(self, conflict: Dict[str, Any]) -> None:
        conflict_id = conflict.get("id")
        if conflict_id and any(item.get("id") == conflict_id for item in self._conflicts):
            return
        self._conflicts.append(dict(conflict))


def _normalize_workspace_profile(value: Any) -> str:
    profile = str(value or "general").strip().lower()
    return profile if profile in _KNOWN_WORKSPACE_PROFILES else "general"


def _shared_memory_extra_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    extra: Dict[str, Any] = {}
    for key in ("claim_key", "shared_memory", "retention", "outcome"):
        if key in item:
            extra[key] = item[key]
    return extra


def _profile_matches_entry(
    entry: Dict[str, Any],
    profile: str,
    include_general: bool = True,
) -> bool:
    if profile == "general":
        return True
    entry_profile = _normalize_workspace_profile(
        entry.get("workspace_profile") or entry.get("profile")
    )
    if entry_profile == profile:
        return True
    return include_general and entry_profile == "general"


def _profile_filter(
    profile: str,
    include_general: bool = True,
    shared_policy: Optional[SharedMemoryPolicy] = None,
):
    if profile == "general":
        return _shared_filter(shared_policy)

    def matches(chunk: TextChunk) -> bool:
        meta = chunk.meta or {}
        if not _profile_matches_entry(
            meta,
            profile,
            include_general=include_general,
        ):
            return False
        if shared_policy is not None and not shared_policy.can_read(meta, profile):
            return False
        return True

    return matches


def _shared_filter(shared_policy: Optional[SharedMemoryPolicy]):
    if shared_policy is None:
        return None

    def matches(chunk: TextChunk) -> bool:
        return shared_policy.can_read(
            chunk.meta or {},
            _normalize_workspace_profile((chunk.meta or {}).get("workspace_profile")),
        )

    return matches


def _resolve_profile_policies(raw: Any) -> Dict[str, Dict[str, Any]]:
    policies = {profile: dict(policy) for profile, policy in _DEFAULT_PROFILE_POLICIES.items()}
    if not isinstance(raw, dict):
        return policies
    for key, value in raw.items():
        profile = _normalize_workspace_profile(key)
        if not isinstance(value, dict):
            continue
        next_policy = dict(policies.get(profile, policies["general"]))
        for field in ("top_k", "include_general", "allow_fallback"):
            if field in value:
                next_policy[field] = value[field]
        policies[profile] = next_policy
    return policies


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = int(default)
    return max(1, number)
