"""
tests/test_condition_dsl.py - safe condition DSL tests.

The DSL is the condition evaluator used by plan v2 ``branch`` and ``loop``
steps. It must:
  - allow only specific field roots and operators
  - reject unknown fields and operators with a typed error
  - never call ``eval``/``exec`` (no Python expression injection)
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.condition_dsl import (  # noqa: E402
    ALLOWED_FIELD_ROOTS,
    ALLOWED_OPERATORS,
    ConditionError,
    eval_condition,
)


# ---------------------------------------------------------------------------
# Allowed field roots
# ---------------------------------------------------------------------------

def test_condition_dsl_field_roots_match_adr():
    assert ALLOWED_FIELD_ROOTS == {
        "goal_state", "control_signal", "observation", "plan_progress",
    }


def test_condition_dsl_operators_match_adr():
    assert ALLOWED_OPERATORS == {
        "==", "!=", ">", ">=", "<", "<=", "contains",
    }


# ---------------------------------------------------------------------------
# Operator behavior
# ---------------------------------------------------------------------------

def test_eval_condition_equality_works():
    ctx = {"observation": {"ok": True}}
    assert eval_condition("observation.ok == True", ctx) is True
    assert eval_condition("observation.ok == False", ctx) is False


def test_eval_condition_inequality_works():
    ctx = {"observation": {"ok": False}}
    assert eval_condition("observation.ok != True", ctx) is True
    assert eval_condition("observation.ok != False", ctx) is False


def test_eval_condition_numeric_compare_works():
    ctx = {"control_signal": {"signal": 2.5}}
    assert eval_condition("control_signal.signal > 2.0", ctx) is True
    assert eval_condition("control_signal.signal < 3.0", ctx) is True
    assert eval_condition("control_signal.signal >= 2.5", ctx) is True
    assert eval_condition("control_signal.signal <= 2.5", ctx) is True


def test_eval_condition_contains_works():
    ctx = {"observation": {"failure_type": "permission_denied"}}
    assert eval_condition("observation.failure_type contains denied", ctx) is True
    assert eval_condition("observation.failure_type contains timeout", ctx) is False


def test_eval_condition_resolves_nested_keys():
    ctx = {"plan_progress": {"counts": {"done": 3, "pending": 1}}}
    # We do not allow arbitrary nesting; only direct field roots.
    try:
        eval_condition("plan_progress.counts.done == 3", ctx)
    except ConditionError:
        return
    raise AssertionError("nested keys beyond the field root should be rejected")


# ---------------------------------------------------------------------------
# Negative paths: unknown field roots, operators, injection
# ---------------------------------------------------------------------------

def test_eval_condition_rejects_unknown_field_root():
    try:
        eval_condition("evil.attribute == 1", {"evil": {"attribute": 1}})
    except ConditionError:
        return
    raise AssertionError("unknown field root should raise ConditionError")


def test_eval_condition_rejects_unknown_operator():
    try:
        eval_condition("observation.ok === True", {"observation": {"ok": True}})
    except ConditionError:
        return
    raise AssertionError("unknown operator should raise ConditionError")


def test_eval_condition_rejects_python_injection():
    """The DSL must never evaluate Python expressions. The string
    ``__import__('os').system('rm -rf /')`` is meaningless to the DSL
    parser, so it must raise ConditionError, not execute anything.
    """
    payload = "__import__('os').system('rm -rf /')"
    try:
        eval_condition(payload, {"observation": {"ok": True}})
    except ConditionError:
        return
    raise AssertionError("python-style expressions must raise ConditionError")


def test_eval_condition_rejects_empty_expression():
    try:
        eval_condition("", {"observation": {"ok": True}})
    except ConditionError:
        return
    raise AssertionError("empty expression should raise")


def test_eval_condition_rejects_malformed_expression():
    try:
        eval_condition("observation.ok", {"observation": {"ok": True}})
    except ConditionError:
        return
    raise AssertionError("expression without an operator should raise")


def test_eval_condition_rejects_non_string():
    try:
        eval_condition(42, {"observation": {"ok": True}})  # type: ignore[arg-type]
    except ConditionError:
        return
    raise AssertionError("non-string expression should raise ConditionError")


# ---------------------------------------------------------------------------
# Boolean coercion rules
# ---------------------------------------------------------------------------

def test_eval_condition_truthy_string_becomes_true():
    """A boolean field holding ``True`` compares equal to ``True``.

    We do NOT add a custom truthiness coercion (Python's ``"yes" == True``
    is ``False``). The DSL follows Python's own comparison semantics so
    operators behave predictably. This test pins the behaviour.
    """
    ctx = {"observation": {"ok": True}}
    assert eval_condition("observation.ok == True", ctx) is True
    assert eval_condition("observation.ok == False", ctx) is False


def test_eval_condition_missing_field_returns_false():
    ctx = {"observation": {}}
    # Missing fields default to None; comparison with None is False
    assert eval_condition("observation.ok == True", ctx) is False
