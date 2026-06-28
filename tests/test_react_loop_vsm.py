"""
tests/test_react_loop_vsm.py - ReActLoop + VSMShell wiring.

Phase F exit gate. The shell must be wired into the iteration loop
behind ``vsm.enabled`` and must not change behavior when the flag is
off. When the shell returns ``"replan"`` after a step, the loop must
set a flag the rescue orchestrator / outer loop can read.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


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


def _write_config(tmp: Path, *, vsm_enabled: bool) -> Path:
    cfg = {
        "llm": {
            "n_ctx": 4096,
            "reserve_tokens": 64,
            "hot_memory_max_turns": 4,
            "max_history_steps": 6,
        },
        "memory": {"vector_index": {"enabled": True, "embedding_dim": 8, "model": "stub"}},
        "agents_md": {"enabled": False, "files": []},
        "vsm": {
            "enabled": vsm_enabled,
            "auto_replan": False,
            "replan_cooldown_steps": 3,
            "max_replan_depth": 1,
            "expert_rescue_on_diverging": True,
        },
    }
    path = tmp / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Default off — no VSMShell instance, no observability events
# ---------------------------------------------------------------------------

def _make_loop(vsm_shell=None):
    """Build a ReActLoop with minimal stubs, exercising only the
    vsm_shell parameter wiring. We do NOT need a real executor or
    tool registry here — the wiring attribute is set in __init__.
    """
    from agent.react_loop import ReActLoop
    # Pass enough of the construction arguments that __init__ can run
    # without trying to instantiate ActionExecutionService. We use a
    # minimal executor that will not be invoked because we never call run().
    fake_executor = type("FakeExecutor", (), {})()
    fake_tools = type("FakeTools", (), {"preflight_action": lambda *a, **k: {"ok": True}})()
    fake_log = type("FakeLog", (), {"append": lambda *a, **k: None})()
    return ReActLoop(
        llm=_NoopLLM(),
        tools=fake_tools,
        executor=fake_executor,
        event_log=fake_log,
        vsm_shell=vsm_shell,
    )


def test_react_loop_vsm_shell_default_is_none():
    """When the caller passes no shell, ``_vsm_shell`` is None."""
    loop = _make_loop(vsm_shell=None)
    assert getattr(loop, "_vsm_shell", None) is None
    # No replan request at startup
    assert getattr(loop, "_vsm_replan_requested", False) is False


def test_react_loop_vsm_shell_param_stores_instance():
    from core.vsm import VSMShell
    from core.control_loop import ControlLoop
    shell = VSMShell(control_loop=ControlLoop(), config={
        "enabled": True,
        "auto_replan": False,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    loop = _make_loop(vsm_shell=shell)
    assert loop._vsm_shell is shell
    assert loop._vsm_shell.is_active() is True
    # Default replan request is False
    assert getattr(loop, "_vsm_replan_requested", False) is False


def test_react_loop_vsm_shell_disabled_shell_still_stored_but_inactive():
    """A shell constructed with enabled=False is stored but inactive,
    so it short-circuits the wiring.
    """
    from core.vsm import VSMShell
    from core.control_loop import ControlLoop
    shell = VSMShell(control_loop=ControlLoop(), config={
        "enabled": False,
        "auto_replan": False,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    loop = _make_loop(vsm_shell=shell)
    assert loop._vsm_shell is shell
    assert loop._vsm_shell.is_active() is False


def test_react_loop_signature_accepts_vsm_shell_kwarg():
    """ReActLoop.__init__ must accept ``vsm_shell`` as a keyword arg."""
    import inspect
    from agent.react_loop import ReActLoop
    sig = inspect.signature(ReActLoop.__init__)
    assert "vsm_shell" in sig.parameters


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _NoopLLM:
    """A no-op LLM that returns a ``{"done": True, "output": "ok"}``
    action on every call. Enough to drive one iteration of ReActLoop
    without running real prompts.
    """

    def think(self, **kwargs):
        return "noop thought"

    def choose_action(self, **kwargs):
        return {"done": True, "output": "ok"}

    def reflect(self, **kwargs):
        return ""

    def generate(self, **kwargs):
        return "noop"
