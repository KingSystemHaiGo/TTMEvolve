"""Built-in knowledge seeds for agent and Maker-specialized behavior."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


KNOWLEDGE_SEED_VERSION = "knowledge-seeds.2026-06-25"


def default_knowledge_seeds() -> List[Dict[str, Any]]:
    """Return stable, source-attributed rules TTMEvolve should know on first run."""
    return [
        # ====== Maker MCP: 初始化與項目綁定 ======
        {
            "domain": "maker_mcp",
            "rule": "Before real Maker development, run portable diagnostics, Maker Setup Doctor, and Maker Tool Audit; degraded is usable only when the missing capability is explicit.",
            "context": "TTMEvolve runtime contract and field tests showed Maker auth, project binding, and tool exposure can fail independently.",
            "confidence": 0.95,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "diagnostics", "repair", "init"],
        },
        {
            "domain": "maker_mcp",
            "rule": "Official @taptap/maker remote proxy must see TAPTAP_MAKER_HOME; TTMEvolve should mirror the same path into TTM_MAKER_HOME for compatibility.",
            "context": "Field test: tools/list exposed only two tools until TAPTAP_MAKER_HOME was set; after the fix, creative tools became available.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "auth", "portable"],
        },
        {
            "domain": "maker_mcp",
            "rule": "A .maker-mcp/config.json with project_id 0 is not a bound Maker project; rerun Maker init/binding instead of reconnecting only.",
            "context": "Remote creative tools depend on a real bound project with .project/settings.json or a valid project id.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "project_binding", "init"],
        },
        {
            "domain": "maker_mcp",
            "rule": "MCP JSON-RPC success is transport success only; if tool payload has isError or structuredContent.success=false, classify it as remote business failure.",
            "context": "Creative tool calls can return remote 500 or async pending states through a successful JSON-RPC envelope.",
            "confidence": 0.95,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "tool_result", "verification"],
        },
        {
            "domain": "maker_mcp",
            "rule": "For Maker build/submit, use the Maker MCP build flow and reconcile remote state; do not substitute generic git push unless the Maker workflow explicitly requires it.",
            "context": "Maker remote build authority and generated .gitignore/project files belong to the Maker flow.",
            "confidence": 0.9,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "build", "remote_authority"],
        },
        # ====== Maker MCP: Guide 工作流知識 ======
        {
            "domain": "maker_mcp",
            "rule": "Maker Git workflow: use maker_build_current_directory for submit/push/build; do not create branches, task branches, PR/MR for Maker projects; .gitignore is a required Maker project file.",
            "context": "Official Maker MCP Guide: Maker remote only accepts main branch; maker_build_current_directory owns the safety gate before commit/push.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "git", "build", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "First Maker project clone can take 20+ seconds; transient 503/5xx errors are retried automatically; keep the CLI running during retries.",
            "context": "Official Maker MCP Guide: Maker server may be preparing the repository; the CLI retries transient HTTP 5xx/network/timeout errors automatically.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "clone", "init", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "For Maker init/clone/download, use `taptap-maker init` so CLI shows the app list for user choice; add `--create` only when user explicitly asks to create a new project.",
            "context": "Official Maker MCP Guide: Standard init shows app preview with '0. Create a new Maker project' row; --create is for explicit create-project intent only.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "init", "project", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "Push failure classification: remote_rejected needs pull/rebase; branch_not_allowed means Maker only accepts main (cherry-pick to main); forbidden_path requires removing paths from unpushed commit; auth needs PAT refresh.",
            "context": "Official Maker MCP Guide, push_recovery section: each failure type has a distinct recovery path; do not use generic git push as workaround.",
            "confidence": 0.97,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "push", "recovery", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "Remote sync check before editing: up_to_date -> continue; needs_pull+clean -> git pull --ff-only; needs_pull+dirty -> handle local edits first; diverged -> plan rebase/merge.",
            "context": "Official Maker MCP Guide: read Maker remote sync section from maker_status_lite before starting fresh editing sessions.",
            "confidence": 0.97,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "sync", "git", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "Use `taptap-maker upgrade --target-dir <PROJECT_DIR>` to upgrade Maker MCP; after upgrade restart/reconnect AI client MCP session; project-level MCP configs (.mcp.json, .codex/config.toml) may override global.",
            "context": "Official Maker MCP upgrade guide: upgrade refreshes MCP config, AGENTS.md policy block, cwd pinning; does not delete old config backups.",
            "confidence": 0.96,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "upgrade", "mcp_config", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "MCP tool registration cwd mismatch: if maker_status_lite reports MCP cwd != Maker project dir, explain that tools/list ran from the wrong cwd; start AI from project dir or update MCP config cwd.",
            "context": "Official Maker MCP Guide: passing target_dir to maker_status_lite proves the project is valid but does not dynamically add proxy tools to already-started MCP session.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "mcp_config", "cwd", "proxy_tools", "guide"],
        },
        {
            "domain": "maker_mcp",
            "rule": "Generated Maker assets: images in assets/image, audio in assets/audio, video in assets/video; 3D model outputs save original GLB/FBX + MDL zip under assets/model; MDL extracts to assets/Meshes, assets/Materials, assets/Textures, assets/Prefabs.",
            "context": "Official Maker MCP creative asset tool policy: Maker tools keep generated files inside the project with remote mappings for later editing.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "maker_mcp", "assets", "creative", "guide"],
        },
        # ====== UrhoX 引擎核心 ======
        {
            "domain": "urhox_engine",
            "rule": "UrhoX UI requires three mandatory steps: UI.Init(config), build widget tree with UI.WidgetName{props}, and UI.SetRoot(root). Forgetting SetRoot() is the most common bug.",
            "context": "Official UrhoX UI guide: unlike React/Vue, UrhoX has no implicit root mounting mechanism.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "ui", "lua", "engine"],
        },
        {
            "domain": "urhox_engine",
            "rule": "UrhoX Lua eventData access: use eventData[\"fieldName\"]:GetType() syntax; cannot use dot syntax eventData.fieldName; shorthand eventData:GetType(\"fieldName\") also valid.",
            "context": "Official UrhoX Lua scripting guide: eventData is a VariantMap C++ object bound through tolua++; dot access not supported.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "lua", "event", "gotcha"],
        },
        {
            "domain": "urhox_engine",
            "rule": "UrhoX NanoVG Lua API fully mirrors C API (same function names and parameters). NVGcontext* is an Object (nvgCreate(1) return), NOT an integer.",
            "context": "Official UrhoX Lua scripting guide: nvgBeginPath(vg), nvgRect(vg, x, y, w, h) etc all work the same as C API.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "nanovg", "lua", "engine"],
        },
        # ====== UrhoX 物理系統陷阱 ======
        {
            "domain": "urhox_engine",
            "rule": "Rolling Friction + Cylinder incompatible for coin-like flat cylinders; keep rollingFriction=0 and use angularDamping=0.3-0.5 instead.",
            "context": "Verified UrhoX physics gotcha: rollingFriction designed for wheel side rolling; coin edge contact has abnormal torque calculation causing tilt-lock or bounce.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "physics", "gotcha", "rolling_friction"],
        },
        {
            "domain": "urhox_engine",
            "rule": "Bullet default CollisionMargin (0.04m) is too large for small objects under 0.5m; use shape:SetMargin(0.01) for coins, tokens and similar.",
            "context": "Verified UrhoX physics gotcha: default margin for meter-scale objects; for 0.03m thick coin, default margin doubles collision thickness.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "physics", "gotcha", "collision_margin"],
        },
        {
            "domain": "urhox_engine",
            "rule": "3D character controller must use KinematicCharacterController + convex CollisionShape + CharacterComponent four-piece set; RigidBody + SetLinearVelocity causes wall-hanging.",
            "context": "Verified UrhoX physics gotcha (engine issue #1907): KCC without convex CollisionShape silently no-ops; CharacterComponent is required to sync physics ghost position back to node.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "physics", "gotcha", "character_controller"],
        },
        {
            "domain": "urhox_engine",
            "rule": "KCC four components (all required): RigidBody(collision events, LinearFactor=ZERO), CollisionShape(convex capsule), KinematicCharacterController(actual movement), CharacterComponent(syncs node position).",
            "context": "Verified UrhoX physics gotcha issue #1907: missing any of the four causes silent failure; order matters - create CollisionShape before KCC.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "physics", "gotcha", "kcc"],
        },
        {
            "domain": "urhox_engine",
            "rule": "KCC position is not readable from Lua: kcc.position returns nil, assigning it to node.position causes segfault (tolua++ nil property assignment). Always use CharacterComponent for position sync.",
            "context": "Verified UrhoX engine issue: Lua cannot read KCC internal position; GetPosition not bound; never bypass CharacterComponent.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "physics", "gotcha", "kcc_position"],
        },
        # ====== UrhoX 相機陷阱 ======
        {
            "domain": "urhox_engine",
            "rule": "Camera orthoSize represents full view height but engine internally uses orthoSize * 0.5; manual screen-world coordinate calculations must include the 0.5 factor.",
            "context": "Verified UrhoX camera gotcha: Camera.cpp line 960 uses 1/(orthoSize*0.5); screen-to-world transforms need 0.5 multiplier.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "camera", "gotcha", "ortho"],
        },
        {
            "domain": "urhox_engine",
            "rule": "Camera:GetScreenRay() computes from current camera state each call; no cache, no MarkDirty() needed after changing orthoSize.",
            "context": "Verified UrhoX camera gotcha: GetScreenRay is real-time; modify orthoSize then call GetScreenRay directly for correct results.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "camera", "gotcha", "getscreenray"],
        },
        # ====== UrhoX 節點系統 ======
        {
            "domain": "urhox_engine",
            "rule": "Node:SetEnabled(false) does NOT hide child render components; use node:SetDeepEnabled(false) to recursively disable the entire subtree.",
            "context": "Verified UrhoX gotcha: Component:IsEnabledEffective() only checks direct parent enabled state, not ancestor chain.",
            "confidence": 0.99,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "node", "gotcha", "enabled"],
        },
        # ====== UrhoX 遊戲開發最佳實踐 ======
        {
            "domain": "urhox_engine",
            "rule": "UrhoX engine module structure: Scene(CreateChild), Node(CreateComponent), Component properties set directly; resources loaded via cache:GetResource(\"XXX\", path).",
            "context": "UrhoX Lua API common patterns: use cache global for resource loading, node:CreateComponent for component creation, direct property access for settings.",
            "confidence": 0.95,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "common", "lua", "engine"],
        },
        {
            "domain": "urhox_engine",
            "rule": "UrhoX Cloud Score: GetRankList returns player field as number type; use tostring() for string operations. ClientCloud for client-side, ServerCloud for server-side cloud variables.",
            "context": "Verified UrhoX gotcha: AI commonly mistakes player field as string; it is number. Two distinct cloud APIs for client vs server.",
            "confidence": 0.97,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "cloud", "score", "gotcha"],
        },
        {
            "domain": "urhox_engine",
            "rule": "The UI system uses urhox-libs/UI (Yoga Flexbox + NanoVG, 40+ widgets); native Urho3D C++ UI components (UIElement, Button, Text) are deprecated.",
            "context": "Verified UrhoX engine documentation: UI system built on Yoga layout engine and NanoVG rendering; deprecated native UI for backward compatibility only.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "urhox", "ui", "yoga", "nanovg"],
        },
        # ====== Coding Agent 最佳實踐 ======
        {
            "domain": "coding_agent",
            "rule": "Use repository memory files as first-class operating context: AGENTS.md for Codex, CLAUDE.md for Claude Code, and project-local instructions before generic assumptions.",
            "context": "Codex and Claude Code both prioritize local instruction files for repo-specific behavior.",
            "confidence": 0.9,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "codex", "claude_code", "memory"],
        },
        {
            "domain": "coding_agent",
            "rule": "Expose compact onboarding, evidence, and context-sync packets instead of replaying full transcripts to external coding agents.",
            "context": "Codex/Claude-style handoffs work best when agents receive current plan, tool state, warnings, and acceptance gates.",
            "confidence": 0.9,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "handoff", "context_sync", "token_budget"],
        },
        {
            "domain": "coding_agent",
            "rule": "Prefer deterministic hooks and repair plans for recurring failures; let the LLM choose between classified actions, not rediscover the same fix from scratch.",
            "context": "Claude Code hooks and Codex automation patterns both favor explicit checkpoints around tool use and verification.",
            "confidence": 0.86,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "hooks", "repair", "agent_runtime"],
        },
        {
            "domain": "coding_agent",
            "rule": "Keep tools ranked and scoped to the task; full tool-schema prompts should be a debug path, not the normal action prompt.",
            "context": "TTMEvolve local/API performance data and modern coding agent designs both benefit from tool subset selection.",
            "confidence": 0.92,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "tool_ranking", "react", "codex"],
        },
        # ====== Coding Agent: Claude Code 模式 ======
        {
            "domain": "coding_agent",
            "rule": "Claude Code patterns to adopt: pre/post action hooks, session-level hooks, deterministic repair via hooks, /loop for recurring tasks, .claude/settings.json for agent config.",
            "context": "Analysis of Claude Code architecture: hooks provide deterministic checkpoints; loop command enables recurring task execution; settings.json controls agent permissions.",
            "confidence": 0.88,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "claude_code", "hooks", "patterns", "agent_runtime"],
        },
        {
            "domain": "coding_agent",
            "rule": "Codex patterns to adopt: AGENTS.md as dynamic tool source, subagent task spawning for parallelism, structured MCP service configuration, three-tier sandbox/approval.",
            "context": "Analysis of Codex/Cursor architecture: dynamic tools from AGENTS.md, subagents for parallel work, structured sandbox policies.",
            "confidence": 0.87,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "codex", "subagent", "patterns", "agent_runtime"],
        },
        {
            "domain": "coding_agent",
            "rule": "Skill generation should auto-trigger cross-ecosystem export after successful creation; write to skills/generated/ then sync to .claude/skills, .codex/skills, .hermes/skills.",
            "context": "Current gap: skill_generator writes to skills/generated/ but does not trigger SkillSyncRegistry.export_plan; generated skills remain isolated.",
            "confidence": 0.92,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "skill_sync", "export", "generation", "improvement"],
        },
        # ====== TapTap Maker 特殊領域 ======
        {
            "domain": "taptap_maker",
            "rule": "Treat creative asset generation as asynchronous and evidence-based: track task id, output path, business error, and retryability separately.",
            "context": "Maker image/music/video/3D tools can produce immediate files, task ids, or remote business failures.",
            "confidence": 0.9,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "assets", "async_tools"],
        },
        {
            "domain": "taptap_maker",
            "rule": "generated_image tool requires prompt, name, and target_size fields; batch_generate_images and edit_image currently return remote 500 errors (official limitation).",
            "context": "Real field test with bound Maker project and TAPTAP_MAKER_HOME set: generate_image succeeded; batch and edit returned remote business failures.",
            "confidence": 0.95,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "generate_image", "creative_tools", "field_test"],
        },
        {
            "domain": "taptap_maker",
            "rule": "text_to_music, create_video_task/query_video_task, create_3d_model_task/query_3d_model_task all verified working through official Maker MCP with bound project.",
            "context": "Real field test: music output MP3 at assets/audio, video task cgt-20260624..., 3D task UUID; all return verifiable outputs.",
            "confidence": 0.98,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "creative_tools", "field_test", "working"],
        },
        {
            "domain": "taptap_maker",
            "rule": "Maker project structure: .maker-mcp/config.json binds project; .project/settings.json contains engine/build config; scripts/main.lua is the Lua entry point.",
            "context": "Official Maker project documentation: .project/ contains i18n.json, project.json, resources.json; settings schema is project-wide config.",
            "confidence": 0.97,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "project", "structure"],
        },
        {
            "domain": "taptap_maker",
            "rule": "For Maker projects, developer should install taptap-maker-local, taptap-maker-dev-kit-guide, and update-taptap-mcp skills for proper workflow support.",
            "context": "Official Maker MCP bundled skills: taptap-maker-local covers Maker local workflow, dev-kit-guide explains AI dev-kit resources, update-taptap-mcp handles upgrades.",
            "confidence": 0.96,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "skills", "workflow", "guide"],
        },
        {
            "domain": "taptap_maker",
            "rule": "Prefer Maker MCP proxy tools over native AI image/video/audio tools for bound Maker projects; report full remote error payload when isError or remote failure occurs.",
            "context": "Official Maker MCP creative asset tool policy: Maker tools keep files inside project, record remote mappings; do not substitute client-native AI generation.",
            "confidence": 0.97,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "assets", "proxy_tools", "policy"],
        },
        {
            "domain": "taptap_maker",
            "rule": "Before calling edit_image, resolve the image to a local project path or CDN URL; search assets/image for partial name matches; never call edit_image without an image reference.",
            "context": "Official Maker MCP creative tool policy: dragged/attached images must be inspected and resolved to verifiable paths before edit_image calls.",
            "confidence": 0.96,
            "source_session": KNOWLEDGE_SEED_VERSION,
            "tags": ["seed", "taptap_maker", "edit_image", "assets", "policy"],
        },
    ]


def seed_knowledge_base(knowledge_base: Any, seeds: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Idempotently insert built-in knowledge seeds into a KnowledgeBase."""
    existing = {
        (str(item.get("source_session") or ""), str(item.get("rule") or ""))
        for item in knowledge_base.list_all()
    }
    stored_ids: List[str] = []
    skipped = 0
    for item in seeds or default_knowledge_seeds():
        key = (str(item.get("source_session") or ""), str(item.get("rule") or ""))
        if key in existing:
            skipped += 1
            continue
        stored_ids.append(knowledge_base.store(dict(item)))
        existing.add(key)
    return {
        "version": KNOWLEDGE_SEED_VERSION,
        "stored": len(stored_ids),
        "skipped": skipped,
        "stored_ids": stored_ids,
    }
