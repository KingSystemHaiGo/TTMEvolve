# Release Candidate: TTMEvolve-source-v1.0.0

**Date:** 2026-06-28
**Artifact:** `release-artifacts/TTMEvolve-source-v1.0.0.zip`
**Manifest:** `release-artifacts/TTMEvolve-source-v1.0.0.zip.manifest.json`

## Provenance

Built from the working tree immediately after commit
`5f6f490 feat(memory+plan): graph RAG, Bayesian scoring, progressive loader, plan v2 + VSM`.

The candidate bundles the new opt-in memory/control features behind
feature flags. **It is not the current production release.**

## Current production

`release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip`
(386 files, 0.9 MB, sha256 030157c55a3c9006...) is the current
production artifact. `scripts/release_readiness.py` defaults to this
zip; do not change that default until v1.0.0 is promoted.

## Verification

| Gate | Status |
| --- | --- |
| `tests/test_rag_performance.py` + `test_runtime_contract.py` | 14 passed in 1.16s |
| Focused memory/control suite (15 test files) | 134 passed |
| Wide backend regression (excluding pre-existing flaky RAG budget check) | 83 passed |
| `release_readiness --mode source-checkpoint` (against v0.4.5) | `status=ready, blockers=[], production_rag_quality=unproven` |
| VSMShell auto-construction via `from_config(cfg)` | verified |
| New tests covering VSMShell wiring in ReActLoop | 4 passed |

## Boundaries (preserved)

- `memory.graph.enabled` / `memory.bayes.enabled` / `loader.enabled` /
  `plan.v2_enabled` / `vsm.enabled` all default to `false`.
- `production_rag_quality` remains `unproven` until
  `/memory/rag-quality` passes with a real labelled corpus and
  production embedding artifact.
- LLM provider adapters are not modified.
- VSM is a thin naming layer over existing control surfaces.

## Promotion path

1. Replace `DEFAULT_PACKAGE` in `scripts/release_readiness.py` to
   point at `TTMEvolve-source-v1.0.0.zip`.
2. Re-run `release_readiness --mode source-checkpoint` to confirm
   the v1.0.0 zip passes the source package gate.
3. After a real-lab GUI smoke pass (out of scope of this slice),
   promote the v1.0.0 zip to production.

## SHA-256

```
a3f7fe260560b7f2... (first 16 hex)
```

See `release-artifacts/TTMEvolve-source-v1.0.0.zip.manifest.json`
for the full hash and the file-by-file listing.
