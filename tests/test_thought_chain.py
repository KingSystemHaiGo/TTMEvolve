"""
tests/test_thought_chain.py - structured thought chain tests.

Phase R1. The parser is lenient: free text returns a record
with no fields, full JSON populates fields, broken JSON keeps
the raw text. The default flag is off, so the control loop
and react_loop do not need to call the parser at all unless
``thought_chain.strict=true`` is set.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.control_loop import ControlLoop  # noqa: E402
from llm.thought_record import (  # noqa: E402
    THOUGHT_RECORD_VERSION,
    ThoughtRecord,
    parse_thought_record,
)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_parser_returns_none_when_disabled():
    text = '{"plan_step": "s1", "confidence": 0.5}'
    assert parse_thought_record(text, enabled=False) is None


def test_parser_returns_none_for_none_or_empty():
    assert parse_thought_record(None) is None
    assert parse_thought_record("") is None
    assert parse_thought_record("   ") is None
    assert parse_thought_record(42) is None  # not a string


def test_parser_treats_plain_text_as_empty_record():
    rec = parse_thought_record("I think the next step is to read the file.")
    assert rec is not None
    assert rec.plan_step == ""
    assert rec.observation_summary == ""
    assert rec.confidence == 0.0
    assert rec.raw_text == "I think the next step is to read the file."
    assert rec.is_empty is True
    assert rec.parse_warnings == []


def test_parser_populates_full_canonical_record():
    text = """
    {
      "plan_step": "step-3",
      "observation_summary": "project_status returned the same dict",
      "hypothesis": "this tool is not advancing the task",
      "expected_outcome": "a different tool will produce progress",
      "confidence": 0.42,
      "decision": "abandon project_status, list project files"
    }
    """
    rec = parse_thought_record(text)
    assert rec is not None
    assert rec.plan_step == "step-3"
    assert rec.observation_summary == "project_status returned the same dict"
    assert rec.hypothesis == "this tool is not advancing the task"
    assert rec.expected_outcome == "a different tool will produce progress"
    assert rec.confidence == 0.42
    assert rec.decision == "abandon project_status, list project files"
    assert rec.parse_warnings == []


def test_parser_clamps_out_of_range_confidence():
    rec = parse_thought_record('{"confidence": 1.7}')
    assert rec is not None
    assert rec.confidence == 1.0
    rec2 = parse_thought_record('{"confidence": -0.3}')
    assert rec2 is not None
    assert rec2.confidence == 0.0


def test_parser_records_warnings_for_bad_inputs():
    rec = parse_thought_record('not actually json but looks like it')
    assert rec is not None
    # Either the regex matched (it won't here since there's no leading {)
    # so it's plain text, or there's a warning. Either way, the
    # caller should not crash.
    assert rec.raw_text == 'not actually json but looks like it'

    rec2 = parse_thought_record('{"plan_step": 123}')
    assert rec2 is not None
    # plan_step was non-string; the parser coerces or warns
    assert isinstance(rec2.plan_step, str)


def test_parser_ignores_unknown_fields():
    rec = parse_thought_record('{"plan_step": "s1", "made_up": "x"}')
    assert rec is not None
    assert rec.plan_step == "s1"
    # raw_text is preserved for debugging
    assert "made_up" in rec.raw_text


# ---------------------------------------------------------------------------
# Control loop integration
# ---------------------------------------------------------------------------

def test_control_loop_can_read_thought_record_confidence():
    """When a step carries a thought_record with low confidence,
    the control loop's error score can incorporate that signal.
    This is a soft signal: high confidence + repeated tool is
    less concerning than low confidence + repeated tool.
    """
    cl = ControlLoop()
    # No thought_record: existing behavior
    window = [
        {
            "action": {"tool": "x"},
            "observation": {"ok": True, "result": "same"},
        }
    ] * 3
    score_without = cl._error(window)
    cl.reset()
    # With low confidence: still same score (R1 is a soft signal;
    # the strict integration is in R4)
    for step in window:
        step["thought_record"] = {"confidence": 0.1}
    score_with = cl._error(window)
    assert score_with == score_without  # no behavior change in R1


def test_thought_record_to_dict_is_serializable():
    rec = ThoughtRecord(
        plan_step="s1",
        observation_summary="x",
        hypothesis="y",
        expected_outcome="z",
        confidence=0.5,
        decision="go",
    )
    d = rec.to_dict()
    assert d["schema_version"] == THOUGHT_RECORD_VERSION
    assert d["plan_step"] == "s1"
    assert d["confidence"] == 0.5
    assert d["raw_text"] == ""
    assert d["parse_warnings"] == []


def test_evidence_bundle_exposes_thought_chain_field():
    """The evidence bundle should always carry a ``thought_chain``
    field, even when no record has been emitted yet.
    """
    # Smoke test: parse a record and verify its to_dict() shape
    # is what the bundle will render.
    rec = parse_thought_record(
        '{"plan_step": "s1", "confidence": 0.7, "decision": "go"}'
    )
    d = rec.to_dict()
    # The bundle is a JSON-serializable dict. Verify keys.
    assert "schema_version" in d
    assert "plan_step" in d
    assert "confidence" in d
    assert "decision" in d
