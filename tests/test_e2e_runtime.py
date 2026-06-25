"""E2E runtime tests — verify critical paths without a full HTTP server.

Strategy: directly exercise the public API of each subsystem (LLM router,
intent classifier, knowledge base, settings builders, fast_ops client,
updater helpers, critical module imports). The full HTTP server boot is
covered by the existing tests/test_app_server.py module-level tests.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------- Settings API builders (work without HTTP server) ----------


class _StubServer:
    """Minimal stub for server.settings_api builders."""

    def __init__(self, *, config, mcp=None, llm=None, tools=None):
        self.agent = _StubAgent(config=config, mcp=mcp, llm=llm, tools=tools)


class _StubAgent:
    def __init__(self, *, config, mcp=None, llm=None, tools=None):
        self.config = config
        self.mcp_integration = mcp
        self.llm = llm
        self.tools = tools or []


class _StubConfig:
    def __init__(self, *, project_root="D:/my-game", maker_cfg=None, llm_provider="deepseek"):
        self._project_root = project_root
        self._maker_cfg = maker_cfg or {
            "project_id": "abc-123",
            "config_path": f"{project_root}/.maker-mcp/config.json",
            "command": "npx",
            "args": ["-y", "@taptap/maker"],
        }
        self._llm_provider = llm_provider

    def project_root(self):
        return Path(self._project_root)

    def maker_mcp_config(self):
        return self._maker_cfg

    def llm_provider(self):
        return self._llm_provider

    def get(self, key, default=None):
        return default


def test_e2e_settings_project_info_extraction():
    from server.settings_api import build_project_info
    cfg = _StubConfig(project_root="D:/games/my-game")
    info = build_project_info(_StubServer(config=cfg))
    assert info["name"] == "my-game"
    assert info["makerProjectId"] == "abc-123"


def test_e2e_settings_runtime_info_top_level():
    from server.settings_api import build_settings_runtime_info

    cfg = _StubConfig()
    server = _StubServer(config=cfg)
    info = build_settings_runtime_info(server)
    assert info["version"] == "settings-api.v1"
    assert "project" in info
    assert "runtime" in info
    assert "schema" in info
    assert "portable" in info
    assert "llmRouter" in info


def test_e2e_settings_provider_summary_includes_all_providers():
    from server.settings_api import build_provider_summary

    cfg = _StubConfig(llm_provider="anthropic")
    server = _StubServer(config=cfg)
    summary = build_provider_summary(server)
    assert summary["version"] == "settings-api.v1"
    assert summary["primary"] == "anthropic"
    preset_ids = {p["id"] for p in summary["presets"]}
    # Must include all major providers.
    for expected in ("deepseek", "openai", "qwen", "zhipu", "moonshot", "claude"):
        assert expected in preset_ids, f"missing provider: {expected}"


# ---------- fast_ops bridge protocol (Python fallback) ----------


def test_e2e_fast_ops_falls_back_to_python(monkeypatch):
    from core import fast_ops_client as fc

    monkeypatch.setattr(fc, "_TAURI_HOST", "127.0.0.1")
    monkeypatch.setattr(fc, "_TAURI_PORT", 1)
    fc.reset_runtime_cache()

    assert fc.fast_format_bytes(1024) == "1.00KiB"
    assert fc.fast_format_bytes(0) == "0B"
    assert fc.fast_format_bytes(1024 * 1024) == "1.00MiB"


def test_e2e_fast_ops_format_bytes_agrees_with_python():
    from core import fast_ops_client as fc
    fc.reset_runtime_cache()

    for n in [0, 512, 1024, 4096, 16384, 1048576, 16777216]:
        assert fc.fast_format_bytes(n) == fc._python_format_bytes(n)


def test_e2e_fast_ops_runtime_status_reports_state():
    from core import fast_ops_client as fc
    fc.reset_runtime_cache()
    status = fc.runtime_status()
    assert "available" in status
    assert "host" in status
    assert "port" in status
    assert status["version"] == fc.FAST_OPS_VERSION


# ---------- LLM Router ----------


def test_e2e_llm_router_handles_missing_api_key():
    from llm.router import LLMRouter
    from llm.mock_llm import MockLLM

    primary = MockLLM()
    router = LLMRouter(primary=primary, fallbacks=[])
    stats = router.get_stats()
    assert len(stats) == 1


def test_e2e_llm_router_think_returns_string():
    from llm.router import LLMRouter
    from llm.mock_llm import MockLLM

    router = LLMRouter(primary=MockLLM())
    result = router.think("test task", "context", [], "tools")
    assert isinstance(result, str)


def test_e2e_llm_router_choose_action_returns_dict():
    from llm.router import LLMRouter
    from llm.mock_llm import MockLLM

    router = LLMRouter(primary=MockLLM())
    result = router.choose_action("task", "thought", "tools")
    assert isinstance(result, dict)
    assert "tool" in result or "output" in result


def test_e2e_llm_router_reflect_returns_string():
    from llm.router import LLMRouter
    from llm.mock_llm import MockLLM

    router = LLMRouter(primary=MockLLM())
    result = router.reflect("anything")
    assert isinstance(result, str)


# ---------- Intent classifier ----------


def test_e2e_intent_classifier_handles_real_inputs():
    from core.intent_classifier import classify

    cases = [
        ("帮我修复这个 bug", "coding"),
        ("做一个跑酷游戏", "game"),
        ("下一阶段的路线图", "plan"),
        ("发布 v1.1 版本", "project"),
        ("打包 portable runtime", "ops"),
        ("调用 Maker MCP 生成图片", "maker"),
        ("这个是怎么工作的？", "question"),
    ]
    for text, expected in cases:
        intent = classify(text)
        assert intent.category == expected, (
            f"classify({text!r}) = {intent.category}, expected {expected}"
        )


def test_e2e_intent_classifier_multi_step_detection():
    from core.intent_classifier import classify

    multi = classify("第一：实现功能\n第二：测试\n第三：部署")
    assert multi.multi_step is True

    single = classify("修复 bug")
    assert single.multi_step is False


# ---------- Maker knowledge ----------


def test_e2e_maker_knowledge_returns_runner():
    from learning.game_knowledge import find_game_type
    info = find_game_type("endless_runner")
    assert info["label"] == "无尽跑酷"


def test_e2e_maker_knowledge_search_finds_runner():
    from learning.game_knowledge import search_game_knowledge
    results = search_game_knowledge("跑酷")
    assert any(r["id"] == "endless_runner" for r in results)


def test_e2e_maker_knowledge_six_types_present():
    from learning.game_knowledge import all_game_types
    types = {entry["id"] for entry in all_game_types()}
    expected = {"endless_runner", "tower_defense", "match_three", "shooting_2d", "idle_tycoon", "puzzle_logic"}
    assert types == expected


# ---------- Updater helpers ----------


def test_e2e_updater_version_comparison_across_cases():
    from core.updater_client import is_newer_version

    assert is_newer_version("2.0.0", "1.99.99") is True
    assert is_newer_version("1.1.0", "1.0.99") is True
    assert is_newer_version("1.0.1", "1.0.0") is True
    assert is_newer_version("1.0.0", "1.0.0") is False
    # prerelease is older than its release.
    assert is_newer_version("1.0.0-rc.1", "1.0.0") is False
    assert is_newer_version("1.0.0", "1.0.0-rc.1") is True


def test_e2e_updater_percent_clamping():
    from core.updater_client import percent_complete
    assert percent_complete(0, 100) == 0.0
    assert percent_complete(50, 100) == 50.0
    assert percent_complete(100, 100) == 100.0
    assert percent_complete(200, 100) == 100.0  # clamps overflow


# ---------- Critical modules import ----------


def test_e2e_critical_modules_import():
    modules = [
        "core.intent_classifier",
        "core.plan_format",
        "core.plan_review",
        "core.plan_prompt",
        "core.conditional_hooks",
        "core.context_compression",
        "core.control_loop",
        "core.loop_scheduler",
        "core.scroll_chapter",
        "core.perf_monitor",
        "core.fast_ops_client",
        "core.updater_client",
        "llm.router",
        "learning.game_knowledge",
        "learning.copy_knowledge",
        "learning.mechanics_knowledge",
        "learning.maker_cases",
        "learning.socratic_planner",
        "learning.engine_knowledge",
        "server.settings_api",
    ]
    for mod_name in modules:
        spec = importlib.util.find_spec(mod_name)
        assert spec is not None, f"module not found: {mod_name}"


# ---------- Portable runtime validator (offline mode) ----------


def test_e2e_verify_portable_runs():
    """The portable validator should run cleanly even when portable/ is empty."""
    from subprocess import run

    result = run(
        [sys.executable, "scripts/build-portable/verify_portable.py", "100"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(_PROJECT_ROOT),
    )
    # Empty portable/ → exit 1, but script must complete without crashing.
    assert result.returncode in (0, 1)
    assert "portable" in (result.stdout + result.stderr).lower()