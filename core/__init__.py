"""
core/__init__.py — public surface of the core runtime.

The core layer holds the deterministic scaffolding around the LLM:
event log, executor, repair, hooks, planning, control loop, scroll
chapter memory, and the loop scheduler. Higher layers (agent, server,
learning) consume these.
"""

from .event_log import EventLog, Event
from .health import HealthMonitor, AgentHealthState
from .version_manager import VersionManager, VersionSnapshot
from .executor import Executor
from .repair import RepairScheduler

# v0.6.0 — Plan First
from .plan_format import (
    PLAN_FORMAT_VERSION,
    empty_plan,
    normalize_plan,
    plan_progress,
    plan_to_context_block,
    update_step_status,
)
from .plan_prompt import build_plan_prompt, extract_plan_from_llm_text
from .plan_review import (
    KNOWN_TOOLS,
    REVIEW_VERSION,
    review_plan,
)
from .plan_validation import (
    summarize_plan_validation,
    validate_plan_step,
)

# v0.6.0 — Coding Agent
from .conditional_hooks import (
    matches_predicate,
    select_applicable_hooks,
)
from .context_compression import (
    compress_trajectory,
    extract_repeated_tool_warnings,
    render_compression_hint,
    should_compress,
)
from .control_loop import ControlLoop
from .loop_scheduler import LoopScheduler, schedule_loop
from .scroll_chapter import (
    ScrollChapterMemory,
    fingerprint_chapter,
    make_chapter,
)

__all__ = [
    # core runtime
    "EventLog", "Event",
    "HealthMonitor", "AgentHealthState",
    "VersionManager", "VersionSnapshot",
    "Executor", "RepairScheduler",
    # plan first
    "PLAN_FORMAT_VERSION", "empty_plan", "normalize_plan",
    "plan_progress", "plan_to_context_block", "update_step_status",
    "build_plan_prompt", "extract_plan_from_llm_text",
    "KNOWN_TOOLS", "REVIEW_VERSION", "review_plan",
    "summarize_plan_validation", "validate_plan_step",
    # coding agent
    "matches_predicate", "select_applicable_hooks",
    "compress_trajectory", "extract_repeated_tool_warnings",
    "render_compression_hint", "should_compress",
    "ControlLoop", "LoopScheduler", "schedule_loop",
    "ScrollChapterMemory", "fingerprint_chapter", "make_chapter",
]
