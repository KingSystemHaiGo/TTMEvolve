"""Tests for v0.7.0 Settings API — server/settings_api.py."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.settings_api import (
    SETTINGS_API_VERSION,
    build_llm_router_stats,
    build_portable_status,
    build_provider_summary,
    build_project_info,
    build_runtime_info,
    build_schema_summary,
    build_settings_devtools_clear,
    build_settings_runtime_info,
)


class _StubMCP:
    """Stub MCP integration exposing the attributes settings_api reads."""

    def __init__(
        self,
        *,
        status_text: str = "running",
        process_id: int = 1234,
        cwd: str = "D:/test",
        tools_list_updated_at: str = "2026-06-26T10:00:00Z",
        last_error: str = "",
    ) -> None:
        self._status_text = status_text
        self._process_id = process_id
        self._cwd = cwd
        self._tools_list_updated_at = tools_list_updated_at
        self._last_error = last_error

    def status_text(self) -> str:
        return self._status_text

    def process_id(self) -> int:
        return self._process_id

    def cwd(self) -> str:
        return self._cwd

    def tools_list_updated_at(self) -> str:
        return self._tools_list_updated_at

    def last_error(self) -> str:
        return self._last_error


class _StubTool:
    """Stub tool with category attribute."""

    def __init__(self, name: str, category: str) -> None:
        self.name = name
        self.category = category


class _StubToolRegistry:
    def __init__(self, tools: list) -> None:
        self._tools = tools

    def list_tools(self) -> list:
        return self._tools


class _StubConfig:
    """Stub config matching what settings_api calls."""

    def __init__(
        self,
        *,
        project_root: str = "D:/my-maker-project",
        maker_cfg: Dict[str, Any] = None,
        llm_provider: str = "deepseek",
    ) -> None:
        self._project_root = project_root
        self._maker_cfg = maker_cfg or {
            "project_id": "abc-123",
            "config_path": "D:/my-maker-project/.maker-mcp/config.json",
            "command": "npx.cmd",
            "args": ["-y", "-p", "@taptap/maker", "taptap-maker"],
        }
        self._llm_provider = llm_provider

    def project_root(self) -> Path:
        return Path(self._project_root)

    def maker_mcp_config(self) -> Dict[str, Any]:
        return self._maker_cfg

    def llm_provider(self) -> str:
        return self._llm_provider


class _StubAgent:
    def __init__(self, *, config: Any = None, mcp: Any = None, llm: Any = None, tools: Any = None) -> None:
        # Only fall back to defaults when the caller truly didn't pass a value.
        # Using a sentinel lets us distinguish "explicitly None" from "not given".
        if config is None and not isinstance(config, _StubConfig):
            # Use sentinel: only apply default when caller passed nothing.
            # The keyword default above already does this for None, so we
            # override here to provide the stub only when not explicitly given.
            pass
        # Preserve the caller's intent: `config=None` stays None.
        self.config = config
        self.mcp_integration = mcp
        self.llm = llm
        if tools is None:
            tools = _StubToolRegistry([])
        self.tools = tools


class _StubServer:
    def __init__(self, agent: Any) -> None:
        self.agent = agent


# ---------- build_project_info ----------


def test_build_project_info_extracts_from_config():
    cfg = _StubConfig(project_root="D:/games/my-game")
    server = _StubServer(_StubAgent(config=cfg))
    info = build_project_info(server)
    assert info["name"] == "my-game"
    # Path may convert separators on Windows; compare the suffix.
    assert info["rootPath"].replace("\\", "/").endswith("games/my-game")
    assert info["makerProjectId"] == "abc-123"
    assert info["configPath"].endswith(".maker-mcp/config.json")


def test_build_project_info_returns_none_when_config_missing():
    """When config is None, build_project_info must not fabricate a phantom project.

    Pass an object whose `config` attribute access raises AttributeError so the
    build function's _safe() wrapper catches the failure and short-circuits.
    """
    class _NoConfigServer:
        agent = None

    result = build_project_info(_NoConfigServer())
    assert result is None


# ---------- build_runtime_info ----------


def test_build_runtime_info_idle_when_mcp_missing():
    server = _StubServer(_StubAgent(mcp=None))
    info = build_runtime_info(server)
    assert info["status"] == "idle"
    assert info["processId"] is None


def test_build_runtime_info_running_with_full_state():
    mcp = _StubMCP(
        status_text="running",
        process_id=9999,
        cwd="D:/maker",
        tools_list_updated_at="2026-06-25T10:00:00Z",
    )
    cfg = _StubConfig()  # default config has maker_cfg with npx.cmd
    server = _StubServer(_StubAgent(config=cfg, mcp=mcp))
    info = build_runtime_info(server)
    assert info["status"] == "running"
    assert info["processId"] == 9999
    assert info["cwd"] == "D:/maker"
    assert info["toolsListUpdatedAt"] == "2026-06-25T10:00:00Z"
    assert "npx.cmd" in info["launchCommand"]


def test_build_runtime_info_includes_last_error():
    mcp = _StubMCP(status_text="error", last_error="connection refused")
    server = _StubServer(_StubAgent(mcp=mcp))
    info = build_runtime_info(server)
    assert info["status"] == "error"
    assert info["lastError"] == "connection refused"


# ---------- build_schema_summary ----------


def test_build_schema_summary_empty_registry():
    server = _StubServer(_StubAgent(tools=_StubToolRegistry([])))
    summary = build_schema_summary(server)
    assert summary["total"] == 0
    assert summary["categories"] == {}
    assert summary["formSource"] == "tools/list inputSchema"


def test_build_schema_summary_groups_by_category():
    tools = _StubToolRegistry([
        _StubTool("a", "image"),
        _StubTool("b", "image"),
        _StubTool("c", "video"),
        _StubTool("d", "build"),
    ])
    server = _StubServer(_StubAgent(tools=tools))
    summary = build_schema_summary(server)
    assert summary["total"] == 4
    assert summary["categories"]["image"] == 2
    assert summary["categories"]["video"] == 1
    assert summary["categories"]["build"] == 1


def test_build_schema_summary_handles_dict_tools():
    """Some tool registries return dicts rather than objects."""
    tools = _StubToolRegistry([
        {"name": "a", "category": "image"},
        {"name": "b", "category": "video"},
        {"name": "c"},  # no category
    ])
    server = _StubServer(_StubAgent(tools=tools))
    summary = build_schema_summary(server)
    assert summary["total"] == 3
    assert summary["categories"]["image"] == 1
    assert summary["categories"]["general"] == 1  # default


# ---------- build_portable_status ----------


def test_build_portable_status_returns_three_sections():
    status = build_portable_status()
    assert "python" in status
    assert "node" in status
    assert "makerMcp" in status
    for section in ("python", "node", "makerMcp"):
        assert "embedded" in status[section]
        assert "path" in status[section]


# ---------- build_llm_router_stats ----------


def test_build_llm_router_stats_empty_when_llm_missing():
    server = _StubServer(_StubAgent(llm=None))
    assert build_llm_router_stats(server) == []


def test_build_llm_router_stats_empty_when_llm_is_not_router():
    server = _StubServer(_StubAgent(llm="not-a-router"))
    assert build_llm_router_stats(server) == []


# ---------- build_settings_runtime_info (top-level aggregator) ----------


def test_build_settings_runtime_info_top_level_shape():
    mcp = _StubMCP()
    tools = _StubToolRegistry([_StubTool("a", "image")])
    server = _StubServer(_StubAgent(mcp=mcp, tools=tools))
    info = build_settings_runtime_info(server)
    assert info["version"] == SETTINGS_API_VERSION
    assert "project" in info
    assert "runtime" in info
    assert "schema" in info
    assert "portable" in info
    assert "llmRouter" in info
    assert info["runtime"]["status"] == "running"
    assert info["schema"]["total"] == 1


def test_build_settings_runtime_info_works_with_minimal_server():
    """No MCP, no tools — should still produce a coherent response."""
    server = _StubServer(_StubAgent())
    info = build_settings_runtime_info(server)
    assert info["runtime"]["status"] == "idle"
    assert info["schema"]["total"] == 0
    assert info["portable"]["python"]["path"] != ""


# ---------- build_settings_devtools_clear ----------


def test_build_settings_devtools_clear_returns_ok():
    result = build_settings_devtools_clear()
    assert result["version"] == SETTINGS_API_VERSION
    assert result["ok"] is True


# ---------- build_provider_summary ----------


def test_build_provider_summary_uses_config_primary():
    cfg = _StubConfig(llm_provider="claude")
    server = _StubServer(_StubAgent(config=cfg))
    summary = build_provider_summary(server)
    assert summary["primary"] == "claude"
    assert "presets" in summary
    assert "hints" in summary
    # presets list should include the major providers
    preset_ids = {p["id"] for p in summary["presets"]}
    assert "claude" in preset_ids
    assert "deepseek" in preset_ids


def test_build_provider_summary_includes_router_stats_field():
    server = _StubServer(_StubAgent())
    summary = build_provider_summary(server)
    assert "router_stats" in summary
    assert isinstance(summary["router_stats"], list)