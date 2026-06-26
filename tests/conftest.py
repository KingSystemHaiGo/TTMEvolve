"""
tests/conftest.py — 共享测试 fixtures

为 pytest 提供 cfg / mock_agent / tmp_project 等共享装置，减少测试重复 setup。
"""

from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from agent.agent import TapMakerAgent
from core.config import Config
from llm.mock_llm import MockLLM


@pytest.fixture(autouse=True)
def stable_temp_dir() -> None:
    """Keep process-global tempfile state valid after portable-env tests."""
    temp_root = Path(__file__).resolve().parent.parent / "portable" / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp_root)
    for key in ("TMP", "TEMP", "TMPDIR"):
        os.environ[key] = str(temp_root)
    try:
        yield
    finally:
        # Some tests call apply_portable_env() with a TemporaryDirectory root.
        # If that root is deleted, the process-wide tempfile cache must not
        # keep pointing at the dead path for later tests or background servers.
        temp_root.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(temp_root)
        for key in ("TMP", "TEMP", "TMPDIR"):
            os.environ[key] = str(temp_root)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    """返回一个指向临时项目的默认 Config。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path / "project"),
                "storage_root": str(tmp_path / "storage"),
                "llm": {"provider": "mock"},
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "never"},
                "expert": {"enabled": False},
                "rescue": {
                    "max_consecutive_errors": 3,
                    "max_iterations_ratio": 0.75,
                    "detect_repeated_actions": False,
                    "health_degraded": False,
                    "max_rescue_per_session": 1,
                    "cooldown_seconds": 0,
                    "distill_after_rescue": False,
                },
                "learning": {"skill_generation_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    return Config(str(config_path))


@pytest.fixture
def tmp_project(cfg: Config) -> Path:
    """创建临时项目目录并返回其路径。"""
    project_root = Path(cfg.project_root())
    storage_root = Path(cfg.storage_root())
    skills_dir = project_root / "skills"
    project_root.mkdir(parents=True, exist_ok=True)
    storage_root.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    return project_root


@pytest.fixture
def mock_agent(cfg: Config, tmp_project: Path) -> TapMakerAgent:
    """返回一个使用 MockLLM 的临时 Agent 实例。"""
    storage_root = Path(cfg.storage_root())
    return TapMakerAgent(
        llm=MockLLM(),
        config=cfg,
        project_root=tmp_project,
        storage_root=storage_root,
    )


@pytest.fixture
def mock_config_dict() -> Dict[str, Any]:
    """返回一份最小 mock 配置字典。"""
    return {
        "project_root": ".",
        "storage_root": "./storage",
        "llm": {"provider": "mock"},
        "sandbox": {"mode": "workspace-write"},
        "approval": {"policy": "never"},
        "expert": {"enabled": False},
        "rescue": {
            "max_consecutive_errors": 3,
            "max_iterations_ratio": 0.75,
            "detect_repeated_actions": False,
            "health_degraded": False,
            "max_rescue_per_session": 1,
            "cooldown_seconds": 0,
            "distill_after_rescue": False,
        },
        "learning": {"skill_generation_enabled": False},
    }
