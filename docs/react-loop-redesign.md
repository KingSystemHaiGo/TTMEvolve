# ReAct Loop Redesign — Architecture Plan

> **Status:** Draft for review. No code change yet.
>
> **Date:** 2026-06-28
>
> **Trigger:** Operator experienced a hard-stuck loop on
> `project_status` (2026-06-28 16:09–16:11). The current rescue
> mechanism fires but does not unstick the agent. Root cause is a
> framework design assumption ("rescue succeeds") that does not
> hold with a 1B local model. This document proposes a 6-phase
> rebuild of the ReAct loop to a true engineering-cybernetics
> agent.

## Status / 状态

The TTMEvolve ReAct loop runs. The control loop, VSM, plan v2
executor, and runtime errors hook all exist. None of them
currently **drives** loop state — they all observe. The result
is a loop that can detect problems but cannot recover from them.

This plan proposes a 6-phase rebuild centered on three missing
properties:

1. **Structured thought chain** — the LLM no longer emits free
   text; it emits a structured plan_step / hypothesis /
   expected_outcome record that the control loop can score.
2. **Tool contracts** — every tool declares preconditions,
   postconditions, and current state. Stuck-tool detection
   uses the contract, not the action name.
3. **Real cybernetics** — VSMShell writes back to the loop
   state. Plan executor and homeostasis enforce invariants.
   The loop self-terminates when stuck, with a structured
   "I need help" payload to the operator.

All three are required. Doing only one is a partial fix that
will be undone by the next time the agent gets stuck.

## Problem diagnosis / 问题诊断

The hard-stuck trace from 2026-06-28 16:09–16:11:

```
16:10:39  User presses "项目状态"
16:11:00  ReActLoop iteration 1: project_status
16:11:07  ReActLoop iteration 2: project_status  ← same tool
16:11:16  ReActLoop iteration 3: project_status  ← same tool
16:11:16  rescue_trigger fires: reason="repeated_actions"
16:11:29  rescue_count = 0 → rescue_count = 1 (max hit)
16:11:29+ ReActLoop stays in "thinking", user must click 停止
```

Five distinct issues. Each maps to a layer that does not exist
or is wired but not used.

### Issue 1 — `think()` produces free text, not a state record
`agent/react_loop.py:566` calls `self.llm.think(...)` which
returns an opaque string. The control loop's `_error()` in
`core/control_loop.py:113` scores on tool failures and action
repeats, not on the LLM's reasoning quality. Result: the control
loop cannot tell good reasoning from bad.

### Issue 2 — `project_status` is a tool with no contract
`core/executor.py:330` defines `_project_status()` which always
returns `{"ok": True, ...}`. The agent has no way to know that
"this tool's result is stable but does not advance the task."
A tool contract — preconditions, postconditions, state — would
let the loop detect "this tool is being called but the world
state is not changing."

### Issue 3 — `rescue_trigger._repeated_actions` checks the wrong thing
`agent/rescue_trigger.py:112` checks that the last 3 actions
have the same `tool` name. It does NOT check whether the last
3 *results* are identical. So 3 calls to `project_status`
returning the same dictionary 3 times does not even register as
"stuck with no progress." It only registers as "same tool 3
times." A real stuck detector compares observations.

### Issue 4 — rescue触顶后没有 dead-man's switch
`agent/rescue_orchestrator.py:74` skips rescue when
`rescue_count >= max_rescue_per_session` (default 1). When
skipped, it re-runs the local ReActLoop with `on_step=None` so
no further rescue can fire. Result: the agent is on its own.
There is no condition under which the loop gives up and
emits a "I am stuck" message back to the operator.

### Issue 5 — preflight is advisory, not blocking
`core/executor.py:propose_action` does not check Maker MCP
readiness before running `project_status`. The system message
"Maker MCP 还没有完全就绪" is informational only. A block
at the executor level (returning `{"ok": False, "error":
"maker not ready"}`) would prevent the agent from running
tools that depend on Maker before the user fixes Maker.

## Target architecture / 目标架构

The target is a ReAct loop organized as Stafford Beer's Viable
System Model, with each subsystem owning its own
sense-compare-decide-act loop.

