---
id: genre_rpg
name: RPG Genre Patterns
scope: genre
summary: Patterns and pitfalls for turn-based and action RPGs on UrhoX.
capability: deep
tags: [genre, rpg, turn-based, action, stats, inventory, quest, dialogue, save, load, level, progression, balance, balancing]
keywords: [rpg, turn-based, action-rpg, stats, str, dex, int, vit, hp, mp, inventory, equipment, weapon, armor, quest, dialogue, npc, party, level, experience, xp, skill, ability, talent, save, load, slot, balance, balancing, economy, shop, vendor, crafting, loot, drop-rate, drop-table, proc, on-hit, on-kill, aggro, threat, taunt, formation, line-up, line-up, encounter, random-encounter, dialog-tree, dialog-branch, branching-dialog, localization, l10n, i18n]
version: 1.0.0
---

# RPG Genre Patterns

Working knowledge for RPGs (turn-based and action) on UrhoX. The
biggest RPG pitfalls are around state explosion, save corruption,
and balance drift — this pack is biased toward those.

## Core state

- A single `gameState` table holds the player's progress. Treat
  it as **append-and-snapshot** rather than overwrite-in-place.
- Save format should be **versioned**: an integer `saveVersion`
  field lets the loader migrate older saves when the schema
  changes. Players keep saves for years.
- Save the **smallest possible** derived state. Re-derive stats
  from base + equipment + buffs at load time; never persist
  derived values that can drift from their inputs.

## Stats and progression

- A stat is a function of three things: **base**, **modifiers**,
  and **derived**. Always compute the displayed value as a sum or
  pipeline of those three layers, not as a hard-coded number.
- Level-up should be **deterministic**: given the same XP curve
  and the same quest outcomes, two characters reach the same
  level. Do not inject random bonuses.
- Equipment slots are **fixed** in the schema; do not let new
  content introduce new slots without a migration step.

## Combat

- A turn is a **transaction** with at least three states:
  `selecting`, `resolving`, `animating`. A common bug is to let
  the player issue the next command while a previous one is
  still animating; the result is overlapping actions.
- Aggro / threat is a **number**, not a "is this enemy targeting
  me" boolean. Numbers let you implement taunt, off-tank, and
  threat decay in a consistent way.
- Damage formulas are the **single most edited piece of code** in
  an RPG. Keep them in one place (a `combat.lua` module) and
  expose a `calcDamage(attacker, defender, ability)` function the
  rest of the game calls. Resist the urge to inline damage
  math at call sites.

## Quest and dialogue

- A quest is a **state machine** with a small number of states
  (`available`, `active`, `completed`, `failed`). Branching is
  handled by **multiple quest instances** rather than by
  in-place state mutation.
- Dialogue trees should be **data, not code**. A JSON or cjson
  tree is much easier to author and translate than nested Lua
  if/else.
- Localize dialogue as part of authoring; do not retrofit. The
  `i18n_extract` tool pulls every string in the tree.

## Inventory and economy

- Inventory size is a **cap**, not a goal. Players should hit
  the cap at predictable intervals; hitting it at random is
  frustrating.
- Item rarity should be **cosmetic + functional**. Cosmetic
  rarity drives desire; functional rarity (drop rate, stat
  budget) drives the meta. Tune them independently.
- A vendor or shop is a **sink**, not a source. If the shop
  generates more currency than it removes, the economy
  inflates and the late game becomes trivial.

## Save / load pitfalls

- Saving during a turn transition is the most common source of
  corrupted saves. Save only at **stable checkpoints** (between
  turns, between scenes, at the end of a dialogue).
- Save size matters. A 1 MB save every 30 seconds fills the
  device quickly. Compress with `zlib` if your saves exceed
  200 KB; profile before and after.
- **Cloud sync** is a separate layer from local save. Treat the
  local save as the source of truth; the cloud is a copy.
  Reconciling two divergent local saves is its own problem and
  should be a deliberate UX choice (e.g. "which one is
  newer?").

## Asset checklist for a new RPG

- Player sprite + 4 to 6 enemy archetypes
- 3 to 5 environment backgrounds per biome
- Combat sound effects (hit, miss, crit, ability activation)
- A short theme track per biome
- A "level up" jingle
- UI icons for each item category and status effect
- At least one save indicator (icon or text) on the HUD
