# ADR-0008: Plan v2 And Cybernetic Control Wiring

## 状态 / Status

Draft (Phase 0) — will move to Accepted after Phase D exit gate.

## 背景 / Context

`core/plan_format.py` is still at `plan-format.v1`. A plan is a list of `{id, tool, params, intent, expected_evidence, depends_on, status, notes}` steps. `Plan First` (`agent/plan_first.py`) drafts the plan, `core/plan_review.py` runs deterministic checks, and the approved plan is injected into ReAct context as `[approved_plan]` block. Execution is one ReAct iteration per step with the LLM choosing the action.

The current shape has three concrete limits:

1. **Dependencies are not enforced.** `depends_on` is normalized into the step shape but nothing in the runtime blocks a step until its dependencies are `done`. The LLM can pick any `pending` step on any iteration.
2. **No sub-plans, no branching, no loops.** The plan is a flat ordered list. Complex tasks that need a sub-task with its own sub-plan, or a branch on an observation, or a retry-until-condition loop, are not expressible.
3. **`ControlLoop` is observational.** `core/control_loop.py` produces `signal`/`verdict`/`recommendation` from the trajectory, but no runtime path reads those and changes behavior. `engineering_control` (`server/engineering_control.py`) and `project_control` consume `ControlLoop` only as data, not as a control input.

The upgrade must:

- preserve `plan-format.v1` parsing and the existing Plan First flow when `plan.v2_enabled=false`;
- make plans executable state machines with strict dependency enforcement, optional sub-plans, branch/loop steps;
- consume `ControlLoop.last_verdict()` (a new accessor) as a real control input;
- add a thin `VSMShell` adapter that **only** labels existing surfaces (`engineering_control`, `project_control`, Evidence Bundle) — it does **not** create a second control dashboard;
- gate every re-plan / rescue decision behind observable evidence (cooldown + threshold + flag).

## 决策 / Decision

Adopt plan v2 as a strict superset of v1, plus a VSM thin-adapter that wires `ControlLoop` into the runtime.

1. **Plan v2 schema** (`core/plan_format.py` bump `PLAN_FORMAT_VERSION = "plan-format.v2"`):
   ```json
   {
     "version": "plan-format.v2",
     "steps": [
       {
         "id": "step-1",
         "kind": "tool | sub_plan | branch | loop",
         "tool": "read_file",
         "params": {},
         "intent": "...",
         "expected_evidence": ["..."],
         "depends_on": [],
         "status": "pending",
         "vsm_layer": "S1",
         "control_signal": { "verdict": "stable", "recommendation": "..." }
       }
     ]
   }
   ```
   `kind` defaults to `"tool"`; `vsm_layer` defaults to `"S1"`. v1 plans auto-promote: every step gets `kind="tool"` and `vsm_layer="S1"`.
2. **New `core/plan_executor.py`** — a small scheduler that:
   - computes ready steps from dependency status (a step is ready iff every `depends_on` id is `done` or `skipped`);
   - marks `in_progress`, `done`, `failed`, `skipped` via the existing `plan_progress()` / `update_step_status()` helpers;
   - refuses cycles and unknown dependencies (reuses `core/plan_review._find_cycles`);
   - **does not duplicate** `ActionExecutionService` — it delegates tool execution to the existing ReAct/action path;
   - emits `plan_state` events so Workbench and Evidence Bundle can observe progress.
