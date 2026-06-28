"""
core/plan_executor.py - recursive plan executor with strict deps.

Phase D. Drives a plan-format v2 plan to completion. Does NOT execute
tools itself — the caller supplies a ``step_runner`` callback. The
executor is responsible for:

  - dependency enforcement (a step is only run after all its deps
    are ``done`` or ``skipped``)
  - branch / loop steps
  - sub-plan recursion (bounded by ``max_depth``)
  - refusing cycles and unknown dependencies
  - marking step statuses (``in_progress`` -> ``done`` / ``failed`` / ``skipped``)
  - emitting plan state events so Workbench and Evidence Bundle can
    observe progress

Design reference: ADR-0008 Section 4.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Set

from core.condition_dsl import eval_condition
from core.plan_format import (
    PLAN_FORMAT_VERSION,
    normalize_plan,
    plan_progress,
    update_step_status,
)


PLAN_EXECUTOR_VERSION = "plan-executor.v1"

DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_LOOP_ITERATIONS = 4


class PlanExecutorError(ValueError):
    """Raised when the executor refuses a plan (cycle, unknown dep,
    max depth overflow, etc.)."""


EmitFn = Callable[[str, str, Dict[str, Any]], None]
StepRunner = Callable[[Dict[str, Any], Dict[str, Any], int], Dict[str, Any]]
ConditionRunner = Callable[[str, Dict[str, Any]], bool]


class PlanExecutor:
    """Execute a plan-format v2 plan.

    Parameters
    ----------
    step_runner : callable
        ``step_runner(step, plan, depth) -> observation`` runs a single
        ``kind=="tool"`` step. The executor never calls tools itself;
        this keeps it free of side effects and test-friendly.
    condition_runner : callable, optional
        ``condition_runner(expr, context) -> bool`` evaluates the
        ``condition`` field of branch/loop steps. Defaults to
        ``core.condition_dsl.eval_condition``.
    config : dict, optional
        ``max_depth`` (int, default 3),
        ``max_loop_iterations`` (int, default 4).
    emit : callable, optional
        ``emit(session_id, event_name, payload)`` for observability.
    """

    def __init__(
        self,
        step_runner: StepRunner,
        condition_runner: Optional[ConditionRunner] = None,
        config: Optional[Dict[str, Any]] = None,
        emit: Optional[EmitFn] = None,
    ):
        if not callable(step_runner):
            raise ValueError("step_runner must be callable")
        self._step_runner = step_runner
        self._condition_runner = condition_runner or (
            lambda expr, ctx: eval_condition(expr, ctx)
        )
        cfg = dict(config or {})
        self.max_depth = int(cfg.get("max_depth", DEFAULT_MAX_DEPTH))
        self.max_loop_iterations = int(
            cfg.get("max_loop_iterations", DEFAULT_MAX_LOOP_ITERATIONS)
        )
        self._emit = emit

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute_plan(
        self,
        plan: Dict[str, Any],
        *,
        depth: int = 0,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a plan to completion. Returns ``{status, plan, counts}``."""
        if depth > self.max_depth:
            raise PlanExecutorError(
                f"max_depth ({self.max_depth}) exceeded at depth {depth}"
            )
        normalized = self._normalize_for_execution(plan)
        self._validate(normalized)
        # Recursive driver. We use a simple loop over the current plan;
        # sub-plan steps call back into ``execute_plan`` recursively.
        ctx = dict(context or {})
        last_observation: Optional[Dict[str, Any]] = None
        while True:
            ready = self._ready_steps(normalized)
            if not ready:
                # No more work to do. Check whether anything is still in
                # progress (a runner returned without marking the step)
                # or failed.
                progress = plan_progress(normalized)
                in_progress = [
                    s for s in normalized["steps"] if s.get("status") == "in_progress"
                ]
                for s in in_progress:
                    self._set_status(normalized, s["id"], "failed", note="runner did not finish")
                progress = plan_progress(normalized)
                if progress["counts"]["failed"] > 0:
                    return {
                        "status": "needs_recovery",
                        "plan": normalized,
                        "progress": progress,
                        "depth": depth,
                    }
                return {
                    "status": "completed" if progress["counts"]["pending"] == 0 else "completed",
                    "plan": normalized,
                    "progress": progress,
                    "depth": depth,
                }
            step = ready[0]
            ctx["observation"] = last_observation or ctx.get("observation") or {}
            observation, _next_plan = self._dispatch(step, normalized, depth, ctx)
            last_observation = observation
            if observation.get("ok") is False:
                # Mark this step failed. Subsequent steps that depend on
                # it will become unreachable, but the executor keeps
                # running so it can report the full progress.
                self._set_status(normalized, step["id"], "failed", note=str(observation.get("error") or ""))
                continue

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        step: Dict[str, Any],
        plan: Dict[str, Any],
        depth: int,
        context: Dict[str, Any],
    ) -> tuple:
        kind = step.get("kind", "tool")
        if kind == "tool":
            return self._dispatch_tool(step, plan, depth)
        if kind == "sub_plan":
            return self._dispatch_sub_plan(step, plan, depth)
        if kind == "branch":
            return self._dispatch_branch(step, plan, depth, context)
        if kind == "loop":
            return self._dispatch_loop(step, plan, depth, context)
        raise PlanExecutorError(f"unknown step kind: {kind!r}")

    def _dispatch_tool(self, step, plan, depth):
        self._set_status(plan, step["id"], "in_progress")
        self._emit_event(plan, "step_in_progress", {"step_id": step["id"], "kind": "tool", "depth": depth})
        observation = self._step_runner(step, plan, depth) or {}
        ok = observation.get("ok", True)
        next_status = "done" if ok is not False else "failed"
        self._set_status(plan, step["id"], next_status, note=str(observation.get("error") or ""))
        self._emit_event(plan, f"step_{next_status}", {"step_id": step["id"], "depth": depth})
        return observation, None

    def _dispatch_sub_plan(self, step, plan, depth):
        self._set_status(plan, step["id"], "in_progress")
        self._emit_event(plan, "step_in_progress", {"step_id": step["id"], "kind": "sub_plan", "depth": depth})
        sub = step.get("sub_plan")
        if not isinstance(sub, dict) or not sub.get("steps"):
            self._set_status(plan, step["id"], "skipped", note="empty sub_plan")
            return {"ok": True, "skipped": True}, None
        # Recurse. The depth check happens in execute_plan.
        sub_result = self.execute_plan(sub, depth=depth + 1)
        next_status = "done" if sub_result["status"] == "completed" else "failed"
        self._set_status(plan, step["id"], next_status, note=str(sub_result.get("status") or ""))
        self._emit_event(plan, f"step_{next_status}", {"step_id": step["id"], "depth": depth})
        return {"ok": next_status == "done", "sub_plan_status": sub_result["status"]}, None

    def _dispatch_branch(self, step, plan, depth, context):
        self._set_status(plan, step["id"], "in_progress")
        condition = step.get("condition")
        if not isinstance(condition, str) or not condition.strip():
            raise PlanExecutorError("branch step requires a non-empty condition")
        try:
            branch_taken = self._condition_runner(condition, context)
        except Exception as exc:
            self._set_status(plan, step["id"], "failed", note=f"condition error: {exc}")
            return {"ok": False, "error": str(exc)}, None
        chosen = step.get("then") if branch_taken else step.get("else")
        if not isinstance(chosen, dict):
            # Neither then nor else provided; mark as done with a stub
            # observation. The step itself "succeeded" (it picked a
            # branch — even if both branches were empty).
            self._set_status(plan, step["id"], "done", note=f"branch={'then' if branch_taken else 'else'} (empty)")
            return {"ok": True, "branch": "then" if branch_taken else "else"}, None
        # Run the chosen child step directly. We treat it as a single
        # tool step in the parent's coordinate system so its status
        # is visible in the plan progress view.
        self._emit_event(plan, "branch_taken", {
            "step_id": step["id"],
            "branch": "then" if branch_taken else "else",
            "depth": depth,
        })
        observation, _ = self._dispatch(chosen, plan, depth, context)
        next_status = "done" if observation.get("ok", True) is not False else "failed"
        self._set_status(plan, step["id"], next_status)
        return observation, None

    def _dispatch_loop(self, step, plan, depth, context):
        self._set_status(plan, step["id"], "in_progress")
        body = step.get("body")
        condition = step.get("condition")
        max_iter = int(step.get("max_iterations", 0) or self.max_loop_iterations)
        max_iter = min(max_iter, self.max_loop_iterations)
        if not isinstance(body, dict):
            self._set_status(plan, step["id"], "skipped", note="empty loop body")
            return {"ok": True, "iterations": 0}, None
        iterations = 0
        while iterations < max_iter:
            try:
                should_continue = self._condition_runner(condition or "", context) if condition else True
            except Exception as exc:
                self._set_status(plan, step["id"], "failed", note=f"condition error: {exc}")
                return {"ok": False, "error": str(exc)}, None
            if not should_continue:
                break
            observation, _ = self._dispatch(body, plan, depth, context)
            if observation.get("ok", True) is False:
                self._set_status(plan, step["id"], "failed", note="body failed")
                return observation, None
            iterations += 1
            context["observation"] = observation
        self._set_status(plan, step["id"], "done", note=f"iterations={iterations}")
        return {"ok": True, "iterations": iterations}, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ready_steps(self, plan):
        steps = plan.get("steps") or []
        out: List[Dict[str, Any]] = []
        for step in steps:
            if step.get("status") not in (None, "pending"):
                continue
            deps = step.get("depends_on") or []
            if all(
                self._dep_status(plan, dep) in {"done", "skipped"}
                for dep in deps
            ):
                out.append(step)
        return out

    def _dep_status(self, plan, dep_id):
        for s in plan.get("steps") or []:
            if s.get("id") == dep_id:
                return s.get("status") or "pending"
        return "missing"

    def _set_status(self, plan, step_id, status, *, note=""):
        # ``update_step_status`` is immutable — it returns a new plan with
        # the step marked. We must capture the return value or the caller's
        # plan never reflects the status change, which causes infinite
        # loops in ``_ready_steps``.
        new_plan = update_step_status(plan, step_id, status, note=note)
        plan.clear()
        plan.update(new_plan)
        self._emit_event(plan, "plan_progress", {"progress": plan_progress(plan)})

    def _emit_event(self, plan, name, payload):
        if not self._emit:
            return
        try:
            self._emit(str(plan.get("_session_id") or ""), name, payload)
        except Exception:
            return

    def _validate(self, plan):
        steps = plan.get("steps") or []
        # Cycle detection via DFS
        edges: Dict[str, List[str]] = {}
        ids: Set[str] = set()
        for s in steps:
            sid = str(s.get("id"))
            if not sid:
                raise PlanExecutorError("step missing id")
            if sid in ids:
                raise PlanExecutorError(f"duplicate step id: {sid}")
            ids.add(sid)
            edges[sid] = list(s.get("depends_on") or [])
        # Unknown dependencies
        for sid, deps in edges.items():
            for dep in deps:
                if dep not in ids:
                    raise PlanExecutorError(
                        f"step {sid!r} depends on unknown step {dep!r}"
                    )
        # Cycle detection (iterative DFS)
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {sid: WHITE for sid in ids}
        parent: Dict[str, Optional[str]] = {sid: None for sid in ids}
        for start in ids:
            if color[start] != WHITE:
                continue
            stack = [(start, iter(edges[start]))]
            color[start] = GRAY
            while stack:
                node, it = stack[-1]
                advanced = False
                for nxt in it:
                    if nxt not in color:
                        # Should not happen given unknown-dep check
                        continue
                    if color[nxt] == GRAY:
                        # Cycle: collect members
                        cycle = [nxt, node]
                        cur = node
                        while cur != nxt and parent[cur] is not None:
                            cur = parent[cur]
                            cycle.append(cur)
                        raise PlanExecutorError(
                            "dependency cycle: " + " -> ".join(reversed(cycle))
                        )
                    if color[nxt] == WHITE:
                        color[nxt] = GRAY
                        parent[nxt] = node
                        stack.append((nxt, iter(edges[nxt])))
                        advanced = True
                        break
                if not advanced:
                    color[node] = BLACK
                    stack.pop()

    def _normalize_for_execution(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a v1 plan into a v2 plan in-place shape.

        v1 plans (without ``kind``) become ``kind="tool"`` and
        ``vsm_layer="S1"``. v2 plans pass through. The function
        returns a deep copy so the caller's plan is not mutated.
        """
        if not isinstance(plan, dict):
            raise PlanExecutorError("plan must be a dict")
        copy = deepcopy(plan)
        copy["version"] = PLAN_FORMAT_VERSION
        normalized = normalize_plan(copy, task=str(copy.get("task") or ""))
        for step in normalized.get("steps") or []:
            if "kind" not in step:
                step["kind"] = "tool"
            if "vsm_layer" not in step:
                step["vsm_layer"] = "S1"
            if "depends_on" not in step:
                step["depends_on"] = []
        return normalized
