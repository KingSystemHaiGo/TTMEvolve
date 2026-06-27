"""
memory/vector_index.py — 向量索引

轻量 FAISS + sentence-transformers 封装，支持持久化、update/delete、
失败时自动降级为关键词匹配。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class TextChunk:
    id: str
    text: str
    source: str
    heading: str = ""
    offset: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextChunk":
        return cls(
            id=data["id"],
            text=data["text"],
            source=data["source"],
            heading=data.get("heading", ""),
            offset=data.get("offset", 0),
            meta=data.get("meta", {}),
        )


class VectorIndex:
    """基于 FAISS + sentence-transformers 的命名空间向量索引。

    参数:
        namespace: 索引命名空间，决定磁盘子目录。
        storage_dir: 索引根目录。
        model_name: sentence-transformers 模型名或本地路径。
        embedding_dim: 显式指定维度；为 None 时从 encoder 推导。
        enabled: 是否启用向量索引；False 时只使用 keyword fallback。
        encoder: 可选自定义编码器（用于测试或注入轻量模型）。
               接受 `Callable[[List[str]], np.ndarray]`。
    """

    def __init__(
        self,
        namespace: str,
        storage_dir: Path,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dim: Optional[int] = None,
        enabled: bool = True,
        encoder: Optional[Callable[[List[str]], np.ndarray]] = None,
    ) -> None:
        self.namespace = namespace
        self.storage_dir = Path(storage_dir) / namespace
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self._requested_dim = embedding_dim
        self._enabled = enabled
        self._encoder = encoder
        self._model: Optional[Any] = None
        self._dim: Optional[int] = None
        self._index: Optional[Any] = None
        self._id_map: Dict[str, int] = {}
        self._reverse_id_map: Dict[int, str] = {}
        self._chunks: Dict[str, TextChunk] = {}
        self._faiss_available = False
        self._st_available = False
        self._last_error: Optional[str] = None

        self._load_libraries()
        self.load()

    # ------------------------------------------------------------------
    # 初始化 / 加载
    # ------------------------------------------------------------------
    def _load_libraries(self) -> None:
        """尝试加载 FAISS 和 sentence-transformers；任意失败即降级。"""
        if not self._enabled:
            return
        try:
            import faiss  # noqa: F401
            self._faiss_available = True
        except Exception as e:
            self._last_error = f"faiss import failed: {e}"
            return

        if self._encoder is not None:
            self._st_available = True
            return

        try:
            from sentence_transformers import SentenceTransformer
            model_path = self._resolve_embedding_model_path()
            local_files_only = False
            if model_path is not None and Path(model_path).exists():
                self.model_name = str(model_path)
                local_files_only = True
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=os.getenv("SENTENCE_TRANSFORMERS_HOME"),
                local_files_only=local_files_only,
            )
            self._st_available = True
        except Exception as e:
            self._last_error = f"sentence-transformers import/load failed: {e}"

    def _resolve_embedding_model_path(self) -> Optional[str]:
        """优先使用 vendor/embeddings 中的离线模型。"""
        vendor_dir = Path(__file__).resolve().parent.parent / "vendor" / "embeddings"
        if not vendor_dir.exists():
            return None
        # model_name may be a repo id like sentence-transformers/...
        local_candidate = vendor_dir / Path(self.model_name).name
        if local_candidate.exists():
            return str(local_candidate)
        return None

    @property
    def is_available(self) -> bool:
        return self._enabled and self._faiss_available and self._st_available and self._index is not None

    @property
    def can_build_vector_index(self) -> bool:
        return self._enabled and self._faiss_available and self._st_available

    # ------------------------------------------------------------------
    # 编码
    # ------------------------------------------------------------------
    def _encode(self, texts: List[str]) -> np.ndarray:
        if self._encoder is not None:
            return self._encoder(texts)
        if self._model is None:
            raise RuntimeError("No encoder available")
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)

    # ------------------------------------------------------------------
    # 索引构建
    # ------------------------------------------------------------------
    def _create_index(self, dim: int) -> None:
        import faiss
        base = faiss.IndexFlatIP(dim)
        self._index = faiss.IndexIDMap2(base)
        self._dim = dim

    def _ensure_index(self, dim: int) -> None:
        if self._index is not None and self._dim == dim:
            return
        self._create_index(dim)

    def _get_dim(self) -> int:
        if self._requested_dim is not None:
            return self._requested_dim
        if self._dim is not None:
            return self._dim
        # 用一个空字符串推导维度
        sample = self._encode(["dimension probe"])
        return int(sample.shape[1])

    # ------------------------------------------------------------------
    # 增删改查
    # ------------------------------------------------------------------
    def add(self, chunks: List[TextChunk]) -> None:
        if not chunks:
            return
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
        if not self.can_build_vector_index:
            return

        dim = self._get_dim()
        self._ensure_index(dim)

        new_chunks = [c for c in chunks if c.id not in self._id_map]
        if not new_chunks:
            return

        texts = [c.text for c in new_chunks]
        vectors = self._encode(texts)
        ids = np.array(self._allocate_ids(len(new_chunks)), dtype=np.int64)
        self._index.add_with_ids(vectors, ids)  # type: ignore[union-attr]
        for chunk, idx in zip(new_chunks, ids):
            self._id_map[chunk.id] = int(idx)
            self._reverse_id_map[int(idx)] = chunk.id
        self.save()

    def update(self, chunk: TextChunk) -> None:
        """先删除再添加，实现更新。"""
        self.delete(chunk.id)
        self.add([chunk])

    def delete(self, chunk_id: str) -> None:
        if chunk_id not in self._chunks:
            return
        del self._chunks[chunk_id]
        internal_id = self._id_map.pop(chunk_id, None)
        if internal_id is not None:
            self._reverse_id_map.pop(internal_id, None)
        if internal_id is None or self._index is None:
            self.save()
            return
        try:
            import faiss
            sel = faiss.IDSelectorBatch(1, np.array([internal_id], dtype=np.int64))
            self._index.remove_ids(sel)  # type: ignore[union-attr]
        except Exception:
            # 删除失败则重建索引
            self._rebuild_index()
        self.save()

    def clear(self) -> None:
        self._id_map.clear()
        self._reverse_id_map.clear()
        self._chunks.clear()
        self._index = None
        self._dim = None
        self.save()

    def _rebuild_index(self) -> None:
        if not self._faiss_available:
            self._index = None
            return
        if not self._chunks:
            self._index = None
            return
        dim = self._get_dim()
        self._create_index(dim)
        texts = [c.text for c in self._chunks.values()]
        vectors = self._encode(texts)
        ids = np.arange(len(texts), dtype=np.int64)
        self._index.add_with_ids(vectors, ids)  # type: ignore[union-attr]
        self._id_map = {cid: int(i) for cid, i in zip(self._chunks.keys(), ids)}
        self._reverse_id_map = {internal: cid for cid, internal in self._id_map.items()}

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_fn: Optional[Callable[[TextChunk], bool]] = None,
    ) -> List[Tuple[float, TextChunk]]:
        """返回 (score, chunk) 列表，按相似度降序。"""
        if not query.strip():
            return []

        candidates: List[Tuple[float, TextChunk]] = []
        candidate_ids: set[str] = set()

        if self.is_available and self._index is not None and self._index.ntotal > 0:
            try:
                qvec = self._encode([query])
                distances, indices = self._index.search(qvec, top_k * 4)  # type: ignore[union-attr]
                for dist, idx in zip(distances[0], indices[0]):
                    if idx < 0:
                        continue
                    cid = self._reverse_id_map.get(int(idx))
                    if not cid:
                        continue
                    chunk = self._chunks.get(cid)
                    if chunk and cid not in candidate_ids:
                        candidates.append((float(dist), chunk))
                        candidate_ids.add(cid)
                vector_results = self._dedupe_filter_candidates(candidates, top_k, filter_fn)
                if len(vector_results) >= top_k:
                    return vector_results
            except Exception:
                pass

        # 去重 + 过滤 + 排序
        for score, chunk in self._keyword_search(query, top_k * 4):
            if chunk.id in candidate_ids:
                continue
            candidates.append((score, chunk))
            candidate_ids.add(chunk.id)

        return self._dedupe_filter_candidates(candidates, top_k, filter_fn)

    @staticmethod
    def _dedupe_filter_candidates(
        candidates: List[Tuple[float, TextChunk]],
        top_k: int,
        filter_fn: Optional[Callable[[TextChunk], bool]] = None,
    ) -> List[Tuple[float, TextChunk]]:
        seen: set[str] = set()
        results: List[Tuple[float, TextChunk]] = []
        for score, chunk in sorted(candidates, key=lambda x: x[0], reverse=True):
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            if filter_fn is not None and not filter_fn(chunk):
                continue
            results.append((score, chunk))
            if len(results) >= top_k:
                break
        return results

    def _keyword_search(self, query: str, top_k: int) -> List[Tuple[float, TextChunk]]:
        """兜底关键词搜索，支持中英文混合。对英文按词匹配，中文按字匹配。"""
        # 提取 query 中的有效 token：英文单词 + 单个中文字符
        english_tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]{2,}", query)]
        chinese_chars = [c for c in query if "一" <= c <= "鿿"]
        tokens = list(set(english_tokens + chinese_chars))
        if not tokens:
            return []

        scored: List[Tuple[float, TextChunk]] = []
        for chunk in self._chunks.values():
            text = f"{chunk.text} {chunk.heading}".lower()
            score = sum(1 for t in tokens if t in text)
            if score > 0:
                scored.append((float(score), chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def _next_id(self) -> int:
        candidate = int(time.time() * 1_000_000) % (2 ** 63)
        while candidate in self._reverse_id_map:
            candidate = (candidate + 1) % (2 ** 63)
        return candidate

    def _allocate_ids(self, count: int) -> List[int]:
        allocated: List[int] = []
        seen = set(self._reverse_id_map)
        candidate = self._next_id()
        while len(allocated) < count:
            if candidate not in seen:
                allocated.append(candidate)
                seen.add(candidate)
            candidate = (candidate + 1) % (2 ** 63)
        return allocated

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def save(self) -> None:
        index_tmp = self.storage_dir / "index.faiss.tmp"
        index_path = self.storage_dir / "index.faiss"
        try:
            if self._index is not None and self._faiss_available:
                import faiss
                faiss.write_index(self._index, str(index_tmp))  # type: ignore[union-attr]
                shutil.move(str(index_tmp), str(index_path))
        except Exception as e:
            self._last_error = f"save index failed: {e}"

        chunks_data = {cid: c.to_dict() for cid, c in self._chunks.items()}
        self._atomic_write_json(self.storage_dir / "chunks.json", chunks_data)
        self._atomic_write_json(self.storage_dir / "id_map.json", self._id_map)

    def load(self) -> None:
        index_path = self.storage_dir / "index.faiss"
        chunks_path = self.storage_dir / "chunks.json"
        id_map_path = self.storage_dir / "id_map.json"

        if chunks_path.exists():
            try:
                data = json.loads(chunks_path.read_text(encoding="utf-8"))
                self._chunks = {cid: TextChunk.from_dict(c) for cid, c in data.items()}
            except Exception:
                self._chunks = {}

        if id_map_path.exists():
            try:
                self._id_map = {k: int(v) for k, v in json.loads(id_map_path.read_text(encoding="utf-8")).items()}
            except Exception:
                self._id_map = {}
        self._reverse_id_map = {internal: cid for cid, internal in self._id_map.items()}

        if self._faiss_available and index_path.exists():
            try:
                import faiss
                self._index = faiss.read_index(str(index_path))
                self._dim = self._index.d
                # 校验一致性
                if self._index.ntotal != len(self._chunks) or self._index.ntotal != len(self._id_map):
                    self._rebuild_index()
            except Exception as e:
                self._last_error = f"load index failed: {e}"
                self._rebuild_index()
        elif self._chunks:
            self._rebuild_index()

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.move(str(tmp), str(path))

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._chunks)

    def __bool__(self) -> bool:
        return True

    def list_chunks(self) -> List[TextChunk]:
        return list(self._chunks.values())

    def last_error(self) -> Optional[str]:
        return self._last_error
