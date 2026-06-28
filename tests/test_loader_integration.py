"""
tests/test_loader_integration.py - end-to-end MemoryManager + loader path.

Phase C exit gate. The shim in ``MemoryManager.prepare_think_payload`` must
delegate to the loader when ``loader.enabled=true`` and stay on the legacy
path when ``loader.enabled=false``. The returned shape must be the same in
both cases (``(text, BudgetStats)``).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.manager import MemoryManager  # noqa: E402


def _mock_encoder(texts):
    dim = 8
    vectors = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        for ch in text.lower():
            vec[ord(ch) % dim] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        vectors.append(vec)
    return np.array(vectors, dtype=np.float32)


def _write_config(tmp: Path, *, loader_enabled: bool) -> Path:
    cfg = {
        "llm": {"n_ctx": 4096, "reserve_tokens": 64, "hot_memory_max_turns": 4},
        "memory": {"vector_index": {"enabled": True, "embedding_dim": 8, "model": "stub"}},
        "agents_md": {"enabled": False, "files": []},
        "loader": {"enabled": loader_enabled},
    }
    path = tmp / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_prepare_think_payload_loader_disabled_keeps_legacy_shape():
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = _write_config(Path(tmp), loader_enabled=False)
        from core.config import Config
        cfg = Config(cfg_path)
        cfg.data["storage_root"] = str(Path(tmp) / "storage")
        project_root = Path(tmp) / "project"
        skills_dir = project_root / "skills"
        project_root.mkdir(parents=True, exist_ok=True)
        skills_dir.mkdir(parents=True, exist_ok=True)
        storage_root = Path(tmp) / "storage"
        mgr = MemoryManager(
            project_root=project_root,
            storage_root=storage_root,
            skills_dir=skills_dir,
            config=cfg,
        )
        text, stats = mgr.prepare_think_payload(
            task="do the thing",
            context="",
            trajectory=[],
            tools_description="read_file",
            max_tokens=256,
            workspace_profile="general",
        )
        assert isinstance(text, str)
        # Legacy fragment fields stay at 0 when loader is off
        d = stats.to_dict()
        assert d["fragment_count"] == 0
        assert d["deferred_count"] == 0
        assert d["stubbed_count"] == 0


def test_prepare_think_payload_loader_enabled_records_fragment_stats():
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = _write_config(Path(tmp), loader_enabled=True)
        from core.config import Config
        cfg = Config(cfg_path)
        cfg.data["storage_root"] = str(Path(tmp) / "storage")
        project_root = Path(tmp) / "project"
        skills_dir = project_root / "skills"
        project_root.mkdir(parents=True, exist_ok=True)
        skills_dir.mkdir(parents=True, exist_ok=True)
        storage_root = Path(tmp) / "storage"
        mgr = MemoryManager(
            project_root=project_root,
            storage_root=storage_root,
            skills_dir=skills_dir,
            config=cfg,
        )
        text, stats = mgr.prepare_think_payload(
            task="do the thing",
            context="",
            trajectory=[],
            tools_description="read_file",
            max_tokens=128,
            workspace_profile="general",
        )
        assert "do the thing" in text
        d = stats.to_dict()
        # When loader is on, fragment_count must reflect what was built
        assert d["fragment_count"] >= 2  # at least task + tools
        assert isinstance(d["deferred_ids"], list)
