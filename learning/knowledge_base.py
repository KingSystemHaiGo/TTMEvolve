"""
learning/knowledge_base.py — 知识库

存储从反思中提炼出的规则 / 模式 / 失败模式。
使用 JSON 文件作为源文件，向量索引作为检索后端，失败时降级为关键词匹配。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json
import time
import uuid

from memory.vector_index import TextChunk, VectorIndex


class KnowledgeBase:
    """轻量知识库。"""

    def __init__(
        self,
        storage_path: Path,
        vector_index_config: Optional[Dict[str, Any]] = None,
        encoder: Optional[Any] = None,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.storage_path / "index.json"
        self._entries: List[Dict[str, Any]] = []

        vi_cfg = vector_index_config or {}
        self._fallback_to_keyword = vi_cfg.get("fallback_to_keyword", True)
        self._vector_index = VectorIndex(
            namespace="knowledge_base",
            storage_dir=self.storage_path,
            model_name=vi_cfg.get("model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            embedding_dim=vi_cfg.get("embedding_dim"),
            enabled=vi_cfg.get("enabled", True),
            encoder=encoder,
        )

        self._load()
        if len(self._vector_index) == 0 and self._entries:
            self.rebuild()

    def store(self, item: Dict[str, Any]) -> str:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "created_at": time.time(),
            "domain": item.get("domain", "general"),
            "rule": item.get("rule", ""),
            "context": item.get("context", ""),
            "confidence": item.get("confidence", 0.5),
            "source_session": item.get("source_session", ""),
            "tags": item.get("tags", []),
        }
        self._entries.append(entry)
        self._save()

        chunk = TextChunk(
            id=entry["id"],
            source=entry.get("domain", "general"),
            text=f"{entry.get('rule', '')} {entry.get('context', '')} {' '.join(entry.get('tags', []))}".strip(),
            meta=dict(entry),
        )
        self._vector_index.add([chunk])
        return entry["id"]

    def search(
        self,
        query: str,
        top_k: int = 5,
        source_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filter_fn: Optional[Callable[[TextChunk], bool]] = None
        if source_filter:
            filter_fn = lambda chunk: source_filter in chunk.meta.get("tags", []) or str(chunk.meta.get("source_session", "")).startswith(source_filter)  # noqa: E501

        results = self._vector_index.search(query, top_k=top_k, filter_fn=filter_fn)
        if results:
            return [chunk.meta for _, chunk in results if chunk.meta]

        if self._fallback_to_keyword:
            return self._keyword_search(query, top_k, source_filter)
        return []

    def rebuild(self) -> None:
        """从 JSON 源文件重建向量索引。"""
        self._vector_index.clear()
        chunks = [
            TextChunk(
                id=entry["id"],
                source=entry.get("domain", "general"),
                text=f"{entry.get('rule', '')} {entry.get('context', '')} {' '.join(entry.get('tags', []))}".strip(),
                meta=dict(entry),
            )
            for entry in self._entries
        ]
        self._vector_index.add(chunks)

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._entries)

    def _keyword_search(
        self,
        query: str,
        top_k: int,
        source_filter: Optional[str],
    ) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        scored = []
        for e in self._entries:
            if source_filter:
                tags = e.get("tags", [])
                source_session = e.get("source_session", "")
                if source_filter not in tags and not source_session.startswith(source_filter):
                    continue
            score = 0
            text = f"{e.get('rule', '')} {e.get('context', '')} {' '.join(e.get('tags', []))}"
            if query_lower in text.lower():
                score += 1
            for tag in e.get("tags", []):
                if tag.lower() in query_lower:
                    score += 1
            # 专家救援来源加权
            if "expert_rescue" in e.get("tags", []):
                score += 0.5
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    def _save(self) -> None:
        self._index_path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            self._entries = json.loads(self._index_path.read_text(encoding="utf-8"))
        except Exception:
            self._entries = []
