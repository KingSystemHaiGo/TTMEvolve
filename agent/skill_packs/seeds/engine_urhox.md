---
id: engine_urhox
name: UrhoX Engine Reference
scope: engine
summary: UrhoX Lua scripting essentials for game development on TapTap Maker.
capability: balanced
tags: [engine, urhox, lua, maker, scene, script, runtime]
keywords: [urhox, scene, node, component, script, lua, vector3, color, sprite, animation, taptap, maker, prefab, asset, resourcecache, urho3d, defs, attribute, event, subscribe, time, frame, update, fixedupdate, viewport, renderer]
version: 1.0.0
---

# UrhoX Engine Reference

This pack is the agent's working knowledge of the UrhoX engine as
exposed through TapTap Maker's Lua scripting API. It is **not** a full
engine manual — it captures the patterns the agent needs to know
when writing or reviewing a script.

## Scene graph

- A **scene** is a tree of **nodes**; every visible object is a node
  with one or more **components**.
- A node has `position`, `rotation`, `scale` (all `Vector3`). Use
  `node:SetPosition(vec3)` and friends; field assignment is not
  supported.
- Components live on nodes. Common ones: `StaticModel`, `AnimatedModel`,
  `Light`, `Camera`, `RigidBody`, `CollisionShape`, `SoundSource`,
  `ScriptObject`, `Sprite2D` / `StaticSprite2D`.
- To attach a component: `node:CreateComponent("ComponentName")` then
  configure fields. Components that need a model set its `model`
  resource cache handle, e.g. `staticModel.model = cache:GetResource("Model", "Models/Hero.mdl")`.

## ScriptObject

- One Lua file per ScriptObject component. The file's module table
  becomes the script's namespace.
- Lifecycle events the engine calls on the script:
  - `Start()` — once, after the scene loads
  - `Update(timeStep)` — every frame
  - `FixedUpdate(timeStep)` — fixed timestep
  - `Stop()` — once, before the scene unloads
  - `OnNodeSetEnabled(enabled)` — when the node's enabled state flips
- Subscribe to events with `self:SubscribeToEvent("EventName", handler)`.
  Handlers receive `eventType, eventData` where `eventData` is a
  Lua table reflecting the event payload.
- Use `self.node` to get the node the script is attached to.

## Subsystems

- `self.engine` — the engine singleton, useful for `engine:Exit()`,
  `engine:Update()` etc.
- `self.time` — frame time and elapsed time.
- `self.input` — mouse / keyboard / touch; `input:GetKeyDown(KEY_X)`.
- `self.resourceCache` — load models, textures, sounds.
- `self.renderer` — render targets and viewports.
- `self.scene` — the currently active scene.

## Resources and the cache

- Always load through the resource cache; never read files directly.
  - `cache:GetResource("Model", "Models/Boss.mdl")`
  - `cache:GetResource("Texture2D", "Textures/Boss.png")`
  - `cache:GetResource("Sound", "Sounds/Hit.ogg")`
- A missing resource returns `nil`. Always nil-check.

## Common pitfalls

- **Subscribing in Start without unsubscribing** leads to a duplicate
  handler after a scene reload. Use `self:UnsubscribeFromAllEvents()`
  in `Stop()` for scripts that may be re-attached.
- **Per-frame allocations** in `Update()` are an easy GC pressure
  source. Reuse tables and avoid `string.format` for hot-path logs.
- **Hard-coded paths** (e.g. `"Models/Hero.mdl"`) will silently break
  on platforms that mount resources differently. Use the `defs`
  convention (see the maker_mcp pack) or pass paths in.
- **Engine attribute writes** must use the typed setter
  (`SetPosition`, `SetRotation`), not the field name.
- **`Update` runs while the scene is paused** unless guarded with
  `self.paused` checks. For idle/incremental games, gate your tick.

## Recommended project layout

```
scripts/             # Lua script objects (one per file)
scenes/              # .scene files referencing the scripts
assets/sprites/      # PNG sprites
assets/audio/        # OGG / MP3 / WAV
assets/animations/   # AnimatedModel definitions
config/              # cjson-loaded configuration tables
defs/                # Path constants used across the project
```

## Where to look first

- For a new game object: write a `ScriptObject` Lua file in `scripts/`
  matching the object class. Do not edit the scene file directly.
- For a UI element: prefer the maker UI components documented in
  the maker_mcp pack. Touch coordinates are already converted.
- For a new resource: drop the file in `assets/...` and reference it
  through `defs/` so a project-wide rename does not require a
  grep-and-replace.

> Note: this pack summarises engine surface. The maker_mcp pack
> covers the project-management and asset-generation tools that
> sit on top of the engine.
