"""Conditional hook triggers for the TTMEvolve hook system.

Extends the simple `apply(phase, text, context)` flow with predicate-based
gating: a hook only fires when its `when` clause matches the runtime context.

Supported `when` clauses:
- tool: matches when the action tool name equals the given string
- tool_prefix: matches when the action tool name starts with the given prefix
- verdict: matches when context['plan_validation']['verdict'] equals the value
- status: matches when the goal_checklist overall status equals the value
- session_id: matches when the current session_id equals the value
- expr: a tiny dot-path expression evaluated against context (e.g. "iteration>=2")

The hooks module can stay declarative: users write
  {"phase": "post_action", "type": "append", "content": "...",
   "when": {"tool": "modify_file", "verdict": "pass"}}
and the registry routes accordingly.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


Hook = Any  # same callable signature as core.hooks.Hook


def matches_predicate(predicate: Optional[Dict[str, Any]], context: Dict[str, Any]) -> bool:
    """Return True when a single `when` clause matches the runtime context.

    An empty / None predicate matches everything (the legacy "always fire"
    behavior).
    """
    if not predicate:
        return True
    if not isinstance(predicate, dict):
        return False
    action = context.get("action") if isinstance(context.get("action"), dict) else {}
    observation = context.get("observation") if isinstance(context.get("observation"), dict) else {}
    plan_validation = observation.get("plan_validation") if isinstance(observation.get("plan_validation"), dict) else {}
    checklist = context.get("goal_checklist") if isinstance(context.get("goal_checklist"), dict) else {}

    if "tool" in predicate and action.get("tool") != predicate["tool"]:
        return False
    if "tool_prefix" in predicate:
        prefix = predicate["tool_prefix"] if isinstance(predicate["tool_prefix"], str) else str(predicate["tool_prefix"])
        actual = action.get("tool") or ""
        if not isinstance(actual, str) or not actual.startswith(prefix):
            return False
    if "verdict" in predicate and plan_validation.get("verdict") != predicate["verdict"]:
        return False
    if "status" in predicate and checklist.get("overall") != predicate["status"]:
        return False
    if "session_id" in predicate and context.get("session_id") != predicate["session_id"]:
        return False
    if "ok" in predicate and bool(observation.get("ok")) != bool(predicate["ok"]):
        return False
    if "iteration_gte" in predicate:
        try:
            if int(context.get("iteration", -1)) < int(predicate["iteration_gte"]):
                return False
        except (TypeError, ValueError):
            return False

    expr = predicate.get("expr")
    if isinstance(expr, str) and expr:
        if not _eval_simple_expr(expr, context):
            return False

    return True


def select_applicable_hooks(
    items: Iterable[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Filter the configured hook descriptors by their `when` clauses."""
    return [item for item in items if matches_predicate(item.get("when"), context)]


def _eval_simple_expr(expr: str, context: Dict[str, Any]) -> bool:
    """Evaluate a tiny expression grammar for `when.expr`.

    Grammar: a comparison `<dot.path><op><literal>` joined by `and`/`or`.
    Operators are ==, !=, >=, <=, >, <. Literals can be int, float, bool,
    None, bare string, or quoted string. Each clause carries its own joiner
    (default `and`); when a clause starts with `and`/`or`, that keyword is
    used as the joiner with the previous clause. Fail-closed on errors.
    """
    try:
        clauses = [c.strip() for c in _split_clauses(expr)]
        if not clauses:
            return False
        results: List[Tuple[bool, str]] = []  # (value, joiner_before)
        default_joiner = "and"
        for clause in clauses:
            lower = clause.lower()
            if lower in {"and", "or"}:
                default_joiner = lower
                continue
            value, prefix = _eval_clause(clause, context)
            results.append((value, prefix or default_joiner))
        return _combine_pairs(results, default_joiner)
    except Exception:
        return False


def _split_clauses(expr: str) -> List[str]:
    # Split on top-level " and "/" or " while respecting quoted strings.
    out: List[str] = []
    buf: List[str] = []
    quote = None
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if expr[i:i + 5].lower() == " and ":
            out.append("".join(buf).strip())
            buf = [" and "]
            i += 5
            continue
        if expr[i:i + 4].lower() == " or ":
            out.append("".join(buf).strip())
            buf = [" or "]
            i += 4
            continue
        buf.append(ch)
        i += 1
    if buf:
        out.append("".join(buf).strip())
    return out


def _eval_clause(clause: str, context: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    clause = clause.strip()
    joiner = None
    lowered = clause.lower()
    if lowered.startswith("and "):
        joiner = "and"
        clause = clause[4:].strip()
    elif lowered.startswith("or "):
        joiner = "or"
        clause = clause[3:].strip()
    for op in (">=", "<=", "==", "!=", ">", "<"):
        if op in clause:
            left, right = clause.split(op, 1)
            left_val = _resolve_path(left.strip(), context)
            right_val = _parse_literal(right.strip())
            return _compare(left_val, op, right_val), joiner
    return False, joiner


def _combine_pairs(pairs: List[Tuple[bool, str]], default_joiner: str) -> bool:
    if not pairs:
        return False
    out = pairs[0][0]
    for value, joiner in pairs[1:]:
        # Use the joiner that precedes this clause (default_joiner if absent).
        effective = joiner or default_joiner
        if effective == "or":
            out = out or value
        else:
            out = out and value
    return out


def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op in {">", "<", ">=", "<="}:
            return {
                ">": lambda a, b: a > b,
                "<": lambda a, b: a < b,
                ">=": lambda a, b: a >= b,
                "<=": lambda a, b: a <= b,
            }[op](left, right)
    except TypeError:
        return False
    return False


def _resolve_path(path: str, context: Dict[str, Any]) -> Any:
    cur: Any = context
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _parse_literal(literal: str) -> Any:
    literal = literal.strip()
    if not literal:
        return ""
    if (literal[0] == literal[-1]) and literal[0] in {"'", '"'}:
        return literal[1:-1]
    lowered = literal.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "none" or lowered == "null":
        return None
    try:
        if "." in literal:
            return float(literal)
        return int(literal)
    except ValueError:
        return literal