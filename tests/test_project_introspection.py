"""Tests for agent.project_introspection (Q2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.project_introspection import (
    AssetRecord,
    ProjectIntrospector,
    ProjectManifest,
    register_introspection_tools,
    INTROSPECTION_TOOL_SPECS,
)


@pytest.fixture
def urhox_project(tmp_path: Path) -> Path:
    """A small but representative UrhoX / Maker project tree."""
    root = tmp_path
    (root / "scripts").mkdir()
    (root / "scripts" / "player.lua").write_text(
        "function Player:jump()\n  self.velocity = 12\nend\n",
        encoding="utf-8",
    )
    (root / "scripts" / "enemy.lua").write_text(
        "function Enemy:attack(target)\n  target:damage(1)\nend\n",
        encoding="utf-8",
    )
    (root / "scenes").mkdir()
    (root / "scenes" / "level1.scene").write_text(
        "<scene><node name='player'/></scene>",
        encoding="utf-8",
    )
    (root / "assets").mkdir()
    (root / "assets" / "sprites").mkdir()
    (root / "assets" / "sprites" / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "assets" / "sprites" / "boss.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "assets" / "audio").mkdir()
    (root / "assets" / "audio" / "bgm.ogg").write_bytes(b"OggS")
    (root / "config.json").write_text("{}", encoding="utf-8")
    # Drop one we should skip.
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("ignored", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


def test_manifest_counts_categories_for_urhox_project(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_manifest()
    assert result["ok"] is True
    m = result["manifest"]
    assert m["engine"] in {"urhox", "urhox-like"}
    assert m["engine_confidence"] > 0
    assert m["script_count"] == 2
    assert m["scene_count"] == 1
    counts = m["asset_counts"]
    assert counts.get("sprite") == 2
    assert counts.get("audio") == 1
    assert counts.get("config") == 1
    assert counts.get("script") == 2
    assert counts.get("scene") == 1
    # .git / node_modules must not leak.
    assert "git" not in counts


def test_manifest_handles_missing_project_root(tmp_path: Path):
    intro = ProjectIntrospector(tmp_path / "does-not-exist")
    result = intro.project_manifest()
    assert result["ok"] is True
    assert "does not exist" in result["manifest"]["warnings"][0]


def test_manifest_includes_top_level_layout(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_manifest()
    names = [item["name"] for item in result["manifest"]["top_level"]]
    assert "scripts" in names
    assert "assets" in names
    # Skipped directories should not appear.
    assert ".git" not in names
    assert "node_modules" not in names


# ---------------------------------------------------------------------------
# asset_read
# ---------------------------------------------------------------------------


def test_asset_read_returns_metadata_and_multimodal_content(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    # Drop a thumbnail next to the sprite so multimodal content has an image.
    (urhox_project / "assets" / "sprites" / "hero.thumb.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    result = intro.project_asset_read("assets/sprites/hero.png")
    assert result["ok"] is True
    assert result["asset"]["category"] == "sprite"
    assert result["asset"]["thumbnail_rel_path"] == "assets/sprites/hero.thumb.png"
    image_blocks = [c for c in result["content"] if c.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["caption"]


def test_asset_read_rejects_path_traversal(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_asset_read("../etc/passwd")
    assert result["ok"] is False
    assert result["error_type"] in {"invalid_path", "not_found"}


def test_asset_read_rejects_unknown_extension(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    weird = urhox_project / "weird.bin"
    weird.write_bytes(b"\x00\x01")
    result = intro.project_asset_read("weird.bin")
    assert result["ok"] is False
    assert result["error_type"] == "unsupported_type"


def test_asset_read_requires_name(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_asset_read("")
    assert result["ok"] is False
    assert result["error_type"] == "missing_param"


# ---------------------------------------------------------------------------
# asset_search
# ---------------------------------------------------------------------------


def test_asset_search_filters_by_category(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_asset_search(category="sprite")
    assert result["ok"] is True
    names = {a["name"] for a in result["assets"]}
    assert names == {"hero.png", "boss.png"}


def test_asset_search_matches_name_substring(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_asset_search(query="boss")
    assert result["ok"] is True
    assert any(a["name"] == "boss.png" for a in result["assets"])
    assert all("boss" in a["name"].lower() for a in result["assets"])


def test_asset_search_respects_limit(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_asset_search(limit=1)
    assert result["ok"] is True
    assert len(result["assets"]) == 1


# ---------------------------------------------------------------------------
# code_search
# ---------------------------------------------------------------------------


def test_code_search_finds_lua_symbol(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_code_search("Player:jump")
    assert result["ok"] is True
    assert result["scanned_files"] >= 2
    assert any(m["file"].endswith("player.lua") for m in result["matches"])


def test_code_search_skips_excluded_directories(urhox_project: Path):
    (urhox_project / "scripts" / "secret.lua").write_text(
        "local function jump() end",
        encoding="utf-8",
    )
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_code_search("jump")
    assert result["ok"] is True
    files = {m["file"] for m in result["matches"]}
    assert all("node_modules" not in f for f in files)
    assert all(".git" not in f for f in files)


def test_code_search_requires_symbol(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_code_search("")
    assert result["ok"] is False
    assert result["error_type"] == "missing_param"


# ---------------------------------------------------------------------------
# preview_capture
# ---------------------------------------------------------------------------


def test_preview_capture_writes_placeholder_when_missing(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_preview_capture(scene_id="level1")
    assert result["ok"] is True
    image_blocks = [c for c in result["content"] if c.get("type") == "image"]
    assert len(image_blocks) == 1
    preview_path = urhox_project / result["preview_path"]
    assert preview_path.is_file()
    assert preview_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_capture_uses_existing_png(urhox_project: Path):
    (urhox_project / ".previews").mkdir()
    existing = urhox_project / ".previews" / "boss.png"
    existing.write_bytes(b"\x89PNG\r\n\x1a\nrest")
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_preview_capture(scene_id="boss")
    assert result["ok"] is True
    # We did not overwrite the existing file.
    assert existing.read_bytes() == b"\x89PNG\r\n\x1a\nrest"


def test_preview_capture_rejects_path_traversal(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_preview_capture(save_path="../escape.png")
    assert result["ok"] is False
    assert result["error_type"] == "invalid_path"


# ---------------------------------------------------------------------------
# build_state
# ---------------------------------------------------------------------------


def test_build_state_returns_no_file_when_missing(urhox_project: Path):
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_build_state()
    assert result["ok"] is True
    assert result["build_state"]["available"] is False


def test_build_state_reads_recorded_file(urhox_project: Path):
    state_path = urhox_project / ".ttmevolve" / "build_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"status": "passed", "returncode": 0, "errors": []}),
        encoding="utf-8",
    )
    intro = ProjectIntrospector(urhox_project)
    result = intro.project_build_state()
    assert result["ok"] is True
    assert result["build_state"]["status"] == "passed"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _fake_registry() -> Any:
    class _Reg:
        def __init__(self) -> None:
            self.tools: Dict[str, Dict[str, Any]] = {}

        def register(self, *, name: str, description: str, parameters: Dict[str, Any],
                     handler: Any, source: str) -> None:
            self.tools[name] = {
                "description": description,
                "parameters": parameters,
                "handler": handler,
                "source": source,
            }

    return _Reg()


def _fake_executor() -> Any:
    class _Ex:
        def __init__(self) -> None:
            self._tool_handlers: Dict[str, Any] = {}
            self._dynamic_tools: Dict[str, Dict[str, Any]] = {}
            self.approval = type("A", (), {"risk_levels": {}})()

        def register_dynamic_tool(self, name: str, handler: Any, *, risk_level: str) -> None:
            self._tool_handlers[name] = handler
            self._dynamic_tools[name] = {"risk_level": risk_level}
            self.approval.risk_levels[name] = risk_level

    return _Ex()


def test_register_introspection_tools_registers_all_six(urhox_project: Path):
    registry = _fake_registry()
    executor = _fake_executor()
    intro = register_introspection_tools(registry, executor, urhox_project)
    assert isinstance(intro, ProjectIntrospector)
    # One tool per spec — currently seven (six project.* plus
    # project.skill_pack).
    assert len(registry.tools) == len(INTROSPECTION_TOOL_SPECS)
    for spec in INTROSPECTION_TOOL_SPECS:
        assert spec["name"] in registry.tools
        assert spec["name"] in executor._tool_handlers
        assert spec["name"] in executor._dynamic_tools
        assert executor._dynamic_tools[spec["name"]]["risk_level"] == "low"


def test_registered_handler_dispatches_to_introspector(urhox_project: Path):
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, urhox_project)
    handler = executor._tool_handlers["project.asset_search"]
    result = handler(query="boss", category="sprite", limit=5)
    assert result["ok"] is True
    assert any(a["name"] == "boss.png" for a in result["assets"])


def test_introspection_tools_have_proper_schemas(urhox_project: Path):
    """Every tool must declare a valid parameters schema with required
    fields where the LLM would otherwise forget them."""
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, urhox_project)
    for spec in INTROSPECTION_TOOL_SPECS:
        tool = registry.tools[spec["name"]]
        schema = tool["parameters"]
        assert schema.get("type") == "object", spec["name"]
        if spec["method"] in {"project_asset_read", "project_code_search"}:
            assert "required" in schema, spec["name"]
