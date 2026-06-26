"""Verify the v0.6.0 public API is importable from the core namespace.

This test pins the surface area exported by `core/__init__.py` so accidental
regressions (removed symbols, renamed helpers) are caught at unit-test time.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import core


def test_core_exposes_event_log_and_health():
    assert callable(core.EventLog)
    assert callable(core.Event)
    assert callable(core.HealthMonitor)
    assert callable(core.AgentHealthState)


def test_core_exposes_plan_first_symbols():
    assert callable(core.empty_plan)
    assert callable(core.normalize_plan)
    assert callable(core.plan_progress)
    assert callable(core.plan_to_context_block)
    assert callable(core.update_step_status)
    assert callable(core.build_plan_prompt)
    assert callable(core.extract_plan_from_llm_text)
    assert callable(core.review_plan)
    assert callable(core.validate_plan_step)
    assert callable(core.summarize_plan_validation)
    assert isinstance(core.PLAN_FORMAT_VERSION, str)
    assert isinstance(core.KNOWN_TOOLS, set)


def test_core_exposes_coding_agent_symbols():
    assert callable(core.matches_predicate)
    assert callable(core.select_applicable_hooks)
    assert callable(core.compress_trajectory)
    assert callable(core.extract_repeated_tool_warnings)
    assert callable(core.render_compression_hint)
    assert callable(core.should_compress)
    assert callable(core.ControlLoop)
    assert callable(core.LoopScheduler)
    assert callable(core.schedule_loop)
    assert callable(core.ScrollChapterMemory)
    assert callable(core.fingerprint_chapter)
    assert callable(core.make_chapter)


def test_core_all_exports_match_dunder_all():
    """Every name in __all__ must actually be importable from the package."""
    for name in core.__all__:
        assert hasattr(core, name), f"core.{name} listed in __all__ but missing"