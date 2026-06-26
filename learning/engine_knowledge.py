"""Engine knowledge seeds — UrhoX Lua engine subsystems.

Compact reference rules for the five most-used subsystems in Maker projects:
physics, audio, input, network, and graphics. The agent quotes these in
plan reviews when a tool call targets one of these subsystems.

Each rule is one or two sentences. Keep them short — long prose does not
fit cheaply into a ReAct prompt.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_KNOWLEDGE_VERSION = "engine-knowledge.v1"


PHYSICS_RULES: List[Dict[str, Any]] = [
    {
        "id": "physics.collision_layer",
        "subsystem": "physics",
        "rule": "Use collision layer constants (LAYER_STATIC=1, LAYER_PLAYER=2, LAYER_ENEMY=4) so collisions can be filtered with bitwise AND.",
        "severity": "gotcha",
    },
    {
        "id": "physics.fixed_timestep",
        "subsystem": "physics",
        "rule": "Always integrate physics in the engine's fixed timestep (default 1/60). Using variable delta breaks determinism and causes tunneling.",
        "severity": "gotcha",
    },
    {
        "id": "physics.rigidbody_sleep",
        "subsystem": "physics",
        "rule": "Static colliders should have rigidbody disabled; letting them sleep saves CPU in idle scenes.",
        "severity": "best_practice",
    },
    {
        "id": "physics.raycast_filter",
        "subsystem": "physics",
        "rule": "Raycast queries must pass a collision mask, otherwise they hit everything (including invisible triggers).",
        "severity": "gotcha",
    },
]


AUDIO_RULES: List[Dict[str, Any]] = [
    {
        "id": "audio.bgm_loop",
        "subsystem": "audio",
        "rule": "BGM files must be set as looping via the engine resource cache; otherwise the music ends abruptly after one play.",
        "severity": "gotcha",
    },
    {
        "id": "audio.sfx_pool",
        "subsystem": "audio",
        "rule": "Sound effects should be loaded from a small pool (8-16 channels). Heavy SFX without pooling will starve the audio bus.",
        "severity": "best_practice",
    },
    {
        "id": "audio.spatial_falloff",
        "subsystem": "audio",
        "rule": "Spatial 3D sounds need both a source node and a listener; forgetting the listener silently kills the audio.",
        "severity": "gotcha",
    },
]


INPUT_RULES: List[Dict[str, Any]] = [
    {
        "id": "input.touch_priority",
        "subsystem": "input",
        "rule": "Touch input handlers must check UI overlays first; otherwise a tap on a HUD button also triggers gameplay.",
        "severity": "gotcha",
    },
    {
        "id": "input.keyboard_repeat",
        "subsystem": "input",
        "rule": "Keyboard key events fire on press and repeat — gate actions on edge detection unless continuous motion is intended.",
        "severity": "gotcha",
    },
    {
        "id": "input.gamepad_axis_deadzone",
        "subsystem": "input",
        "rule": "Gamepad axes need a small deadzone (~0.15) or controllers drift on idle.",
        "severity": "best_practice",
    },
]


NETWORK_RULES: List[Dict[str, Any]] = [
    {
        "id": "network.reconnect",
        "subsystem": "network",
        "rule": "Network clients must implement exponential backoff (1s → 2s → 4s, cap 30s). Linear reconnect storms the server.",
        "severity": "gotcha",
    },
    {
        "id": "network.message_id",
        "subsystem": "network",
        "rule": "Tag every outbound message with a sequence id so late packets can be detected and dropped.",
        "severity": "best_practice",
    },
    {
        "id": "network.authoritative_server",
        "subsystem": "network",
        "rule": "Server is authoritative for gameplay state; client-side prediction must be reconciled every tick.",
        "severity": "gotcha",
    },
]


GRAPHICS_RULES: List[Dict[str, Any]] = [
    {
        "id": "graphics.batching",
        "subsystem": "graphics",
        "rule": "Group draw calls by material to allow the renderer to batch; otherwise each sprite costs its own draw call.",
        "severity": "best_practice",
    },
    {
        "id": "graphics.z_order",
        "subsystem": "graphics",
        "rule": "Use explicit Z-order values rather than relying on draw order; later objects can pop in front unexpectedly.",
        "severity": "gotcha",
    },
    {
        "id": "graphics.texture_atlas",
        "subsystem": "graphics",
        "rule": "Small textures should live in one atlas; per-sprite textures blow up the draw call count.",
        "severity": "best_practice",
    },
    {
        "id": "graphics.viewport_resize",
        "subsystem": "graphics",
        "rule": "Listen for viewport resize events and update the camera aspect ratio, otherwise the scene stretches on rotation.",
        "severity": "gotcha",
    },
]


ALL_RULES: List[Dict[str, Any]] = (
    PHYSICS_RULES
    + AUDIO_RULES
    + INPUT_RULES
    + NETWORK_RULES
    + GRAPHICS_RULES
)


def all_rules() -> List[Dict[str, Any]]:
    return list(ALL_RULES)


def rules_for_subsystem(subsystem: str) -> List[Dict[str, Any]]:
    return [rule for rule in ALL_RULES if rule.get("subsystem") == subsystem]


def search_rules(query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Deterministic keyword search across engine rule text.

    Uses word-boundary regex on ASCII tokens and substring matching on CJK
    tokens (since CJK has no whitespace boundaries).
    """
    import re
    lowered = (query or "").lower().strip()
    if not lowered:
        return []
    scored: List[Dict[str, Any]] = []
    for rule in ALL_RULES:
        text = (rule.get("rule") or "").lower()
        score = _keyword_score(text, lowered)
        if score > 0:
            scored.append({"rule": rule, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return [item["rule"] for item in scored[:limit]]


def _keyword_score(text: str, lowered_query: str) -> float:
    """Word-boundary-aware keyword score.

    ASCII tokens are matched with re.search(rf"\\b{re.escape(word)}\\b").
    CJK tokens are matched as substring since CJK has no word boundary.
    """
    import re
    score = 0.0
    for word in lowered_query.split():
        if not word:
            continue
        # CJK token: substring match.
        if any("一" <= ch <= "鿿" for ch in word) or any(0x3400 <= ord(ch) <= 0x4DBF for ch in word):
            if word in text:
                score += 1.0
            continue
        # ASCII token: word-boundary match.
        if re.search(rf"\b{re.escape(word)}\b", text):
            score += 1.0
    return score


def render_subsystem_card(subsystem: str) -> str:
    """Render the rules for one subsystem as a UI card."""
    rules = rules_for_subsystem(subsystem)
    if not rules:
        return ""
    lines = [f"# {subsystem} 规则", ""]
    for rule in rules:
        severity_tag = "⚠" if rule.get("severity") == "gotcha" else "✓"
        lines.append(f"- {severity_tag} **{rule['id']}** — {rule['rule']}")
    return "\n".join(lines)


def render_all_cards() -> str:
    sections = [render_subsystem_card(name) for name in ("physics", "audio", "input", "network", "graphics")]
    return "\n\n".join(sections)