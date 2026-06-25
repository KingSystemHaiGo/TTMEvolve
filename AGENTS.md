# D:/CC/TTMEvolve - Core Memory

## Current Status
- Version: 0.4.5-one-click-practice-entry+gui-chat-readable
- Progress: Desktop Maker cockpit + Runtime Contract + external handoff + pullable diagnostics + async learning + Maker guard/advice + external LLM quickstart + Workbench surface selector + live session-scoped LLM probe/advice/metrics/learning evidence + one-click external-agent boot links + compact Evidence Bundle + pasteable Evidence Markdown + Runtime Readiness + API call proof + local LLM feedback summary + one-stop LLM Onboarding Bundle + Maker Setup Doctor + Maker Tool Audit + project directory switching + embedded auth flow preparation + chat-first GUI default + Portable Agent Root diagnostics + middle workspace sidebar for files/assets + page-like tools/settings surfaces + compact preview chrome + TapTap Maker forum entry + shell/BrowserView dark mode + readable chat layout + new/history conversation controls + splash-first startup gate
- Last Delivery: Replaced Provider/Model native selects with custom theme-aware pickers so the Settings page remains readable in dark mode on Windows/Electron.

## User Profile
- Name: 灰語, Assistant: 嗒啦啦
- Style: Casual friend, equal partner
- Prefers: Simple direct solutions, one-click setup, complete delivery
- Cares about: system design, continuous improvement, AI self-evolution

## Predicted Next Step
- Task: Open the GUI from the visible launcher, verify user messages are right bubbles, assistant output is full-width Markdown preview, tool steps are compact status rows, `新对话` resets the active chat, `历史` lists persisted sessions, and Maker preview remains active; then use GUI Maker Setup `Practice` for the next real Maker smoke task.
- Files: frontend/src/App.tsx, frontend/src/components/CockpitHeader.tsx, frontend/src/components/BrowserPreview.tsx, frontend/src/styles/index.css, electron/main/index.ts, docs/sessions/2026-06-24.md

## Recovery Protocol
1. Read AGENTS.md (this file)
2. Read docs/memory-index.md
3. Read docs/architecture/code-review-roadmap-2026-06-22.md
4. If present, read docs/persona.md and .Codex/memory/self.md