3. **New `core/condition_dsl.py`** — a safe condition evaluator with **no Python `eval`**:
   - allowed field roots: `goal_state.*`, `control_signal.*`, `observation.ok`, `observation.failure_type`, `plan_progress.*`;
   - allowed operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`;
   - raises `ConditionError` on unknown fields or operators.
4. **`ControlLoop` accessors.** Add `ControlLoop.last_signal()` and `ControlLoop.last_verdict()` accessors and emit a telemetry event on every `evaluate()` call so downstream surfaces can observe.
5. **New `core/vsm.py` — thin VSM adapter only:**
   | VSM label | TTMEvolve evidence |
   | --- | --- |
   | S1 Operations | current tool/action execution (`ActionExecutionService`) |
   | S2 Anti-oscillation | rescue cooldown and repeated-tool detection (`RescueTrigger`) |
   | S3 Audit | plan progress, budget, goal checklist |
   | S3* Exception | `ControlLoop.verdict == "diverging"` |
   | S4 Strategy | guarded re-plan or expert rescue |
   | S5 Policy | sandbox/profile/approval/runtime contract |
   The adapter feeds `engineering_control` and `project_control`. It **does not** create a second control dashboard.
6. **Wiring in `ReActLoop`.** Before each iteration the executor picks the next ready step. If the executor's `last_verdict()` is `"diverging"` and `vsm.auto_replan=true` and `vsm.replan_cooldown_steps` has elapsed, the adapter calls `PlanExecutor._replan(reason=...)` (which re-asks the LLM for a v2 plan and re-runs `review_plan`). If re-plan is disallowed, the adapter raises `RescueRequired` for the existing `RescueOrchestrator` to handle.
7. **Backward compatibility.** `plan.v2_enabled=false` keeps the flat execution path. v1 plans are auto-promoted at parse time. `condition_dsl.py` rejects unknown fields/operators loudly; it does not silently fall through.

## 后果 / Consequences

### Positive / 正面

- `depends_on` becomes a real, enforced dependency edge. The runtime cannot pick a step whose prerequisites are not `done`.
- Sub-plans (`kind="sub_plan"`) let a complex step recursively decompose into its own plan, with its own progress, sub-goals, and control signal. Depth is bounded by `plan.max_depth` (default 3).
- Branch/loop steps let a plan express conditional recovery and retry, which today is hand-rolled in the LLM prompt.
- `ControlLoop` becomes a **real** control input. The `verdict == "diverging"` signal is no longer observed-only; it is consumed by S3*/S4 to request a guarded re-plan or rescue.
- VSM labels map directly to existing surfaces (engineering_control, project_control, Evidence Bundle). The adapter is a naming layer, not a second dashboard.

### Negative / 负面

- Plan v2 is a schema bump. Old persisted plans (`storage/.../plan.json`) parse as v1 and auto-promote, but a unit test must prove the promotion is lossless.
- The condition DSL is a small new surface. A bug in the DSL could silently take the wrong branch. Mitigated by the strict allowlist and by tests that exercise every operator and every field root.
- Auto-replan can thrash if the cooldown is too short. Mitigated by `vsm.replan_cooldown_steps` (default 3) and `vsm.max_replan_depth` (default 1).
- The VSM adapter introduces a thin layer of indirection in the iteration loop. The cost is small (a method call and an event emit), but it is a new code path that needs its own tests.

### Compliance / 合规

- New tests: `tests/test_condition_dsl.py`, `tests/test_plan_executor.py`, `tests/test_vsm.py`, `tests/test_plan_review.py` (extended).
- v1 normalization must produce the same step shape as the existing `normalize_plan()` for the same input. This is verified by a side-by-side test.
- `ControlLoop.last_verdict()` must be observable from `engineering_control` and from the Evidence Bundle payload. Verified by a new test.
- A forced-divergence end-to-end test (`tests/test_cybernetics_endtoend.py`) drives a 5-step plan, forces a divergence on step 3, and asserts that VSM requests a re-plan (or rescue) only when the cooldown and flag allow.

## 替代方案 / Alternatives Considered

- **Replace Plan First with a learned policy.** Rejected — adds a training dependency we do not have. Plan v2 is an evolution of the LLM-drafted plan format, not a replacement.
- **Adopt LATS-style tree search.** Rejected — too expensive for the local LLM and out of scope for the current ReAct budget. We adopt only the static `branch` and `loop` shapes.
- **Make VSM a parallel control dashboard.** Rejected — would duplicate `engineering_control` and `project_control`. VSM is a naming layer, full stop.
- **Auto-replan on every divergence.** Rejected — thrashes the LLM. Mitigated by `vsm.replan_cooldown_steps` and `vsm.max_replan_depth`.

## References / 引用

See `docs/research/2026-memory-and-control.md` for the full source list. The directly relevant ones:

- [ADaPT paper](https://arxiv.org/abs/2311.05772) — recursive decomposition "only when needed"
- [LATS paper](https://arxiv.org/abs/2310.04406) — branching/alternative plan evaluation
- [PlanBench paper](https://arxiv.org/abs/2206.10498) — plan validation vocabulary
- [VSM Overview](https://viable-systems.github.io/vsm-docs/overview/what-is-vsm/) and [VSM Subsystems](https://viable-systems.github.io/vsm-docs/subsystems/) — S1–S5 mapping
- [RAG Survey on LLM-agent memory](https://arxiv.org/abs/2404.13501) — vocabulary for control signals
- [DSPy paper](https://arxiv.org/abs/2310.03714) — module shape for plan fragments (future optimization boundary)

## 退出条件 / Exit Gate (Phase D)

- `plan.v2_enabled=false` keeps all existing tests passing.
- v1-to-v2 normalization is lossless (verified by a side-by-side test).
- `ControlLoop.last_signal()` and `ControlLoop.last_verdict()` are exposed and observable.
- `condition_dsl.py` rejects unknown fields and operators with `ConditionError`.
- `PlanExecutor` enforces `depends_on` and refuses cycles / unknown deps.
- Auto-replan only fires when `vsm.auto_replan=true` AND cooldown AND `max_replan_depth` allow.
- Evidence Bundle reports `plan_v2.status`, `current_step`, `control_verdict`, and latest corrective action.
