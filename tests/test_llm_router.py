"""Tests for the v0.7.0 LLM router with fallback."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from typing import Any, Dict, List

from llm.interface import LLMInterface
from llm.router import LLMRouter, RouterConfig, build_router_from_config


class StubProvider(LLMInterface):
    """Stub LLM provider with controllable failure modes."""

    def __init__(self, name: str, *, fail: bool = False, fail_methods=None) -> None:
        self.name = name
        self.fail = fail
        self.fail_methods = set(fail_methods or [])
        self.calls: List[str] = []

    def _maybe_fail(self, method: str) -> None:
        if self.fail or method in self.fail_methods:
            raise RuntimeError(f"{self.name} forced to fail on {method}")

    def think(self, task, context, trajectory, tools_description) -> str:
        self.calls.append("think")
        self._maybe_fail("think")
        return f"{self.name}:think"

    def choose_action(self, task, thought, tools_description) -> Dict[str, Any]:
        self.calls.append("choose_action")
        self._maybe_fail("choose_action")
        return {"tool": f"{self.name}-tool", "params": {}}

    def reflect(self, prompt) -> str:
        self.calls.append("reflect")
        self._maybe_fail("reflect")
        return f"{self.name}:reflect"

    def generate_code(self, prompt) -> str:
        self.calls.append("generate_code")
        self._maybe_fail("generate_code")
        return f"{self.name}:code"


# ---------- construction ----------


def test_router_requires_primary():
    try:
        LLMRouter(primary=None)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_router_accepts_empty_fallbacks():
    primary = StubProvider("primary")
    router = LLMRouter(primary=primary, fallbacks=[])
    assert router.get_stats() != []


# ---------- happy path ----------


def test_router_calls_primary_when_healthy():
    primary = StubProvider("primary")
    fallback = StubProvider("fallback")
    router = LLMRouter(primary=primary, fallbacks=[fallback])

    assert router.think("t", "c", [], "tools") == "primary:think"
    assert router.choose_action("t", "thought", "tools")["tool"] == "primary-tool"
    assert router.reflect("p") == "primary:reflect"
    assert router.generate_code("p") == "primary:code"

    # Fallback never called when primary is healthy.
    assert fallback.calls == []
    assert primary.calls == ["think", "choose_action", "reflect", "generate_code"]


# ---------- fallback path ----------


def test_router_falls_back_to_secondary_when_primary_fails():
    primary = StubProvider("primary", fail=True)
    fallback = StubProvider("fallback")
    router = LLMRouter(primary=primary, fallbacks=[fallback])

    assert router.think("t", "c", [], "tools") == "fallback:think"
    assert router.reflect("p") == "fallback:reflect"


def test_router_falls_back_through_multiple_providers():
    primary = StubProvider("primary", fail=True)
    secondary = StubProvider("secondary", fail=True)
    tertiary = StubProvider("tertiary")
    router = LLMRouter(primary=primary, fallbacks=[secondary, tertiary])

    assert router.think("t", "c", [], "tools") == "tertiary:think"


def test_router_raises_when_all_providers_fail():
    primary = StubProvider("primary", fail=True)
    fallback = StubProvider("fallback", fail=True)
    router = LLMRouter(primary=primary, fallbacks=[fallback])
    try:
        router.think("t", "c", [], "tools")
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError when all providers fail")


def test_router_falls_back_per_method():
    """Primary works for some methods, fails for others — router uses fallback only on failing methods."""
    primary = StubProvider("primary", fail_methods={"think"})
    fallback = StubProvider("fallback")
    router = LLMRouter(primary=primary, fallbacks=[fallback])

    # think should fall back
    assert router.think("t", "c", [], "tools") == "fallback:think"
    # reflect still uses primary
    assert router.reflect("p") == "primary:reflect"


# ---------- stats ----------


def test_router_records_stats_per_provider():
    primary = StubProvider("primary")
    fallback = StubProvider("fallback")
    router = LLMRouter(primary=primary, fallbacks=[fallback])

    router.think("t", "c", [], "tools")          # primary ok
    router.reflect("p")                            # primary ok
    primary.fail = True
    router.reflect("p2")                           # primary fails, fallback ok
    router.generate_code("p3")                     # primary fails, fallback ok

    stats = {entry["provider"]: entry for entry in router.get_stats()}
    # primary tried 4 times (1 think + 2 reflect + 1 code), 2 succeeded
    assert stats["primary"]["total_calls"] == 4
    assert stats["primary"]["success_calls"] == 2
    assert stats["fallback"]["total_calls"] == 2
    assert stats["fallback"]["fallback_calls"] == 2
    assert stats["fallback"]["success_calls"] == 2


def test_router_records_last_error_for_failed_provider():
    primary = StubProvider("primary", fail=True)
    fallback = StubProvider("fallback")
    router = LLMRouter(primary=primary, fallbacks=[fallback])
    router.think("t", "c", [], "tools")

    stats = {entry["provider"]: entry for entry in router.get_stats()}
    assert "forced to fail" in stats["primary"]["last_error"]


def test_router_callback_fires_on_success_and_failure():
    primary = StubProvider("primary", fail=True)
    fallback = StubProvider("fallback")
    events: List[tuple] = []

    def cb(provider: str, ok: bool) -> None:
        events.append((provider, ok))

    router = LLMRouter(primary=primary, fallbacks=[fallback], on_provider_used=cb)
    router.think("t", "c", [], "tools")

    # Primary failed, fallback succeeded.
    assert events == [("primary", False), ("fallback", True)]


# ---------- router config ----------


def test_router_uses_default_router_config():
    primary = StubProvider("primary")
    router = LLMRouter(primary=primary)
    assert isinstance(router._config, RouterConfig)
    assert router._config.per_provider_timeout_seconds == 60.0


def test_router_accepts_custom_router_config():
    primary = StubProvider("primary")
    cfg = RouterConfig(per_provider_timeout_seconds=10.0, retries_per_provider=2)
    router = LLMRouter(primary=primary, config=cfg)
    assert router._config.retries_per_provider == 2


# ---------- build_router_from_config ----------


def test_build_router_from_config_with_fallbacks(monkeypatch):
    """Build a router from a Config-like object that exposes fallback_providers."""
    class _CfgStub:
        def llm_provider(self):
            return "deepseek"
        def get(self, key, default=None):
            return [
                {"provider": "qwen"},
                {"provider": "anthropic"},
            ]

    # Mock the factory — `build_router_from_config` imports it lazily inside
    # the function body, so patch the source module directly.
    class _FakeFactory:
        @staticmethod
        def create(provider, cfg):
            return StubProvider(f"provider:{provider}")

    monkeypatch.setattr("llm.llm_factory.LLMFactory", _FakeFactory)
    router = build_router_from_config(_CfgStub())
    stats = {entry["provider"] for entry in router.get_stats()}
    assert "provider:deepseek" in stats
    assert "provider:qwen" in stats
    assert "provider:anthropic" in stats