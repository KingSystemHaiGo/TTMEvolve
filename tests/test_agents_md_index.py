"""
tests/test_agents_md_index.py — AgentsMdIndex 集成测试
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.agents_md_index import AgentsMdIndex


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


def test_rebuild_indexes_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        storage = root / "storage"
        agents_md = root / "AGENTS.md"
        agents_md.write_text("# Rules\n\nAlways commit before deploy.\n\n## Tool: deploy_game\n\n```json\n{\"description\": \"deploy\", \"parameters\": {\"type\": \"object\"}, \"risk_level\": \"high\", \"handler\": {\"type\": \"shell\", \"command\": \"git push\"}}\n```\n", encoding="utf-8")

        index = AgentsMdIndex(
            project_root=root,
            storage_root=storage,
            encoder=_mock_encoder,
        )
        index.rebuild()
        assert len(index._vector_index) >= 1

        results = index.search("commit deploy", top_k=3)
        assert len(results) >= 1

        tools = index.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "deploy_game"


def test_recall_injects_context():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        storage = root / "storage"
        (root / "AGENTS.md").write_text(
            "# 界面规范\n\n设置界面必须使用深色主题。\n",
            encoding="utf-8",
        )

        from core.config import Config
        from memory.manager import MemoryManager

        config = Config()
        # 手动覆盖配置，避免依赖真实 config.json
        config.data = {"llm": {"n_ctx": 4096, "reserve_tokens": 256}, "agents_md": {"enabled": True, "top_k": 2}}
        config._profiles = {}

        manager = MemoryManager(
            project_root=root,
            storage_root=storage,
            skills_dir=root / "skills",
            budget_manager=None,
            config=config,
        )
        # 注入 mock encoder
        manager.agents_md_index._vector_index._encoder = _mock_encoder
        manager.agents_md_index._vector_index._dim = 8
        manager.agents_md_index.rebuild()

        user_context, _stats = manager.prepare_think_payload(
            task="设计设置界面",
            context="",
            trajectory=[],
            tools_description="",
            max_tokens=1024,
        )
        assert "项目规范" in user_context
        assert "深色主题" in user_context


def test_disabled_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        storage = root / "storage"
        (root / "AGENTS.md").write_text("# Rules\n\nUse git.\n", encoding="utf-8")

        from core.config import Config
        config = Config()
        config.data = {"agents_md": {"enabled": False}}
        config._profiles = {}

        index = AgentsMdIndex(
            project_root=root,
            storage_root=storage,
            config=config,
            encoder=_mock_encoder,
        )
        assert index.search("git") == []
        assert index.list_tools() == []


if __name__ == "__main__":
    test_rebuild_indexes_files()
    print("OK test_rebuild_indexes_files")
    test_recall_injects_context()
    print("OK test_recall_injects_context")
    test_disabled_returns_empty()
    print("OK test_disabled_returns_empty")
    print("\nAll agents_md index tests passed.")
