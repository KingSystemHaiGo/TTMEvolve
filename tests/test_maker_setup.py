from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from server.maker_setup import (
    REQUIRED_PROXY_TOOLS,
    agent_root_mcp_state,
    build_maker_setup_status,
    build_maker_tool_audit,
    ensure_agent_root_maker_mcp_registration,
    ensure_internal_maker_mcp_latest_config,
    prepare_auth_flow,
    render_maker_setup_markdown,
)


class _FakeMcpIntegration:
    def status(self):
        return {
            "connected": True,
            "tools": [
                {"name": name, "description": name, "parameters": {}}
                for name in REQUIRED_PROXY_TOOLS
            ],
            "last_error": "",
        }


class _FakeTools:
    def list_tools(self):
        return [
            {"name": name, "source": "maker_mcp", "parameters": {}}
            for name in REQUIRED_PROXY_TOOLS
        ]


class _FakeExecutor:
    MAKER_PROXY_TOOLS = set(REQUIRED_PROXY_TOOLS)

    def __init__(self):
        self._tool_handlers = {name: object() for name in REQUIRED_PROXY_TOOLS}


class _FakeAgent:
    mcp_integration = _FakeMcpIntegration()
    tools = _FakeTools()
    executor = _FakeExecutor()


class _PartialMcpIntegration:
    def status(self):
        return {
            "connected": True,
            "tools": [
                {"name": "maker_build_current_directory", "description": "build", "parameters": {}},
                {"name": "maker_status_lite", "description": "status", "parameters": {}},
            ],
            "last_error": "",
        }


class _PartialTools:
    def list_tools(self):
        return [
            {"name": "maker_build_current_directory", "source": "maker_mcp", "parameters": {}},
            {"name": "maker_status_lite", "source": "maker_mcp", "parameters": {}},
        ] + [
            {"name": name, "source": "maker_mcp_unavailable", "parameters": {}}
            for name in REQUIRED_PROXY_TOOLS
        ]


class _PartialExecutor:
    MAKER_PROXY_TOOLS = set(REQUIRED_PROXY_TOOLS)

    def __init__(self):
        self._tool_handlers = {
            "maker_build_current_directory": object(),
            "maker_status_lite": object(),
            **{name: object() for name in REQUIRED_PROXY_TOOLS},
        }


class _PartialAgent:
    mcp_integration = _PartialMcpIntegration()
    tools = _PartialTools()
    executor = _PartialExecutor()


def _config(tmp_path: Path) -> Config:
    project = tmp_path / "maker-game"
    (project / ".maker-mcp").mkdir(parents=True)
    (project / ".project").mkdir(parents=True)
    (project / ".maker-mcp" / "config.json").write_text(
        json.dumps({"project_id": "p1"}),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "storage_root": str(tmp_path / "storage"),
                "llm": {"provider": "mock"},
                "maker_mcp": {
                    "command": "npx",
                    "args": ["-y", "@taptap/maker@0.0.19", "mcp"],
                    "cwd": str(project),
                },
            }
        ),
        encoding="utf-8",
    )
    return Config(config_path)


def test_maker_setup_status_detects_project_and_commands():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        audit = build_maker_tool_audit(agent=_FakeAgent())

        status = build_maker_setup_status(
            config=cfg,
            app_root=_PROJECT_ROOT,
            tool_audit=audit,
        )

        assert status["version"] == "maker-setup.v1"
        assert status["project"]["maker_initialized"] is True
        assert status["project"]["project_id"] == "p1"
        assert status["maker_package"]["configured"] == "0.0.19"
        assert status["commands"]["install_maker_mcp"].startswith("npx -y @taptap/maker install")
        assert status["endpoints"]["tool_audit"] == "/maker/tool-audit"

        markdown = render_maker_setup_markdown(status)
        assert "Maker Setup Doctor" in markdown
        assert "generate_image" in markdown


def test_maker_setup_status_blocks_unbound_project_id_zero():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        maker_config = Path(cfg.project_root()) / ".maker-mcp" / "config.json"
        maker_config.write_text(
            json.dumps({"project_id": "0"}),
            encoding="utf-8",
        )

        status = build_maker_setup_status(
            config=cfg,
            app_root=_PROJECT_ROOT,
            tool_audit=build_maker_tool_audit(agent=_FakeAgent()),
        )

        assert status["readiness"] == "blocked"
        assert "maker_project_not_bound" in status["blockers"]
        assert status["project"]["maker_initialized"] is True
        assert status["project"]["project_bound"] is False
        assert "绑定真实 Maker 项目" in status["commands"]["recommended_next"]


