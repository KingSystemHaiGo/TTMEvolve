# Release Gates — Slice #1

This document is the source of truth for "is this slice #1 ready to
release?" Each gate is a single check the runtime must satisfy, with
a pointer to the test or script that proves it. The
`scripts/check_release_ready.py` script runs every gate in one go and
prints a `READY` / `BLOCKED` verdict.

## Gates

| # | Gate | Evidence | What it protects |
| --- | --- | --- | --- |
| G1 | All five new feature flags default to `false` | `tests/test_regression_guards.py::test_feature_flags_default_off` | We do not accidentally ship unverified behaviour to production. |
| G2 | `release_readiness --mode source-checkpoint` returns `status=ready, blockers=[]` | `scripts/check_release_ready.py` runs it and asserts the boundary | The source checkpoint is the only "ready" claim we make; we are explicit when it's not full-offline. |
| G3 | `production_rag_quality` remains `unproven` | `tests/test_regression_guards.py::test_production_rag_quality_unproven` | We do not over-claim semantic quality from a deterministic fake-FAISS benchmark. |
| G4 | LLM provider adapters are not modified | `tests/test_regression_guards.py::test_llm_provider_files_unchanged` (verifies that the four provider modules import without error and expose the expected public surface) | The "No provider churn" principle from ADR-0007 is preserved. |
| G5 | `plan-format.v1` plans still parse and execute | `tests/test_regression_guards.py::test_plan_v1_backward_compat` | v1 plans remain valid; the v2 schema is strictly additive. |
| G6 | New evidence fields are wired into the live bundle | `tests/test_smoke_evidence_new_fields.py` (3 tests) | The Workbench can read `graph_recall / prompt_loader / plan_v2 / control_loop` from `/sessions/{id}/evidence-bundle`. |
| G7 | All-flags-on integration works end-to-end | `tests/test_integration_all_flags_on.py` | The five surfaces compose correctly when the flags are on. |
| G8 | Cross-surface scenarios | `tests/test_integration_scenarios.py` (4 tests) | Profile filtering, plan v2 sub_plan, failure recovery, cycle detection all integrate. |
| G9 | The 14 baseline tests pass | `tests/test_rag_performance.py` + `tests/test_runtime_contract.py` | The original RAG/runtime contract is intact. |
| G10 | The full memory subsystem regression passes | `tests/test_memory_manager.py` + `tests/test_cold_memory_vector.py` + `tests/test_vector_index.py` + `tests/test_shared_memory_policy.py` | No module in the memory subsystem was broken by the slice #1 changes. |

## How to run

```bash
.venv\Scripts\python.exe scripts/check_release_ready.py
```

The script prints each gate's pass/fail and ends with a final
`READY` / `BLOCKED` line.

## When a gate fails

1. The script tells you which gate failed.
2. Look at the linked test / command output.
3. Fix the underlying issue, **do not silence the gate**.
4. Re-run until `READY`.
5. Commit the fix with the same commit message convention used
   elsewhere: `fix(<area>): <what>`.

## What "ready to release" means

A slice is releasable when:

- Every gate G1-G10 is `pass`.
- The candidate source zip (`scripts/package_release.py`) builds
  cleanly and `release_readiness --mode source-checkpoint` returns
  `status=ready` against it.
- `docs/memory-health.md` carries a `POST` entry with
  `Status: verified.` for the current slice.
- A new `release-artifacts/TTMEvolve-source-vX.Y.Z.zip` exists with
  the matching `manifest.json`.

At that point the slice can be promoted from
`docs/research/baseline/candidate-vX.Y.Z.md` to a real release.
Promotion is the production cut-over (changing
`scripts/release_readiness.py`'s `DEFAULT_PACKAGE`); do not
back-date a release into a previous version's zip.

## Out of scope (do NOT add to gates)

- Visual GUI smoke: requires a real Tauri/Electron runtime. Run as a
  separate task when the environment supports it; do not block
  release on it.
- Maker remote build smoke: requires a Maker MCP account; same.
- Signed installer: requires a code-signing certificate; same.

These three are kept as `unproven` in `release_readiness` and that
is correct: they belong to the next release, not this one.
