"""Bootstrap the default skill packs into a project.

The seed packs (engine references, genre patterns) ship with the
package under ``agent/skill_packs/seeds/``. On a fresh project,
``bootstrap_default_packs`` copies them into the project's pack
directory so the agent has working knowledge available without
the user having to author any packs first.

The function is idempotent: existing packs are not overwritten.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from agent.skill_packs import (
    SCOPE_ENGINE,
    SCOPE_GENRE,
    SkillPack,
    SkillPackRegistry,
    SkillPackStorage,
)


DEFAULT_SEED_DIR = Path(__file__).resolve().parent / "seeds"


# Map seed file -> default (scope, capability). The YAML frontmatter
# in the file is the source of truth; these overrides are only used
# if the frontmatter is missing.
SEED_OVERRIDES: Dict[str, Dict[str, str]] = {
    "engine_urhox.md": {"scope": SCOPE_ENGINE, "capability": "balanced"},
    "engine_maker_mcp.md": {"scope": SCOPE_ENGINE, "capability": "balanced"},
    "genre_platformer.md": {"scope": SCOPE_GENRE, "capability": "balanced"},
    "genre_rpg.md": {"scope": SCOPE_GENRE, "capability": "deep"},
    "genre_puzzle.md": {"scope": SCOPE_GENRE, "capability": "balanced"},
}


def bootstrap_default_packs(
    project_root: Path,
    *,
    seed_dir: Path = DEFAULT_SEED_DIR,
    overwrite: bool = False,
) -> List[SkillPack]:
    """Copy seed packs into the project's pack directory. Returns
    the list of packs that were actually written (excludes
    already-present packs unless ``overwrite=True``)."""
    if not seed_dir.is_dir():
        return []
    storage = SkillPackStorage(project_root)
    written: List[SkillPack] = []
    for seed_path in sorted(seed_dir.glob("*.md")):
        try:
            text = seed_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        from agent.skill_packs import _parse_frontmatter
        meta, body = _parse_frontmatter(text)
        pack_id = str(meta.get("id") or seed_path.stem)
        scope = str(meta.get("scope") or SEED_OVERRIDES.get(seed_path.name, {}).get("scope", SCOPE_ENGINE))
        capability = str(meta.get("capability") or SEED_OVERRIDES.get(seed_path.name, {}).get("capability", "balanced"))
        name = str(meta.get("name") or pack_id)
        summary = str(meta.get("summary") or "")
        tags = list(meta.get("tags") or [])
        keywords = list(meta.get("keywords") or [])
        version = str(meta.get("version") or "1.0.0")
        # Skip if the file already exists at the target path.
        target = storage.pack_dir / scope / f"{pack_id}.md"
        if target.exists() and not overwrite:
            continue
        pack = SkillPack(
            pack_id=pack_id,
            name=name,
            scope=scope,
            summary=summary,
            capability=capability,
            tags=tags,
            keywords=keywords,
            version=version,
            body=body.strip(),
        )
        try:
            storage.write_pack(pack, overwrite=overwrite)
            written.append(pack)
        except Exception:
            continue
    return written


def get_or_create_registry(
    project_root: Path,
    *,
    seed_dir: Path = DEFAULT_SEED_DIR,
) -> SkillPackRegistry:
    """Bootstrap defaults if the project has no packs yet, then
    return a fresh registry over the project's pack directory."""
    storage = SkillPackStorage(project_root)
    if not list(storage.iter_pack_files()):
        bootstrap_default_packs(project_root, seed_dir=seed_dir)
    return SkillPackRegistry(storage)


__all__ = [
    "DEFAULT_SEED_DIR",
    "SEED_OVERRIDES",
    "bootstrap_default_packs",
    "get_or_create_registry",
]