## Key Pitfalls
- Skipping POST = memory fracture. Always run POST after substantive delivery.
- Before real Maker development testing, read `GET /runtime/portable`. Portable state should live under `portable/` and `storage/`, and Windows user-dir leaks (`C:\Users\...`) are blockers.
- User-facing launch must be visible GUI launchers/shortcuts. Treat `.bat`/`.ps1` as backend/bootstrap details; do not ask the user to operate CLI unless debugging.
- Preferred GUI path is the Maker Setup strip `Practice` button. Maker CLI output, auth URL, app-index input, and cancel should stay inside GUI whenever possible.
- Default Maker game work should happen under `workspace/default-maker-project` or another selected project directory, not in the TTMEvolve app root.
- `maker_mcp.cwd` and all relative config paths are config-file-relative; do not reintroduce cwd-relative path assumptions.
- Maker auth must set official `TAPTAP_MAKER_HOME` and mirror `TTM_MAKER_HOME`; do not hard-code `Path.home()/.taptap-maker`.
- Normal GUI execution must not fall back to mock. Use a real API provider, explicit local GGUF, or fail clearly with UnconfiguredLLM.
- Runtime sessions create session-scoped `TapMakerAgent` instances; the base AppServer agent remains control-plane/IDE/shared-MCP owner.
- Frontend `AgentWorkbenchState` is the primary run-state model; raw SSE remains a debug timeline.
- ReAct should use ranked/capped tool subsets for think/action prompts; avoid reintroducing full tool-schema prompts.
- Tool validation failures must remain machine-readable for the LLM: include `failure_type=tool_validation`, `rule_id`, `path`, `reason`, `suggested_fix`, and `structured_errors` while keeping legacy `errors`.
- Three-layer architecture must be observable through `layer` events, not static UI copy.
- Agent chat/event transcript must show full content. Do not use fixed-size cards or hidden overflow for thoughts, tool calls, observations, or outputs.
- Main chat should contain user-readable conversation and essential tool actions only. Internal debug events such as candidate tool selection belong in Workbench/debug surfaces, not the transcript.
- Chat rendering rule: user instructions are right-aligned bubbles; assistant replies are full-width Markdown-rendered answer pages; runtime/tool events are compact status rows with details collapsed by default.
- Chat status controls belong inside the Agent chat panel as a slim top bar. Do not reintroduce absolute/floating `ready/history/collapse` mini cards over the empty chat area.
- File tree and asset library are workspace aids and should open as a middle column between Agent chat and Maker preview. Tool list and settings are page-like auxiliary surfaces, not passive status pills and not duplicate sidebars.
- Do not hide the native Maker BrowserView for normal auxiliary UI. Keep the preview active; solve layering by layout, not by blanking the preview.
- Electron startup should be splash-first: show a small progress window, wait for backend `/health`, then create/show the main GUI only after renderer readiness.
- Preview stage is a browser surface only. File preview belongs with the file tree/editor side, not the central Maker preview stage.
- Default preview chrome should stay compact: do not reintroduce a full-width browser URL toolbar unless the user explicitly asks for an address/debug mode.
- Dark mode is two-layered: React shell uses `data-theme`/`--tm-*` tokens, while native Maker BrowserView receives Electron CSS injection inspired by the local TapTap Maker darkmode extension.
- BrowserView theme must be bidirectional. Do not treat light mode as "remove dark CSS"; inject explicit light CSS too, because Maker pages can retain dark `prefers-color-scheme` or prior inline states.
- Maker BrowserView theme bugs can come from third-party page state, not only CSS. On shell theme changes, sync Maker page storage/classes/meta and reload the view so SPA startup code re-reads the desired mode.
- Avoid native `<select>` for important dark-mode controls on Windows/Electron. The OS popup can render white background with low-contrast text; use custom theme-aware pickers for provider/model/settings surfaces.
- Electron GUI preview uses native `BrowserView` through `electronAPI.makerBrowser`; Playwright browser service remains available for Agent/browser tools and web fallback, not the primary user preview.
- BrowserView bounds are based on `.native-browser-host`; ensure `.preview-content`, `.browser-preview`, and host stretch to full width/height or the native browser will appear as a narrow centered strip.
- Hide the code editor dock when no file is open; do not reserve a right rail beside the Maker browser stage unless there is an active editor context.
- API providers are not local models: `/health.runtime_kind=api`, `base_url`, `model`, `api_key_set`, and `last_call_stats.endpoint` are the evidence for whether MiniMax/OpenAI-compatible providers are actually being called.
- Use `/llm/probe` or the ProviderSelector Probe button before a full agent run when checking provider wiring; it uses a cloned config, one tiny request, and returns endpoint/tokens/latency/error without leaking API keys.
- Quickstart/Handoff/Runtime Advice now carry compact `llm_probe` evidence. If probe failed, advice priority becomes `llm_provider`; absence of a probe does not block Maker work.
- Probe diagnostics are now session-scoped when `session_id` is provided. Prefer `/sessions/{id}/llm-probe?steps=20` over global `/health.last_probe` for external agent handoff.
- ProviderSelector Probe now sends active `session_id` when available and remains usable while a run is active; config fields stay locked during the run.
- Active-session Probe emits `llm_probe` through `Session.emit`, so Workbench/SSE/persistence stay aligned instead of waiting for a later pull.
- `SessionStore.create_session()` deletes old events for the same session id before replacing metadata; fixed-id smoke sessions no longer inherit stale diagnostics.
- Workbench auto-refreshes Runtime Advice, Runtime Metrics, and Learning Status through `/sessions/{id}/evidence?steps=20` when available; direct detail endpoints remain manual drill-down paths.
- Workbench External Agent Boot copies a complete boot checklist for arbitrary LLMs: Quickstart, Handoff, Runtime Advice, Maker Briefing/Guard, Runtime Metrics, Learning Status, Context Sync, and Probe History.
- Prefer `/sessions/{id}/evidence?steps=20` as the first compact runtime evidence pull for arbitrary LLMs. It includes runtime_advice, maker_briefing, latest context, runtime metrics summary, learning latest, maker guard latest, compact LLM probe, counts, and endpoint map without raw histories.
- For LLMs that cannot access localhost, use `/sessions/{id}/evidence.md?steps=20` or Workbench `Copy Evidence` to paste the same compact evidence as Markdown.
- Evidence Bundle JSON/Markdown includes `layer_summary` for agent/runtime/learning latest state/event/route. Use it before raw SSE when diagnosing three-layer communication.
- Evidence Bundle JSON/Markdown includes `maker_mcp` readiness, connected, tool_count, top_tools, remote_identity, and last_call. Use it before `/mcp/tools` unless detailed Maker tool schemas are actually needed.
- Learned `styles.css` design language: brand `#00D9C5` / `#00CDBA`, app `#F7F9FA`, panel white, text `#060A26`, muted rgba text, 6/8/10/16px radius scale, thin scrollbars, and `rgba(0,217,197,0.16)` focus ring. Future frontend changes should use these tokens instead of inventing new palettes.
- Workbench panels should use semantic tokens such as `--tm-primary-border`, `--tm-primary-surface`, `--tm-info-soft`, `--tm-warning-soft`, `--tm-danger-border`, and `--tm-success-border`; do not add one-off Workbench colors for new diagnostics.
- Workbench error/debug text must wrap and show full content; avoid `max-height` / `overflow:hidden` on diagnostic text blocks.
- Stable checkpoint: `docs/releases/v0.4.2-onboarding-closure.md`. First external-agent endpoint is `GET /agent/onboarding?session_id=...&steps=20`; it wraps Runtime Readiness, Evidence Bundle, MakerMCP authority, layer summaries, runtime metrics, learning, API proof, token strategy, and closure gates.
- Runtime Readiness remains the no-network diagnostic gate. The Onboarding Bundle is the one-stop startup/closure packet and should be copied/pasted before raw SSE, full tool schemas, or detailed histories.
- Runtime Readiness can say `blocked`, `degraded`, or `ready`. Do not treat `degraded` as failure: MakerMCP disconnected or missing context sync can still allow local coding, but remote Maker authority is not proven.
- Use `llm_call_proof` to answer whether MiniMax/API was really called: MiniMax should observe `/text/chatcompletion_v2`; OpenAI-compatible providers should observe `/chat/completions`; Claude should observe `/messages`.
- Fresh external LLM self-feedback may be blocked because it sends private architecture to third-party APIs. When blocked, use `GET /llm/feedback-summary` and saved `docs/llm-feedback` artifacts instead of retrying around policy.
