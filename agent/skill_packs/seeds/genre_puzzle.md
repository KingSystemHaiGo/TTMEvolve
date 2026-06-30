---
id: genre_puzzle
name: Puzzle Genre Patterns
scope: genre
summary: Patterns and pitfalls for puzzle and match-3 games on UrhoX.
capability: balanced
tags: [genre, puzzle, match-3, logic, board, grid, hint, undo, level, design, designer-tools, level-editor]
keywords: [puzzle, match-3, match-three, grid, board, cell, tile, swap, chain, combo, hint, undo, redo, move-limit, level, designer-tools, level-editor, generator, validator, solvable, unique-solution, difficulty, ramp, tutorial, first-fail, retry]
version: 1.0.0
---

# Puzzle Genre Patterns

Working knowledge for puzzle games (match-3, sokoban, swipe
puzzles, "merge" games) on UrhoX. Puzzles look simple and are
actually the most subtle genre to balance because every level is
hand-authored and every change ripples through difficulty.

## The two layers

A puzzle game has **two completely separate codebases**:

1. **The game runtime** — the actual playing experience. Players
   tap, the board responds, score updates, levels advance.
2. **The level author / generator** — tooling the designer uses
   to create new levels and verify they are solvable and
   appropriately difficult.

Keep them in separate folders (`game/` and `editor/`, or
`runtime/` and `designer/`). Most "the level is broken" bugs
come from sharing code between the two.

## Board representation

- The board is a **dense array** of cell records, indexed by
  `(col, row)`. Avoid sparse structures during play — they
  cost more in cache misses than they save in memory.
- A cell record is small and **value-typed** (a Lua table is
  fine, but avoid the temptation to subclass it for every
  cell type). Most cells are "empty" with a few "filled" ones
  during play.
- Define the board as a **pure function** `(seed, level) ->
  cells` so the same level always produces the same board.
  Players notice when the same level gives a different result.

## Move model

- A move is a **transaction** with three phases: `input`,
  `validate`, `apply`. Validate **before** apply; never mutate
  state until the move is legal.
- An **undo** is a transaction in reverse. The cleanest
  implementation is to keep a small ring buffer of board states
  and pop them on undo. Do not invent "inverse moves" — they
  drift from the actual game logic.
- **Redo** should survive a "new move" only if you do not want
  a branching history. The default behaviour is: new move
  clears the redo stack. Players learn this convention.

## Hint and tutorial

- The first failure is **free**. Show the player what to do
  rather than punish the mistake. After that, the hint budget
  should decay (or be paid for).
- A hint is **never** a free move. It shows the player a
  recommended action but still costs a turn.
- Tutorials should be **embedded in the level**, not a
  separate "tutorial level". A level whose first 5 moves
  introduce one mechanic is much easier to maintain than a
  separate scripted walkthrough.

## Level design

- Every level must be **validated for solvability** at author
  time. The "I generated a level that the player cannot win"
  bug is the single most damaging failure mode.
- Difficulty should ramp **gradually**. A useful heuristic: a
  player who beats level N should beat level N+1 with the same
  strategy 70% of the time. Tune until that holds.
- A level's first 3 moves should be **forced** for the player
  — there is one good move and the others are clearly worse.
  This is the "teaching moment".

## Designer tools

- The level editor should be the **same app** as the game,
  launched with a flag. Two separate apps drift in
  capabilities within a week.
- Provide a **seeded random** for the level generator so the
  designer can reproduce a specific bad level for debugging.
- Provide a **solver** that the editor can run on each level
  to verify solvability and report difficulty.

## Asset checklist for a new puzzle game

- A tile set (8 to 16 tile types is a common range)
- A "match" sound effect (short, satisfying, no clipping)
- A "swap" sound effect
- A "level complete" jingle
- A "level failed" jingle
- Particle effects for match events (optional, but doubles
  the satisfaction of a match)
- UI icons for hint, undo, pause
