"""
memory/agents_md_index.py — AGENTS.md 向量索引

负责发现项目规范文件、切分、向量化、持久化，并提供检索与动态工具列表。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from core.config import Config

from .agents_md_parser import parse_agents_md_files
from .vector_index import TextChunk, VectorIndex


class AgentsMdIndex:
    """AGENTS.md 向量索引与动态工具规范提取器。"""

    DEFAULT_FILES = ["AGENTS.md", ".codex/AGENTS.md", ".codex/instructions.md"]

    def __init__(
        self,
        project_root: Path,
        storage_root: Path,
        config: Optional[Config] = None,
        encoder: Optional[Callable[[List[str]], np.ndarray]] = None,
    ) -> None:
        self.config = config or Config()
        self.project_root = Path(project_root)
        self.storage_root = Path(storage_root)
        self.storage_dir = self.storage_root / "agents_md_index"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        cfg = self._agents_md_config()
        self._enabled = cfg.get("enabled", True)
        self._files = cfg.get("files", self.DEFAULT_FILES)
        self._chunk_size = cfg.get("chunk_size", 800)
        self._chunk_overlap = cfg.get("chunk_overlap", 100)
        self._top_k = cfg.get("top_k", 3)
        self._dynamic_tools_enabled = cfg.get("dynamic_tools_enabled", True)

        self._encoder = encoder
        self._vector_index = VectorIndex(
            namespace="agents_md",
            storage_dir=self.storage_dir,
            model_name=cfg.get("model", self._vector_index_model()),
            embedding_dim=cfg.get("embedding_dim"),
            enabled=self._enabled,
            encoder=encoder,
        )
        self._tool_specs: List[Dict[str, Any]] = []
        self._load_state()
        self._maybe_rebuild()

    def _agents_md_config(self) -> Dict[str, Any]:
        return self.config.get("agents_md", {}) if self.config else {}

    def _vector_index_model(self) -> str:
        vi_cfg = self.config.get("memory.vector_index", {}) if self.config else {}
        return vi_cfg.get("model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # ------------------------------------------------------------------
    # 状态 / rebuild
    # ------------------------------------------------------------------
    def _state_path(self) -> Path:
        return self.storage_dir / "state.json"

    def _load_state(self) -> None:
        path = self._state_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._tool_specs = data.get("tool_specs", [])
            except Exception:
                self._tool_specs = []

    def _save_state(self) -> None:
        state = {
            "tool_specs": self._tool_specs,
            "last_update": time.time(),
        }
        tmp = self._state_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._state_path())

    def _maybe_rebuild(self) -> None:
        if not self._enabled:
            return
        paths = self._resolve_paths()
        current_mtimes = {str(p): p.stat().st_mtime for p in paths if p.exists()}
        stored_mtimes = self._load_stored_mtimes()
        if current_mtimes == stored_mtimes and self._vector_index and len(self._vector_index) > 0:
            return
        self.rebuild()

    def _resolve_paths(self) -> List[Path]:
        return [self.project_root / f for f in self._files]

    def _load_stored_mtimes(self) -> Dict[str, float]:
        path = self.storage_dir / "mtimes.json"
        if not path.exists():
            return {}
        try:
            return {k: float(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
        except Exception:
            return {}

    def _save_mtimes(self, mtimes: Dict[str, float]) -> None:
        path = self.storage_dir / "mtimes.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(mtimes, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def rebuild(self) -> None:
        """重新解析 AGENTS.md 文件并重建向量索引。"""
        paths = self._resolve_paths()
        chunks, specs = parse_agents_md_files(
            paths,
            max_chunk_chars=self._chunk_size,
            overlap_chars=self._chunk_overlap,
        )

        # 清空并重建
        if self._vector_index:
            self._vector_index.clear()
            self._vector_index.add(chunks)

        self._tool_specs = specs if self._dynamic_tools_enabled else []
        self._save_state()

        mtimes = {str(p): p.stat().st_mtime for p in paths if p.exists()}
        self._save_mtimes(mtimes)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """检索与 query 语义相关的 AGENTS.md 片段。"""
        if not self._enabled or self._vector_index is None:
            return []
        k = top_k or self._top_k
        results = self._vector_index.search(query, top_k=k)
        return [
            {
                "id": chunk.id,
                "text": chunk.text,
                "source": chunk.source,
                "heading": chunk.heading,
                "offset": chunk.offset,
                "score": float(score),
            }
            for score, chunk in results
        ]

    def list_tools(self) -> List[Dict[str, Any]]:
        """返回 AGENTS.md 中声明的动态工具规范。"""
        return list(self._tool_specs)

    def is_available(self) -> bool:
        return self._enabled and self._vector_index is not None and self._vector_index.is_available

    def last_error(self) -> Optional[str]:
        if self._vector_index is None:
            return None
        return self._vector_index.last_error()
