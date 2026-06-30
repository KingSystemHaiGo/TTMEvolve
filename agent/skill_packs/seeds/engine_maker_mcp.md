---
id: maker_mcp
name: TapTap Maker MCP Tools
scope: engine
summary: Project management, asset generation, and remote build tools exposed through Maker MCP.
capability: balanced
tags: [maker, mcp, taptap, asset, generation, publish, build, publish, project, state, identity, remote, sync, sprite, sfx, music, dialogue]
keywords: [maker, mcp, taptap, maker_build, maker_publish, maker_sync, maker_project, maker_status, generate_image, batch_generate_images, edit_image, text_to_sound_effect, batch_sound_effects, text_to_music, audition_voices_for_character, confirm_character_voice, text_to_dialogue, generate_game_material, publish_to_taptap, generate_test_qrcode, i18n_extract, project_select, project_list, scene_inspect, asset_catalog, project_state, remote_identity]
version: 1.0.0
---

# TapTap Maker MCP Tools

The Maker MCP integration is the agent's **authoritative channel**
to the Maker project on TapTap. The agent must prefer Maker MCP for
remote reads and writes; local file tools are for repository
inspection and code edits only.

## Three authority levels

The agent must use the right level for each action:

| Level | Use it for | Examples |
|---|---|---|
| `maker_mcp` | Remote project reads and writes | `maker.project_state`, `maker.scene_inspect`, `maker.asset_catalog` |
| `maker_mcp_authoritative` | Side effects on the Maker project | `maker.build`, `maker.publish`, `maker.sync` |
| `local_files` | Repository inspection and edits | `project.manifest`, `project.code_search`, `read_file`, `modify_file` |

When both surfaces can answer the same question, prefer `maker_mcp`
because the project is the source of truth — the local clone can
drift after a sync, partial restore, or a manual upload.

## Tool groups

### Project authority

- `maker.project_state` — returns the high-level project manifest
  (engine, scenes, scripts, asset categories, last build status).
- `maker.project_select` / `maker.project_list` — choose which
  Maker project the session is bound to. **Never call side-effecting
  tools before project_select**; the project identity is a
  precondition.
- `maker.scene_inspect` — describe a single scene: nodes, scripts,
  components, last preview screenshot.
- `maker.asset_catalog` — list assets by category, with style tags
  and license. Returns image thumbnails (multimodal).

### Asset generation

- `generate_image` — single sprite / icon / concept art.
- `batch_generate_images` — multiple sprites in one request; **one
  batch should not exceed four items** (failure rate climbs above
  that). Split large requests and verify with `ls` after each batch.
- `edit_image` — modify an existing image (palette swap, recolor).
- `text_to_sound_effect` / `batch_sound_effects` — short audio
  cues. Same per-batch limit applies.
- `text_to_music` — background music. Returns a job id; poll
  `query_music_task` until status is `succeeded` or `failed`.
- `audition_voices_for_character` / `confirm_character_voice` /
  `text_to_dialogue` — voice line pipeline. Always audition before
  confirming a voice.

### Build and publish

- `maker.build` — runs the project build. Returns status, return
  code, and a tail of stdout / stderr. **Treat a non-zero return
  code as a build failure even if the response has no error
  field.**
- `maker.sync` — pull the latest project state from Maker into the
  local clone. Should be run before reading `local_files` if the
  Maker project has been edited elsewhere.
- `maker.publish` — push the local clone to Maker and mark a
  release. **Side-effecting**, requires a human confirm in the
  default policy.
- `publish_to_taptap` — actually ship a build to the TapTap
  store. Use only after `maker.publish` has been confirmed.

### Marketing and ops

- `generate_game_material` — store copy, screenshots, promo.
- `generate_test_qrcode` — a scannable link to the latest build
  for QA.
- `i18n_extract` — pull translatable strings from Lua / cjson.

## Preconditions and identity

Most Maker MCP tools require:

- An **active project** (`maker.project_select` was called).
- A **remote identity** that is not partial. If `maker.project_state`
  reports `identity.status = "partial"`, do **not** make
  authoritative calls; treat the response as read-only.
- A **prepared Maker auth** if the build is going to publish to
  TapTap. `maker.auth_prepare` returns a URL; open it in a browser
  to confirm.

If any of these preconditions is missing, the runtime contract
warns and the tool call should be skipped (or, if necessary,
deferred until the user fixes the setup).

## Failure handling

- A `maker_mcp_authoritative` call that returns `ok: false` is a
  real failure. Do not retry blindly — the remote state may have
  changed. Re-read `maker.project_state` to reconcile.
- A `maker.build` that fails halfway is **not** safe to retry on
  the same code; check `maker.commit_history` and consider a
  reset.
- A `text_to_music` job that ends in `failed` is final; submit a
  new job with adjusted parameters.
