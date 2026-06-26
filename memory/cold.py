"""
memory/cold.py — 冷记忆

长期归档：所有轨迹、知识、事件的摘要索引。
使用 JSON 文件作为源文件，向量索引（FAISS + sentence-transformers）作为检索后端，
向量不可用时自动降级为关键词匹配。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import time

from .vector_index import TextChunk, VectorIndex

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
        self._index: List[Dict[str, Any]] = []

        vi_cfg = vector_index_config or {}
        self._fallback_to_keyword = vi_cfg.get("fallback_to_keyword", True)
        self._profile_policies = _resolve_profile_policies(vi_cfg.get("profile_policies"))
        self._vector_index = VectorIndex(
            namespace="cold_memory",
            storage_dir=self.storage_path,
            model_name=vi_cfg.get("model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            embedding_dim=vi_cfg.get("embedding_dim"),
            enabled=vi_cfg.get("enabled", True),
            encoder=encoder,
        )

        self._load()
        if len(self._vector_index) == 0 and self._index:
            self.rebuild()

    def index(self, item: Dict[str, Any], content: str) -> None:
        entry = {
            "id": item.get("id", f"{time.time()}"),
            "type": item.get("type", "unknown"),
            "summary": content[:200],
            "timestamp": time.time(),
            "workspace_profile": _normalize_workspace_profile(
                item.get("workspace_profile") or item.get("profile")
            ),
        }
        self._index.append(entry)
        self._save()

        chunk = TextChunk(
            id=entry["id"],
            text=entry.get("summary", ""),
            source=entry.get("type", "unknown"),
            meta=dict(entry),
        )
        self._vector_index.add([chunk])

    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace_profile: str = "general",
        allow_profile_fallback: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        profile = _normalize_workspace_profile(workspace_profile)
        policy = self.profile_policy(profile, top_k=top_k)
        effective_top_k = policy["top_k"]
        filter_fn = _profile_filter(profile, include_general=policy["include_general"])

        results = self._vector_index.search(query, top_k=effective_top_k, filter_fn=filter_fn)
        if results:
            return [chunk.meta for _, chunk in results if chunk.meta]

        if self._fallback_to_keyword:
            keyword_hits = self._keyword_search(
                query,
                effective_top_k,
                workspace_profile=profile,
                include_general=policy["include_general"],
            )
            if keyword_hits:
                return keyword_hits

        should_fallback = policy["allow_fallback"] if allow_profile_fallback is None else bool(allow_profile_fallback)
        if should_fallback and profile != "general":
            fallback_results = self._vector_index.search(query, top_k=effective_top_k)
            if fallback_results:
                return [chunk.meta for _, chunk in fallback_results if chunk.meta]
            if self._fallback_to_keyword:
                return self._keyword_search(query, effective_top_k)
        return []

    def profile_policy(self, workspace_profile: str = "general", top_k: int = 5) -> Dict[str, Any]:
        profile = _normalize_workspace_profile(workspace_profile)
        policy = dict(self._profile_policies.get(profile) or self._profile_policies["general"])
        policy["profile"] = profile
        policy["top_k"] = _positive_int(policy.get("top_k"), top_k)
        policy["include_general"] = bool(policy.get("include_general", profile != "general"))
        policy["allow_fallback"] = bool(policy.get("allow_fallback", profile != "general"))
        return policy

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
    ) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        profile = _normalize_workspace_profile(workspace_profile)
        hits = []
        for entry in self._index:
            if not _profile_matches_entry(entry, profile, include_general=include_general):
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

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            for entry in self._index:
                entry["workspace_profile"] = _normalize_workspace_profile(
                    entry.get("workspace_profile") or entry.get("profile")
                )
        except Exception:
            self._index = []


def _normalize_workspace_profile(value: Any) -> str:
    profile = str(value or "general").strip().lower()
    return profile if profile in _KNOWN_WORKSPACE_PROFILES else "general"


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


def _profile_filter(profile: str, include_general: bool = True):
    if profile == "general":
        return None

    def matches(chunk: TextChunk) -> bool:
        return _profile_matches_entry(
            chunk.meta or {},
            profile,
            include_general=include_general,
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