def test_maker_tool_audit_checks_remote_registry_and_executor():
    audit = build_maker_tool_audit(agent=_FakeAgent())

    assert audit["ok"] is True
    assert audit["remote_tool_count"] == len(REQUIRED_PROXY_TOOLS)
    assert audit["missing_registration"] == []
    assert audit["missing_proxy_side_effect_marks"] == []
    assert all(row["executor_handler"] for row in audit["required_proxy_tools"])


def test_maker_tool_audit_reports_remote_capability_gap():
    audit = build_maker_tool_audit(agent=_PartialAgent())

    assert audit["ok"] is False
    assert audit["readiness"] == "degraded"
    assert audit["local_registration_complete"] is True
    assert audit["remote_capability_complete"] is False
    assert audit["repair_ok"] is True
    assert audit["requires_remote_capability"] is True
    assert "一键修复已完成本地挂载" in audit["diagnosis"]
    assert set(audit["missing_required_proxy_tools"]) == set(REQUIRED_PROXY_TOOLS)


def test_maker_setup_fault_analysis_tracks_remote_capability_gap():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        audit = build_maker_tool_audit(agent=_PartialAgent())

        status = build_maker_setup_status(
            config=cfg,
            app_root=_PROJECT_ROOT,
            tool_audit=audit,
        )

        analysis = status["fault_analysis"]
        fault_codes = [fault["code"] for fault in analysis["faults"]]
        assert analysis["version"] == "maker-fault-rules.v1"
        assert "maker_remote_capability_missing" in fault_codes
        assert analysis["one_click_repair"]["can_run_now"] is True
        assert "maker_remote_capability_missing" in analysis["one_click_repair"]["manual_faults"]


def test_internal_maker_mcp_config_normalizes_pinned_version_to_latest():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        project = tmp_path / "maker-game"

        result = ensure_internal_maker_mcp_latest_config(cfg, project)

        assert result["changed"] is True
        assert result["normalized"] is True
        assert result["before"]["configured_version"] == "0.0.19"
        assert result["after"]["configured_version"] == "latest"
        assert "@taptap/maker@0.0.19" not in " ".join(cfg.data["maker_mcp"]["args"])
        assert str(project.resolve()) == cfg.data["maker_mcp"]["cwd"]
        env = cfg.data["maker_mcp"]["env"]
        assert env["TAPTAP_MCP_ENV"] == "production"
        assert env["TAPTAP_MAKER_HOME"].endswith("portable/home/.taptap-maker") or env["TAPTAP_MAKER_HOME"].endswith("portable\\home\\.taptap-maker")
        assert env["TTM_MAKER_HOME"] == env["TAPTAP_MAKER_HOME"]


def test_agent_root_mcp_registration_writes_local_agent_configs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        before = agent_root_mcp_state(root)
        result = ensure_agent_root_maker_mcp_registration(root)
        after = agent_root_mcp_state(root)

        assert before["registered"] is False
        assert result["ok"] is True
        assert result["changed"]
        assert after["registered"] is True
        assert (root / ".cursor" / "mcp.json").exists()
        assert (root / ".mcp.json").exists()
        assert (root / ".codex" / "mcp.json").exists()
        assert (root / ".codex" / "config.toml").exists()
        assert "@taptap/maker" in (root / ".cursor" / "mcp.json").read_text(encoding="utf-8")


def test_prepare_auth_flow_keeps_auth_inside_embedded_browser():
    flow = prepare_auth_flow("https://accounts.taptap.cn/oauth")

    assert flow["ok"] is True
    assert flow["open_in_embedded_browser"] is True
    assert flow["after_success_url"] == "https://maker.taptap.cn/"
    assert "system default browser" in flow["note"]


if __name__ == "__main__":
    test_maker_setup_status_detects_project_and_commands()
    test_maker_setup_status_blocks_unbound_project_id_zero()
    test_maker_tool_audit_checks_remote_registry_and_executor()
    test_maker_tool_audit_reports_remote_capability_gap()
    test_internal_maker_mcp_config_normalizes_pinned_version_to_latest()
    test_agent_root_mcp_registration_writes_local_agent_configs()
    test_prepare_auth_flow_keeps_auth_inside_embedded_browser()
    print("[PASS] maker setup")
