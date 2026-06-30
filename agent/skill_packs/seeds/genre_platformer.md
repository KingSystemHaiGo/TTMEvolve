---
id: genre_platformer
name: Platformer Genre Patterns
scope: genre
summary: Patterns and gotchas for side-scrolling and top-down platformers on UrhoX.
capability: balanced
tags: [genre, platformer, side-scroller, jump, physics, coyote, input, controller, level, level-design, level-design, checkpoint, mobile]
keywords: [platformer, jump, double-jump, coyote-time, jump-buffer, wall-jump, dash, hitbox, hurtbox, checkpoint, respawn, gravity, friction, acceleration, max-speed, deceleration, ground-detection, raycast, input, controller, on-screen, joystick, button, level, segment, level-design, level-design, mobile]
version: 1.0.0
---

# Platformer Genre Patterns

Working knowledge for platformer games on UrhoX. Covers the
"feels-good" details that are easy to miss and the level-design
conventions that readers expect.

## The "feel" stack

- **Coyote time** — the player can still jump for a short window
  (typically 6 to 10 frames at 60 fps) after walking off a ledge.
  Without it, jumps that feel "right" to the player's fingers read
  as "the game ate my input".
- **Jump buffer** — if the player presses jump slightly before
  landing, the jump fires the moment they touch ground (typically
  a 6-frame window). Same rationale.
- **Variable jump height** — releasing the jump button mid-air
  cuts upward velocity. Without it, every jump is the same height
  and the game feels stiff.
- **Air control** — small lateral acceleration while in the air
  so the player can adjust their arc. Don't add too much or the
  platforming turns into flying.
- **Acceleration / deceleration curves** — instant direction
  changes feel robotic. A short ramp (around 8-12 frames) on
  acceleration and a longer one on deceleration feels "weighty"
  without sluggish.

## Physics conventions

- A separate `RigidBody` per character; kinematic or dynamic
  depending on whether you want full physics or arcade feel.
- Ground detection: **a downward raycast or a small overlap**
  from the character's feet. Sweep tests with capsule colliders
  also work but cost more per frame.
- Hitboxes: the **hurtbox** and the **hitbox** are different
  rectangles. A common bug is to reuse the visual sprite as the
  hurtbox, which makes small characters unfairly easy to hit.

## Level structure

- A level is a sequence of **segments** with a defined entry and
  exit. Segments can be reused across levels.
- **Checkpoints** are mandatory in any level longer than ~90
  seconds of play. Without them, a single death costs the player
  the entire run.
- A level's first 10 seconds should be **safe and teach one
  mechanic**. Difficulty ramps after that.
- **Mobile platforms** that move on a fixed curve are a great
  teaching tool; they let the player learn timing without
  punishing failure.

## Mobile-specific

- **Touch controls** need a virtual joystick + a jump button.
  Position the jump button on the right thumb side; the
  joystick on the left.
- **Screen-edge dead zones** for landscape mode — the system
  reserves the top-right area for the maker runtime, so do not
  place interactive elements there.
- **Battery-friendly frame budget**: target 30 fps minimum on
  the lowest-end supported device. Reduce particle count or
  shadow resolution before reducing game logic fidelity.

## State machine for a player character

```
SPAWN -> IDLE -> RUN -> JUMP -> FALL -> LAND -> IDLE
            |                    ^
            +-> HURT (knockback, invuln frames) -> IDLE
            +-> DEAD (respawn at checkpoint)
```

Transitions should be **single-source** (one place decides the
next state). Splitting logic across `Update()` and event
handlers is a frequent source of stuck states.

## Asset checklist for a new platformer

- Player sprite (idle, run, jump, fall, hurt, each as a separate
  frame or animation)
- One or more enemy types with the same animation set
- A jump / land / hurt sound effect (short, punchy)
- A background music track (per biome)
- One tile-set per visual theme
- A "game over" / "level complete" UI
