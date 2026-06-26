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
        allow_profile_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        profile = _normalize_workspace_profile(workspace_profile)
        filter_fn = _profile_filter(profile)

        results = self._vector_index.search(query, top_k=top_k, filter_fn=filter_fn)
        if results:
            return [chunk.meta for _, chunk in results if chunk.meta]

        if self._fallback_to_keyword:
            keyword_hits = self._keyword_search(query, top_k, workspace_profile=profile)
            if keyword_hits:
                return keyword_hits

        if allow_profile_fallback and profile != "general":
            fallback_results = self._vector_index.search(query, top_k=top_k)
            if fallback_results:
                return [chunk.meta for _, chunk in fallback_results if chunk.meta]
            if self._fallback_to_keyword:
                return self._keyword_search(query, top_k)
        return []

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
    ) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        profile = _normalize_workspace_profile(workspace_profile)
        hits = []
        for entry in self._index:
            if not _profile_matches_entry(entry, profile):
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


def _profile_matches_entry(entry: Dict[str, Any], profile: str) -> bool:
    if profile == "general":
        return True
    entry_profile = _normalize_workspace_profile(
        entry.get("workspace_profile") or entry.get("profile")
    )
    return entry_profile in {profile, "general"}


def _profile_filter(profile: str):
    if profile == "general":
        return None

    def matches(chunk: TextChunk) -> bool:
        return _profile_matches_entry(chunk.meta or {}, profile)

    return matches
