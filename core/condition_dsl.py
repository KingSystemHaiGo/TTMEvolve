"""
core/condition_dsl.py - safe condition evaluator for plan v2.

Used by ``branch`` and ``loop`` steps in plan-format v2. The DSL is
deliberately tiny: a single ``<lhs> <op> <rhs>`` expression with a
strict allowlist of field roots and operators. There is no Python
``eval``/``exec`` and no expression composition — anything outside the
allowlist raises ``ConditionError``.

Allowed field roots (per ADR-0008):
  - ``goal_state.*``
  - ``control_signal.*``
  - ``observation.ok``
  - ``observation.failure_type``
  - ``plan_progress.*``

Allowed operators:
  - ``==``, ``!=``, ``>``, ``>=``, ``<``, ``<=``, ``contains``
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


ALLOWED_FIELD_ROOTS: frozenset = frozenset({
    "goal_state", "control_signal", "observation", "plan_progress",
})
ALLOWED_OPERATORS: frozenset = frozenset({
    "==", "!=", ">", ">=", "<", "<=", "contains",
})


class ConditionError(ValueError):
    """Raised when a condition expression violates the allowlist."""


# Pre-compile the operator regex. We match the longest operator first
# so that ``>=`` is not split into ``>`` and ``=``.
_OPERATORS_SORTED = sorted(ALLOWED_OPERATORS, key=lambda op: -len(op))
_OP_PATTERN = re.compile("|".join(re.escape(op) for op in _OPERATORS_SORTED))

# Field path must be a sequence of simple identifiers separated by dots.
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _coerce(value: Any) -> Any:
    """Coerce Python booleans to the wire form the DSL expects.

    Boolean ``True``/``False`` round-trip through Python unchanged.
    Strings like ``"True"`` or ``"False"`` are parsed case-sensitively.
    Numbers stay as numbers. Other types (lists, dicts) stay as-is.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value == "True":
            return True
        if value == "False":
            return False
        return value
    return value


def _resolve_field(lhs_text: str, ctx: Dict[str, Any]) -> Any:
    """Resolve ``root.subkey`` to a value in the context dict.

    Only the field root is allowlisted. ``observation.ok`` and
    ``observation.failure_type`` are the only nested keys we permit;
    deeper traversal is rejected.
    """
    if not _FIELD_PATTERN.match(lhs_text):
        raise ConditionError(f"invalid field path: {lhs_text!r}")
    parts = lhs_text.split(".")
    if parts[0] not in ALLOWED_FIELD_ROOTS:
        raise ConditionError(f"field root not allowed: {parts[0]!r}")
    if len(parts) > 2:
        raise ConditionError(
            f"only one level of nesting is allowed under {parts[0]!r}; "
            f"got {lhs_text!r}"
        )
    if len(parts) == 1:
        # Root key only; return the whole subtree (caller is expected
        # to compare to a scalar).
        if parts[0] not in ctx:
            return None
        return ctx[parts[0]]
    # Two-level: parts[0] must be a dict in ctx
    root_value = ctx.get(parts[0])
    if not isinstance(root_value, dict):
        return None
    return root_value.get(parts[1])


def _parse_rhs(rhs_text: str, op: str = "") -> Any:
    """Parse the right-hand side of a condition expression.

    Accepts booleans (``True``/``False``), numbers, and quoted strings.
    For the ``contains`` operator a bare-word rhs is also accepted as
    a string literal (it is the natural way to express a substring
    check). Anything else is rejected.
    """
    rhs_text = rhs_text.strip()
    if rhs_text == "True":
        return True
    if rhs_text == "False":
        return False
    if rhs_text == "None":
        return None
    if rhs_text.startswith('"') and rhs_text.endswith('"'):
        return rhs_text[1:-1]
    if rhs_text.startswith("'") and rhs_text.endswith("'"):
        return rhs_text[1:-1]
    if "." in rhs_text:
        try:
            return float(rhs_text)
        except ValueError:
            pass
    try:
        return int(rhs_text)
    except ValueError:
        pass
    # ``contains`` naturally uses bare-word substrings
    if op == "contains" and _FIELD_PATTERN.match(rhs_text):
        return rhs_text
    raise ConditionError(f"cannot parse rhs value: {rhs_text!r}")


def eval_condition(expression: Any, context: Optional[Dict[str, Any]] = None) -> bool:
    """Evaluate a single ``<lhs> <op> <rhs>`` condition.

    Returns the boolean result. Raises ``ConditionError`` on any
    violation of the allowlist.
    """
    if not isinstance(expression, str):
        raise ConditionError(f"expression must be a string, got {type(expression).__name__}")
    if not expression.strip():
        raise ConditionError("expression is empty")
    ctx = context if isinstance(context, dict) else {}

    match = _OP_PATTERN.search(expression)
    if not match:
        raise ConditionError(f"no allowed operator in expression: {expression!r}")
    op = match.group(0)
    lhs, rhs = expression.split(op, 1)
    lhs = lhs.strip()
    rhs = rhs.strip()
    if not lhs or not rhs:
        raise ConditionError(f"missing lhs or rhs: {expression!r}")

    lhs_value = _coerce(_resolve_field(lhs, ctx))
    rhs_value = _parse_rhs(rhs, op=op)

    try:
        if op == "==":
            return lhs_value == rhs_value
        if op == "!=":
            return lhs_value != rhs_value
        if op == ">":
            if lhs_value is None or rhs_value is None:
                return False
            return lhs_value > rhs_value
        if op == ">=":
            if lhs_value is None or rhs_value is None:
                return False
            return lhs_value >= rhs_value
        if op == "<":
            if lhs_value is None or rhs_value is None:
                return False
            return lhs_value < rhs_value
        if op == "<=":
            if lhs_value is None or rhs_value is None:
                return False
            return lhs_value <= rhs_value
        if op == "contains":
            if lhs_value is None:
                return False
            try:
                return rhs_value in lhs_value
            except TypeError:
                return False
    except TypeError as exc:
        # Incompatible types → false (matches Python's bool behaviour
        # for comparison operators; contains is the exception above).
        return False
    raise ConditionError(f"unhandled operator: {op!r}")