```
        S5 POLICY
           rules / sandbox / maker readiness
           hard-blocks at the executor
                |
                v
        S4 FORWARD PLANNING
           plan_first phase + re-plan on S3* verdict
           re-plan only when vsm.auto_replan=true AND
           cooldown elapsed AND depth limit
                |
                v
   S3 AUDIT  <- - - -  S3* EXCEPTION MONITOR
   plan_progress,    control loop: stable|drift|diverging
   budget,            re-plan or break-loop on
   goal checklist     persistent divergence
                |
                v
        S2 ANTI-OSCILLATION
           result-stability check (not action-repeat)
           tool blacklisting (result-stable tools
             get disabled_until_different)
           rescue cooldown
                |
                v
        S1 OPERATIONS
           tool execution with preconditions checked
           at the executor boundary
           postcondition recording
                |
                v
           ACT - - > OBSERVE - - > back to S3 / S3*
```

Three properties this gives us that the current loop does not have:

1. **Each layer can self-correct locally.** S2 can disable a
   tool without asking S4. S3* can request a re-plan without
   blocking S1.
2. **The operator can see the FSM state at any time** because
   every transition emits an event.
3. **The loop can self-terminate cleanly** because the
   dead-man's switch at S2 has a hard invariant: "no progress
   for N iterations → emit `vsm` critical + break."

The five issues above map to the missing pieces:

