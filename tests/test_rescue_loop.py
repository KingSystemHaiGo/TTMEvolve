"""
tests/test_rescue_loop.py — end-to-end rescue loop tests
"""

from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent.agent import TapMakerAgent
from core.config import Config
from llm.interface import LLMInterface
from llm.mock_llm import MockLLM


class ExpertOnlyLLM(LLMInterface):
    """Test-only expert LLM that returns a RescueAction via reflect()."""

    def __init__(self, action):
        self.action = action

    def think(self, task, context, trajectory, tools_description):
        return "mock think"

    def choose_action(self, task, thought, tools_description):
        if self.action.get("mode") == "direct_action":
            return self.action["action"]
        return {"done": True, "output": "mock expert output"}

    def reflect(self, prompt):
        return json.dumps(self.action, ensure_ascii=False)

    def generate_code(self, prompt):
        return "def run(input): return {}"


def _make_local_llm():
    """Local model fails 3 times then succeeds."""
    return MockLLM(scripted_actions=[
        {"tool": "read_file", "params": {"path": "missing.txt"}},
        {"tool": "read_file", "params": {"path": "missing.txt"}},
        {"tool": "read_file", "params": {"path": "missing.txt"}},
        {"tool": "read_file", "params": {"path": "exists.txt"}},
        {"done": True, "output": "read exists.txt"},
    ])


def _make_config(tmpdir, storage, expert_enabled=False):
    cfg = Config()
    cfg.data = {
        "project_root": str(tmpdir),
        "storage_root": str(storage),
        "llm": {"provider": "mock"},
        "expert": {"enabled": expert_enabled, "provider": "mock", "api_key": "sk-test"},
        "rescue": {
            "max_consecutive_errors": 3,
            "max_iterations_ratio": 0.75,
            "detect_repeated_actions": False,
            "health_degraded": False,
            "max_rescue_per_session": 1,
            "cooldown_seconds": 0,
            "distill_after_rescue": False,
            "skip_if_no_expert_key": False,
        },
        "learning": {"skill_generation_enabled": False},
    }
    cfg._profiles = {}
    return cfg


def test_rescue_disabled():
    tmpdir = Path(tempfile.mkdtemp(prefix="ttm_rescue_off_"))
    storage = tmpdir / "storage"
    skills = tmpdir / "skills"
    skills.mkdir(parents=True, exist_ok=True)

    cfg = _make_config(tmpdir, storage, expert_enabled=False)
    agent = TapMakerAgent(llm=MockLLM(), config=cfg, project_root=tmpdir, storage_root=storage)
    assert agent.rescue_orchestrator is None
    print("[PASS] rescue disabled")


def test_rescue_thought_injection():
    from llm.expert_rescuer import ExpertRescuer

    rescuer = ExpertRescuer(Config())
    rescuer._llm = ExpertOnlyLLM({
        "mode": "thought_injection",
        "thought": "try reading exists.txt",
        "skill_seed": {"domain": "x", "rule": "r"},
    })
    rescuer._enabled = True

    action = rescuer.rescue(
        task="read file",
        trajectory=[],
        health_state={},
        tools_description="",
        warm_context="",
    )
    assert action.mode == "thought_injection"
    assert "exists.txt" in action.thought
    print("[PASS] thought injection mode")


def test_rescue_flow():
    tmpdir = Path(tempfile.mkdtemp(prefix="ttm_rescue_test_"))
    storage = tmpdir / "storage"
    skills = tmpdir / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    (tmpdir / "exists.txt").write_text("hello", encoding="utf-8")

    cfg = _make_config(tmpdir, storage, expert_enabled=True)
    local_llm = _make_local_llm()
    expert_action = {
        "mode": "direct_action",
        "action": {"tool": "read_file", "params": {"path": "exists.txt"}},
        "thought": "read existing file",
        "skill_seed": {
            "domain": "file",
            "rule": "check file existence before read",
            "context": "avoid missing file",
        },
    }

    agent = TapMakerAgent(llm=local_llm, config=cfg, project_root=tmpdir, storage_root=storage)
    assert agent.expert_rescuer is not None
    agent.expert_rescuer._llm = ExpertOnlyLLM(expert_action)

    result = agent.run("read exists.txt")

    expected = "read exists.txt"
    assert result["output"] == expected, "output mismatch: " + result["output"]

    sources = [s.get("source", "local") for s in result["trajectory"]]
    assert "expert" in sources, "no expert step: " + str(sources)

    print("[PASS] rescue flow completes task with expert help")


if __name__ == "__main__":
    test_rescue_disabled()
    test_rescue_thought_injection()
    test_rescue_flow()
    print("[PASS] all rescue loop tests")
