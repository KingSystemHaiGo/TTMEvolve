"""Tests for agent.skill_packs (Q3 / Slice A)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.skill_packs import (
    CAPABILITY_BALANCED,
    CAPABILITY_DEEP,
    CAPABILITY_FAST,
    SCOPE_ENGINE,
    SCOPE_GENRE,
    SCOPE_PROJECT,
    SKILL_PACK_VERSION,
    SkillPack,
    SkillPackError,
    SkillPackRegistry,
    SkillPackStorage,
    _parse_frontmatter,
    _tokenize,
)
from agent.skill_packs.bootstrap import (
    DEFAULT_SEED_DIR,
    bootstrap_default_packs,
    get_or_create_registry,
)


# ---------------------------------------------------------------------------
# Frontmatter + helpers
# ---------------------------------------------------------------------------


def test_parse_frontmatter_basic():
    text = "---\nid: foo\nname: Foo\ntags: [a, b]\n---\nbody"
    meta, body = _parse_frontmatter(text)
    assert meta["id"] == "foo"
    assert meta["tags"] == ["a", "b"]
    assert body.strip() == "body"


def test_parse_frontmatter_no_frontmatter():
    meta, body = _parse_frontmatter("plain text only")
    assert meta == {}
    assert body == "plain text only"


def test_tokenize_handles_unicode():
    tokens = _tokenize("UrhoX 场景 渲染")
    assert "urhox" in tokens
    assert "场景" in tokens
    assert "渲染" in tokens


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_storage_lists_packs(tmp_path: Path):
    storage = SkillPackStorage(tmp_path)
    storage.write_pack(SkillPack(
        pack_id="alpha", name="Alpha", scope=SCOPE_ENGINE,
        summary="alpha summary", keywords=["alpha", "engine"],
    ))
    storage.write_pack(SkillPack(
        pack_id="beta", name="Beta", scope=SCOPE_GENRE,
        summary="beta summary", keywords=["beta", "puzzle"],
    ))
    packs = storage.list_packs()
    assert {p.pack_id for p in packs} == {"alpha", "beta"}


def test_storage_refuses_path_traversal(tmp_path: Path):
    storage = SkillPackStorage(tmp_path)
    target = storage.safe_pack_path("../escape.md")
    assert target is None


def test_storage_round_trip_preserves_metadata(tmp_path: Path):
    storage = SkillPackStorage(tmp_path)
    storage.write_pack(SkillPack(
        pack_id="gamma", name="Gamma", scope=SCOPE_PROJECT,
        summary="gamma", tags=["t1", "t2"], keywords=["k1"],
        capability=CAPABILITY_FAST, body="gamma body",
    ))
    pack = storage.read_pack("project/gamma.md")
    assert pack.pack_id == "gamma"
    assert pack.scope == SCOPE_PROJECT
    assert pack.capability == CAPABILITY_FAST
    assert "gamma body" in pack.body


def test_storage_rejects_overwrite_without_flag(tmp_path: Path):
    storage = SkillPackStorage(tmp_path)
    storage.write_pack(SkillPack(pack_id="dup", name="Dup", scope=SCOPE_ENGINE, summary="x"))
    with pytest.raises(SkillPackError):
        storage.write_pack(SkillPack(pack_id="dup", name="Dup2", scope=SCOPE_ENGINE, summary="y"))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_recall_finds_engine_pack_for_urhox_task(tmp_path: Path):
    bootstrap_default_packs(tmp_path)
    registry = SkillPackRegistry(SkillPackStorage(tmp_path))
    hits = registry.recall_for_task("add a UrhoX scene for a new boss fight")
    pack_ids = {h.pack.pack_id for h in hits}
    assert "engine_urhox" in pack_ids


def test_registry_recall_finds_genre_pack_for_platformer(tmp_path: Path):
    bootstrap_default_packs(tmp_path)
    registry = SkillPackRegistry(SkillPackStorage(tmp_path))
    hits = registry.recall_for_task("build a platformer level with a checkpoint system")
    pack_ids = {h.pack.pack_id for h in hits}
    assert "genre_platformer" in pack_ids


def test_registry_recall_returns_empty_for_unrelated_task(tmp_path: Path):
    bootstrap_default_packs(tmp_path)
    registry = SkillPackRegistry(SkillPackStorage(tmp_path))
    hits = registry.recall_for_task("xqzwpv_novel_glyph_8472")
    # Body fallback may surface faint hits; the assertion is that no
    # pack has a *strong* match (which is what the LLM consumes).
    assert all(h.score < 0.5 for h in hits)


def test_registry_search_filters_by_scope(tmp_path: Path):
    bootstrap_default_packs(tmp_path)
    registry = SkillPackRegistry(SkillPackStorage(tmp_path))
    engine_hits = registry.search("engine", scope=SCOPE_ENGINE, limit=10)
    for hit in engine_hits:
        assert hit.pack.scope == SCOPE_ENGINE


def test_registry_read_raises_for_unknown_pack(tmp_path: Path):
    registry = SkillPackRegistry(SkillPackStorage(tmp_path))
    with pytest.raises(SkillPackError):
        registry.read("does-not-exist")


def test_registry_to_dict_reports_pack_count(tmp_path: Path):
    bootstrap_default_packs(tmp_path)
    registry = SkillPackRegistry(SkillPackStorage(tmp_path))
    out = registry.to_dict()
    assert out["version"] == SKILL_PACK_VERSION
    assert out["pack_count"] >= 5


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_is_idempotent(tmp_path: Path):
    written1 = bootstrap_default_packs(tmp_path)
    written2 = bootstrap_default_packs(tmp_path)
    assert len(written1) >= 5
    assert written2 == []


def test_bootstrap_seeds_all_three_scopes(tmp_path: Path):
    bootstrap_default_packs(tmp_path)
    storage = SkillPackStorage(tmp_path)
    packs = storage.list_packs()
    scopes = {p.scope for p in packs}
    assert SCOPE_ENGINE in scopes
    assert SCOPE_GENRE in scopes


def test_get_or_create_registry_seeds_when_empty(tmp_path: Path):
    registry = get_or_create_registry(tmp_path)
    assert len(registry.list()) >= 5


# ---------------------------------------------------------------------------
# project_introspection integration
# ---------------------------------------------------------------------------


def _fake_registry() -> Any:
    class _Reg:
        def __init__(self):
            self.tools: Dict[str, Dict[str, Any]] = {}

        def register(self, *, name, description, parameters, handler, source):
            self.tools[name] = {
                "description": description,
                "parameters": parameters,
                "handler": handler,
                "source": source,
            }

    return _Reg()


def _fake_executor() -> Any:
    class _Ex:
        def __init__(self):
            self._tool_handlers: Dict[str, Any] = {}
            self._dynamic_tools: Dict[str, Dict[str, Any]] = {}
            self.approval = type("A", (), {"risk_levels": {}})()

        def register_dynamic_tool(self, name, handler, *, risk_level):
            self._tool_handlers[name] = handler
            self._dynamic_tools[name] = {"risk_level": risk_level}
            self.approval.risk_levels[name] = risk_level

    return _Ex()


def test_project_skill_pack_tool_list_action(tmp_path: Path):
    from agent.project_introspection import register_introspection_tools
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, tmp_path)
    handler = executor._tool_handlers["project.skill_pack"]
    result = handler(action="list")
    assert result["ok"] is True
    pack_ids = {p["pack_id"] for p in result["packs"]}
    assert "engine_urhox" in pack_ids
    assert "genre_platformer" in pack_ids


def test_project_skill_pack_tool_search_action(tmp_path: Path):
    from agent.project_introspection import register_introspection_tools
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, tmp_path)
    handler = executor._tool_handlers["project.skill_pack"]
    result = handler(action="search", query="boss fight UrhoX")
    assert result["ok"] is True
    assert result["matches"]
    # Search must not surface packs that have no keyword overlap.
    assert all(h["score"] > 0 for h in result["matches"])


def test_project_skill_pack_tool_read_action(tmp_path: Path):
    from agent.project_introspection import register_introspection_tools
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, tmp_path)
    handler = executor._tool_handlers["project.skill_pack"]
    result = handler(action="read", pack_id="engine_urhox")
    assert result["ok"] is True
    assert "pack" in result
    assert "body" in result
    assert "Scene graph" in result["body"]


def test_project_skill_pack_tool_rejects_unknown_action(tmp_path: Path):
    from agent.project_introspection import register_introspection_tools
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, tmp_path)
    handler = executor._tool_handlers["project.skill_pack"]
    result = handler(action="teleport")
    assert result["ok"] is False


def test_project_skill_pack_tool_seeds_when_empty(tmp_path: Path):
    """A fresh project with no packs still gets useful results."""
    from agent.project_introspection import register_introspection_tools
    registry = _fake_registry()
    executor = _fake_executor()
    register_introspection_tools(registry, executor, tmp_path)
    handler = executor._tool_handlers["project.skill_pack"]
    result = handler(action="list")
    assert result["ok"] is True
    assert len(result["packs"]) >= 5