| Issue | Fixed by |
| --- | --- |
| 1. Free-text `think()` | R1 (structured thought chain) |
| 2. Tools without contracts | R2 (tool contract system) |
| 3. `repeated_actions` checks action, not result | R3 (homeostasis) |
| 4. Rescue触顶 no fallback | R3 (dead-man's switch) |
| 5. Maker preflight is advisory | R2 (preconditions in tool contract) |

## 6-phase roadmap / 6 阶段路线图

Each phase is independently shippable behind a feature flag
(default off), and each is gated by its own exit criteria.
A phase that fails its gate does not block subsequent phases.

### R1 — Structured thought chain protocol

Replace `LLM.think()`'s free-text output with a JSON record:

```json
{
  "plan_step": "step-3",
  "observation_summary": "project_status returned the same dict as before",
  "hypothesis": "this tool is not advancing the task",
  "expected_outcome": "a different tool will produce progress",
  "confidence": 0.42,
  "decision": "abandon project_status, list project files instead",
  "action": { "tool": "list_directory", "params": {} }
}
```

Backward compatibility: the LLM is asked to produce this
shape via a system-prompt contract. The wire format stays JSON
action; the difference is that the `thought` field now carries
the structured record. Old free-text responses are accepted
and parsed leniently.

**Exit gate:**
- 95% of the existing `test_react_loop_*` tests still pass with
  the new contract (lenient parse).
- A new `test_thought_chain_protocol.py` exercises the new
  contract end-to-end.
- A new evidence-bundle field `thought_chain` is populated by
  every iteration; `check_release_ready.py` adds a gate for
  it.

**File impact:**
- `llm/claude_llm.py`, `llm/local_llm.py`, `llm/openai_llm.py`,
  `llm/minimax_llm.py`, `llm/mock_llm.py` — add a
  `parse_thought_chain()` method on each.
- `core/control_loop.py` — `_error()` now reads
  `observation_summary` and `hypothesis` instead of
  `observation.ok` only.
- `llm/context_budget.py` — extend BudgetStats with a
  `thought_chain` field.
- `server/evidence_bundle.py` — new `thought_chain` block.
- `tests/test_regression_guards.py` — new entry for
  the feature flag.

**Estimated size:** ~150 lines, 1–2 days of work.

### R2 — Tool contract system

Every tool declares its contract:

```python
@dataclass
class ToolContract:
    name: str
    purpose: str                # one-line human purpose
    preconditions: List[str]   # e.g. ["maker_mcp_ready", "path_exists"]
    postconditions: List[str]  # e.g. ["returns_observation"]
    state: ToolState            # available | needs_config | unavailable | busy
    side_effects: bool
    risk_level: str
    expected_runtime_s: float
```

`Executor.propose_action` reads the tool's contract and:

- Rejects the call (returns `{"ok": False, "error": "..."}`) if
  any precondition is not satisfied. This is the **preflight
  block** that fixes Issue 5.
- Records the postconditions that fired, so the loop can
  reason about what changed.

`ToolRegistry.rank_tools` is rewritten to score on
`preconditions_satisfied * purpose_match * (1 - recent_failure_rate)`
instead of pure keyword match. This makes "I keep calling a
useless tool" score lower over time.

**Exit gate:**
- `core/executor.py` returns `{"ok": False, "error": "precondition not satisfied"}` when Maker is not ready and a Maker-dependent tool is called. A new test proves this.
- `agent/tool_registry.py::rank_tools` produces different scores when a tool has been recently marked "result-stable" (R3 prerequisite).
- Every existing tool in `core/executor.py` and
  `agent/builtin_tools.py` has an explicit `ToolContract`. A
  regression guard verifies this.
- `project_status` returns a non-trivial `postconditions_fired`
  so the agent can detect "this tool ran but nothing changed."

**File impact:**
- `core/executor.py` — `register_tool(contract, handler)`.
- `agent/tool_registry.py` — `rank_tools` rewrite.
- `agent/builtin_tools.py` — declarative contracts.
- `agent/agent.py` — `_register_maker_briefing_tool` adds
  contract.
- `tests/test_regression_guards.py` — every tool has a contract.

**Estimated size:** ~300 lines, 3–5 days of work.

### R3 — Loop homeostasis + dead-man's switch

A new module `core/loop_homeostasis.py` tracks invariants that
the current rescue system cannot:

- **Result stability:** the last 3 `observation` payloads for a
  given (tool, params) pair are byte-equal. → mark the tool
  result-stable.
- **No-progress:** plan_progress.overall has not advanced in
  N iterations, AND no tool fired a `postconditions_fired` event.
  → emit `homeostasis.no_progress` and request a forced
  re-decision.
- **Recovery failure:** rescue has been called `max_rescue_per_session`
  times and the loop is still in a non-terminal state. →
  break the loop with a structured "I am stuck" payload.

When a hard stuck state is detected, the loop:

1. Emits a `vsm` critical record via `error_hooks.fire` (R3 is
   downstream of the Phase L runtime errors hook).
2. Emits a `loop.stuck` event to the bus.
3. Sets `step["done"] = True` with `step["output"]` =
   `{"stuck": true, "reason": ..., "last_tool": ..., "last_observation": ...}`.
4. Returns a result the Workbench can render as a "I need your
   help" panel.

**Exit gate:**
- A test forces 3 calls to a tool returning the same observation
  and asserts the loop terminates with `stuck=True` after the
  3rd call (not after the 20th iteration).
- The 2026-06-28 trace (`project_status` 3x → rescue → infinite
  think) is replayed as a regression test and the agent
  terminates cleanly within 5 iterations.
- `error_hooks.fire("vsm", severity="critical")` is observed in
  the test's captured hooks.

**File impact:**
- `core/loop_homeostasis.py` (new).
- `agent/react_loop.py` — `execute_plan` and `_run_iteration`
  check the homeostasis state after each step.
- `agent/rescue_orchestrator.py` — when stuck is detected, skip
  rescue and return the stuck result.
- `tests/test_loop_homeostasis.py` (new).
- `tests/test_regression_guards.py` — new entry for
  `homeostasis.enabled=true` (a sub-flag of the runtime errors
  flag).

**Estimated size:** ~150 lines, 2–3 days of work.

### R4 — VSMShell as real control surface

Today, VSMShell (R3 of the v1.1.0 plan) is a thin adapter that
emits events. The events are observed but not acted on.

After R4, VSMShell can:

- **S2:** inject `disabled_until_different` into the trajectory
  so a stuck tool is excluded from `rank_tools` for the next K
  iterations.
- **S3*:** request a re-plan (calls into `plan_executor`'s re-plan
  path) when the control loop is persistently diverging.
- **S4:** surface a structured "suggest a different strategy"
  prompt to the operator via the evidence bundle.
- **S5:** enforce policy (sandbox / approval / maker readiness)
  at the boundary. The preflight check in R2 is the mechanism.

The actual "re-plan" and "different strategy" mechanisms are
reused from `core/plan_executor.py` and the existing
`RescueOrchestrator._apply_rescue`. The change is that VSMShell
is the **only** writer to those mechanisms; today, multiple
places can.

**Exit gate:**
- A test runs the 2026-06-28 stuck trace and verifies the loop
  terminates within 5 iterations, with a `loop.stuck` event,
  and a `vsm` critical record in the runtime errors log.
- The existing 11 regression guards still pass.
- `check_release_ready.py` adds a gate for
  `vsm.control_surface=true` (a new sub-flag) when this phase
  lands.

**File impact:**
- `core/vsm.py` — write methods.
- `agent/react_loop.py` — VSMShell calls are wired.
- `agent/rescue_orchestrator.py` — VSMShell owns the rescue
  decision.
- `tests/test_vsm.py` — extended for control-surface behavior.

**Estimated size:** ~400 lines, 5–7 days of work.

### R5 — Explicit sense-compare-decide-act FSM

The main loop becomes an explicit FSM with named states:

```
OBSERVE    - collect trajectory, observation, control loop verdict
ORIENT     - update self-model (plan_progress, tool_state, budget)
DECIDE     - choose next action (or stuck/dead-man/ask-user)
ACT        - execute the chosen action
REFLECT    - score the action's outcome, update homeostasis
```

Each state has:

- A timeout (failure to enter the next state in N seconds is
  itself a homeostasis event).
- A pre-emit hook (the state transition is observable).
- A sub-decision tree (the control loop is consulted in DECIDE).

The current `_run_iteration` becomes the OBSERVE+ORIENT+DECIDE
half. The current `_execute` becomes the ACT half. The current
record-and-append logic becomes the REFLECT half.

**Exit gate:**
- A new `test_loop_fsm.py` exercises every state transition
  including timeout and self-termination.
- The five issues from "Problem diagnosis" are all closed
  end-to-end.
- The current event-emission surface is preserved (the FSM
  emits the same events the Workbench already reads).
- A new `evidence_bundle.fsm` field exposes the current state
  to the Workbench.

**File impact:**
- `agent/react_loop.py` — major refactor. The class grows but
  the public API (`run()`) is unchanged.
- New file `agent/loop_fsm.py` for the state declarations.
- `core/control_loop.py` — consumed in DECIDE.
- `core/plan_executor.py` — re-plan triggered from DECIDE.

**Estimated size:** ~600 lines, 1–2 weeks of work.

### R6 — Homeostasis dashboard

Surface the new state to the operator:

- `evidence_bundle.fsm.current_state` (e.g. `"OBSERVE"`,
  `"DECIDE.blocked"`, `"stuck"`).
- `evidence_bundle.fsm.last_stuck_reason` (e.g. `"result_stable"`,
  `"max_rescue_exceeded"`).
- `evidence_bundle.fsm.tool_state` (per-tool: `available`,
  `disabled_until_different`, `unavailable`).
- `evidence_bundle.fsm.homeostasis_trend` (last 10 iterations'
  stuck score, rendered as a sparkline in the Workbench).

The dashboard is read-only. It is the operator's window into
"what is the agent doing right now and why is it stuck or not?"

**Exit gate:**
- The 4 fields above appear in the live evidence bundle.
- The Workbench renders them (out of scope for this slice but
  the data shape is locked).
- The current `runtime.errors` and `graph_recall` and
  `prompt_loader` evidence blocks are unchanged.

**File impact:**
- `server/evidence_bundle.py` — new `fsm` block.
- `agent/react_loop.py` — emits `fsm_state` events.
- `core/loop_homeostasis.py` — exposes the trend.

**Estimated size:** ~200 lines, 2–3 days of work.

## Non-goals / 不做的

These are explicit boundaries. Touching them would expand scope
without addressing the user's stated need.

- ❌ **LLM provider swap.** No change to MiniMax / OpenAI /
  Claude / local / mock selection. R1's contract goes into
  the existing `LLMInterface`.
- ❌ **Feature flag defaults.** `memory.graph.enabled`,
  `memory.bayes.enabled`, `loader.enabled`, `plan.v2_enabled`,
  `vsm.enabled`, `runtime.errors.enabled` all stay at `false`
  by default. New sub-flags (e.g. `homeostasis.enabled`)
  also default off.
- ❌ **Evidence bundle schema breaks.** New fields only. No
  existing field is renamed or removed.
- ❌ **Maker MCP rework.** The preflight block in R2 is the
  mechanism; the Maker setup page is unchanged.
- ❌ **Workbench UI changes.** The data is exposed; the UI
  work is a separate slice.
- ❌ **Tauri / React / launcher changes.** Out of scope.
- ❌ **New third-party dependencies.** No langchain / pydantic-ai
  / DSPy. Plain Python dataclasses.
- ❌ **v2.0.0 release cut.** Slice stays at v1.x with a clear
  `v1.2.0` (or `v1.1.1`) tag once R3 lands.
- ❌ **Real GUI smoke.** Not part of this slice.

## Exit gates per phase / 退出门槛

Every phase lands behind a feature flag (default off). Each
phase has a gate that must pass before the flag can be flipped
in production. The gates accumulate: R1's gate plus R2's
gate plus ... must all pass for the cumulative feature to be
on.

| Phase | Gate | Test |
| --- | --- | --- |
| R1 | thought_chain contract is non-breaking | `test_thought_chain_protocol.py` |
| R2 | every tool has a contract | `test_regression_guards.py::test_all_tools_have_contracts` |
| R3 | the 2026-06-28 trace terminates within 5 iterations | `test_loop_homeostasis.py::test_stuck_terminate` |
| R4 | VSMShell writes affect runtime state | `test_vsm.py::test_vsm_can_break_loop` |
| R5 | FSM transitions are observable | `test_loop_fsm.py::test_every_state_has_emit` |
| R6 | evidence bundle exposes fsm block | `test_smoke_evidence_new_fields.py::test_fsm_block_present` |

A new check is added to `scripts/check_release_ready.py` for
each landed phase.

## File impact summary / 文件影响汇总

| File | R1 | R2 | R3 | R4 | R5 | R6 |
| --- | :-: | :-: | :-: | :-: | :-: | :-: |
| `agent/react_loop.py` | M | M | M | M | **R** | M |
| `agent/loop_fsm.py` (new) |  |  |  |  | **N** |  |
| `core/loop_homeostasis.py` (new) |  |  | **N** |  |  |  |
| `core/vsm.py` |  |  |  | M |  |  |
| `core/control_loop.py` | M |  |  |  | M |  |
| `core/plan_executor.py` |  |  |  | M | M |  |
| `core/executor.py` |  | **M** |  |  |  |  |
| `agent/tool_registry.py` |  | **M** |  |  |  |  |
| `agent/builtin_tools.py` |  | **M** |  |  |  |  |
| `agent/rescue_orchestrator.py` |  |  | M | M |  |  |
| `llm/claude_llm.py` + 4 siblings | **M** |  |  |  |  |  |
| `llm/context_budget.py` | M |  |  |  |  |  |
| `server/evidence_bundle.py` | M |  |  |  |  | M |
| `server/rag_evidence_service.py` |  |  |  |  |  |  |
| `tests/test_regression_guards.py` | M | M | M | M | M | M |
| `scripts/check_release_ready.py` | M | M | M | M | M | M |

Legend: **N** = new, **R** = rewrite, **M** = modify. Empty
means no change in that phase.

Total estimated size across all six phases: ~1 800 lines of
production code and ~1 200 lines of test code. Roughly 4–6
weeks of focused work.

## Recommended order / 建议执行顺序

```
R3 (dead-man's switch)  ← smallest, fixes today's pain
       |
       v
R1 (thought chain)       ← enables R5's structured scoring
       |
       v
R2 (tool contracts)      ← enables R3's result-stability detection
       |
       v
R4 (VSM control)         ← makes the existing pieces actually do work
       |
       v
R5 (explicit FSM)        ← structural rewrite
       |
       v
R6 (dashboard surface)   ← read-only evidence
```

R3 first because it directly fixes the issue you just saw, is
the smallest change (~150 lines), and the lowest risk. R1
before R5 because the FSM needs structured reasoning to score.
R2 before R3's full power because the result-stability check
needs tool contracts.

## Open questions for review / 待你确认的开放问题

These are decisions that affect the plan and need an answer
before any phase lands. Mark each with your decision; I will
update this document accordingly.

### Q1 — Should R1's structured thought chain be mandatory or optional?
Mandatory means the local model is retrained / prompted to
produce the contract; some prompts may degrade. Optional means
the contract is asked-for but lenient-parsed. **My
recommendation: optional with a feature flag.** The contract is
enforced only when `thought_chain.strict=true`.

### Q2 — Where should the tool contract live?
Two options: in `core/executor.py` (next to the handler) or
in a new `agent/tool_contracts.py`. **My recommendation: new
file.** Keeps `executor.py` from growing another 200 lines and
makes the contract declarations reviewable independently.

### Q3 — Should R3's dead-man's switch hard-terminate or ask the user?
Hard-terminate means the loop sets `done=True` with
`output={"stuck": true, "reason": "..."}` and the operator
sees the message. Ask-the-user means the loop pauses and
emits a `awaiting_user_input` event. **My recommendation:
hard-terminate first.** The runtime errors hook (Phase L) makes
this observable. Ask-the-user is a R5 / R6 follow-up.

### Q4 — Should R4's VSMShell write-actions go through a policy gate?
R4 lets VSMShell re-plan, disable tools, and break the loop.
Without a policy gate, a bug in VSMShell could disable every
tool. **My recommendation: yes, gate at S5.** The current
`approval.policy` is the right surface; a new
`vsm.policy="cautious"` default would require operator
confirmation for any VSMShell write.

### Q5 — Backward compatibility for v1.1.0 / v1.1.1 deployment?
The v1.1.0 features (graph, bayes, loader, plan v2, VSM) stay
on with `enabled=false` by default. R3 lands in v1.1.1, R1 in
v1.1.2, etc. **My recommendation: yes, version each phase.**
This keeps `check_release_ready.py` clean and the rollout
auditable.

### Q6 — Naming for the new sub-flags?
Proposed:
- `homeostasis.enabled` (R3)
- `thought_chain.strict` (R1)
- `vsm.control_surface` (R4)
- `loop.fsm_enabled` (R5)
- `dashboard.fsm` (R6)

**My recommendation:** approve as listed. The naming
convention `<area>.<feature>` matches the existing
`memory.graph.enabled` etc.

## Appendix — trace replay test (sketch)

A regression test that replays the 2026-06-28 trace and
verifies the agent terminates cleanly. The test is added in
R3 and extended in R4 / R5.

```python
def test_2026_06_28_stuck_trace_terminates_cleanly(tmp_path):
    """The exact trace from the 2026-06-28 incident.

    Three calls to a tool returning the same observation must
    trigger the dead-man's switch within 5 iterations.
    """
    # Set up a session with project_status returning the same
    # dict on every call.
    # ... (test setup)
    for i in range(3):
        agent.step(...)
    result = agent.run(...)
    assert result["done"] is True
    assert result["output"]["stuck"] is True
    assert result["output"]["last_tool"] == "project_status"
    # Runtime errors log captured the vsm critical event
    critical = [r for r in runtime_errors.recent() if r.severity == "critical"]
    assert any("vsm" in r.category for r in critical)
```

## Reviewer checklist / Reviewer Checklist

For each "approve" / "request changes" item below, leave a
note.

- [ ] Q1 mandatory vs optional thought chain
- [ ] Q2 contract location
- [ ] Q3 hard-terminate vs ask-user
- [ ] Q4 VSMShell policy gate
- [ ] Q5 phase-versioned rollout
- [ ] Q6 sub-flag naming
- [ ] R3 first (dead-man's switch)
- [ ] Total size (~1 800 + 1 200 lines) is acceptable
- [ ] Non-goals list is complete
- [ ] Exit gates per phase are sufficient

When all items are addressed, the next step is to land R3
behind `homeostasis.enabled` and run the trace-replay test.
