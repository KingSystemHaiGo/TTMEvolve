"""Project-side skill pack system (Q3 of the multimodal roadmap).

Skill packs are markdown documents with a small YAML frontmatter that
live inside the project so the agent can recall them when working on a
task. They are the *project-side* equivalent of the AI's own private
memory file: shared with everyone (multi-agent, multi-session),
version-controlled with the code, and readable through the same
``project.*`` introspection tools the agent already uses.

The system supports three roles out of the box:

- ``engine`` — engine + framework specifics (UrhoX, Maker MCP)
- ``genre`` — game-genre patterns (platformer, RPG, puzzle)
- ``project`` — project-specific notes (this game's design, art
  direction, level layout)

New packs can be authored by the PM agent or by hand and live in
``docs/skill_packs/`` by default. ``SkillPackRegistry`` scans the
directory at startup and exposes ``read``, ``search``, and ``recall``
helpers. ``recall`` is the keyword-based lookup the GoalLoop
UNDERSTAND stage uses to pull the right packs into a goal's context.

Design rules:
- No model names baked in. The pack metadata names a *capability*
  (``fast`` / ``balanced`` / ``deep``) that the agent config maps to
  an actual provider.
- No code-line thresholds. Pack scopes are sized by *boundary*
  (engine / genre / project), not by file size.
- All content is plain markdown so humans and the AI can both edit
  the same file.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SKILL_PACK_VERSION = "skill-pack.v1"
SKILL_PACK_DEFAULT_DIR = "docs/skill_packs"

# Capability hints. These are *roles*, not model names. The agent
# config maps each role to an actual provider.
CAPABILITY_FAST = "fast"
CAPABILITY_BALANCED = "balanced"
CAPABILITY_DEEP = "deep"
KNOWN_CAPABILITIES = {CAPABILITY_FAST, CAPABILITY_BALANCED, CAPABILITY_DEEP}

# Pack scopes. The three roles the agent cares about.
SCOPE_ENGINE = "engine"
SCOPE_GENRE = "genre"
SCOPE_PROJECT = "project"
KNOWN_SCOPES = {SCOPE_ENGINE, SCOPE_GENRE, SCOPE_PROJECT}


@dataclass
class SkillPack:
    """One skill pack.

    A pack is a markdown document with a small YAML frontmatter. The
    body is the *content* the agent can recall into context. The
    metadata drives indexing, capability hints, and search ranking.
    """

    pack_id: str
    name: str
    scope: str
    summary: str
    capability: str = CAPABILITY_BALANCED
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    rel_path: str = ""
    content: str = ""
    body: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "name": self.name,
            "scope": self.scope,
            "summary": self.summary,
            "capability": self.capability,
            "tags": list(self.tags),
            "keywords": list(self.keywords),
            "version": self.version,
            "rel_path": self.rel_path,
            "char_count": len(self.content),
        }


@dataclass
class PackRecall:
    """One search hit returned by ``SkillPackRegistry.recall``."""

    pack: SkillPack
    score: float
    matched_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack": self.pack.to_dict(),
            "score": round(self.score, 3),
            "matched_keywords": list(self.matched_keywords),
        }


class SkillPackError(RuntimeError):
    """Raised when a pack cannot be read or its frontmatter is invalid."""


# ---------------------------------------------------------------------------
# Frontmatter parsing. Deliberately tiny: a pack author writes
# `--- key: value` lines and an optional `tags: [a, b]` list. Anything
# else is treated as plain body.
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Return ``(metadata, body)``. Empty metadata is OK if the file
    has no frontmatter at all."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}, text
    raw_meta = match.group("meta")
    body = match.group("body")
    meta: Dict[str, Any] = {}
    current_list_key: Optional[str] = None
    for raw_line in raw_meta.splitlines():
        line = raw_line.rstrip()
        if not line:
            current_list_key = None
            continue
        if line.startswith("  - ") and current_list_key is not None:
            meta.setdefault(current_list_key, []).append(line[4:].strip())
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                # A bare key with no value is the start of a list.
                current_list_key = key
                meta.setdefault(key, [])
                continue
            current_list_key = None
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                meta[key] = [
                    item.strip().strip("\"'")
                    for item in inner.split(",")
                    if item.strip()
                ] if inner else []
            else:
                meta[key] = value.strip("\"'")
    return meta, body


# ---------------------------------------------------------------------------
# Storage. File-based, scoped under ``docs/skill_packs/`` by default.
# Each pack is one ``.md`` file. A sidecar SQLite index gives fast
# keyword search; if the index is missing or unreadable, the registry
# falls back to a pure-Python scan.
# ---------------------------------------------------------------------------


class SkillPackStorage:
    """File-based pack storage with an optional SQLite index."""

    def __init__(self, project_root: Path, *, pack_dir: Optional[Path] = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.pack_dir = (
            Path(pack_dir).resolve() if pack_dir else (self.project_root / SKILL_PACK_DEFAULT_DIR)
        )
        self.pack_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.pack_dir / ".skill_pack_index.sqlite3"

    def iter_pack_files(self) -> List[Path]:
        return sorted(
            path for path in self.pack_dir.rglob("*.md")
            if path.is_file() and not path.name.startswith(".")
        )

    def safe_pack_path(self, rel_path: str) -> Optional[Path]:
        raw = str(rel_path or "").replace("\\", "/").lstrip("/")
        if ".." in Path(raw).parts:
            return None
        target = (self.pack_dir / raw).resolve()
        try:
            target.relative_to(self.pack_dir)
        except ValueError:
            return None
        return target

    def read_pack(self, rel_path: str) -> SkillPack:
        target = self.safe_pack_path(rel_path)
        if target is None or not target.is_file():
            raise SkillPackError(f"pack not found: {rel_path}")
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise SkillPackError(f"could not read pack {rel_path}: {exc}") from exc
        meta, body = _parse_frontmatter(text)
        rel = str(target.relative_to(self.project_root)).replace("\\", "/")
        pack_id = str(meta.get("id") or target.stem)
        return SkillPack(
            pack_id=pack_id,
            name=str(meta.get("name") or pack_id),
            scope=str(meta.get("scope") or SCOPE_PROJECT),
            summary=str(meta.get("summary") or ""),
            capability=str(meta.get("capability") or CAPABILITY_BALANCED),
            tags=list(meta.get("tags") or []),
            keywords=list(meta.get("keywords") or []),
            version=str(meta.get("version") or "1.0.0"),
            rel_path=rel,
            content=text,
            body=body.strip(),
            metadata=meta,
        )

    def write_pack(self, pack: SkillPack, *, overwrite: bool = False) -> Path:
        """Write a pack to disk. The directory layout is preserved
        (``scope`` becomes a subdirectory)."""
        scope = pack.scope if pack.scope in KNOWN_SCOPES else SCOPE_PROJECT
        target = self.pack_dir / scope / f"{pack.pack_id}.md"
        if target.exists() and not overwrite:
            raise SkillPackError(f"pack already exists: {target.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        body = pack.body or pack.summary
        lines: List[str] = ["---"]
        lines.append(f"id: {pack.pack_id}")
        lines.append(f"name: {pack.name}")
        lines.append(f"scope: {pack.scope}")
        if pack.summary:
            lines.append(f"summary: {pack.summary}")
        if pack.capability:
            lines.append(f"capability: {pack.capability}")
        if pack.version:
            lines.append(f"version: {pack.version}")
        if pack.tags:
            lines.append(f"tags: [{', '.join(pack.tags)}]")
        if pack.keywords:
            lines.append(f"keywords: [{', '.join(pack.keywords)}]")
        lines.append("---")
        lines.append("")
        lines.append(body)
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    def list_packs(self) -> List[SkillPack]:
        packs: List[SkillPack] = []
        for path in self.iter_pack_files():
            rel = str(path.relative_to(self.pack_dir)).replace("\\", "/")
            try:
                packs.append(self.read_pack(rel))
            except SkillPackError:
                continue
        return packs

    def rebuild_index(self) -> int:
        """Rebuild the SQLite keyword index from the on-disk packs.
        Returns the number of indexed packs. Used by ``recall`` to
        score packs without re-parsing every file on every call."""
        try:
            if self.index_path.exists():
                self.index_path.unlink()
            conn = sqlite3.connect(str(self.index_path))
        except Exception:
            return 0
        try:
            conn.execute(
                "CREATE TABLE packs ("
                "  pack_id TEXT PRIMARY KEY,"
                "  rel_path TEXT NOT NULL,"
                "  scope TEXT NOT NULL,"
                "  keywords TEXT NOT NULL,"
                "  tags TEXT NOT NULL"
                ")"
            )
            count = 0
            for pack in self.list_packs():
                conn.execute(
                    "INSERT INTO packs(pack_id, rel_path, scope, keywords, tags) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        pack.pack_id,
                        pack.rel_path,
                        pack.scope,
                        " ".join(pack.keywords + pack.tags).lower(),
                        " ".join(pack.tags).lower(),
                    ),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Registry. The single object the rest of the agent talks to.
# ---------------------------------------------------------------------------


class SkillPackRegistry:
    """In-memory view over a ``SkillPackStorage``.

    The registry caches the parsed packs at construction time and
    exposes ``read``, ``list``, ``search``, and ``recall``. ``recall``
    is the keyword-scored lookup GoalLoop uses to bring project-side
    knowledge into the UNDERSTAND and PROPOSE stage prompts.
    """

    def __init__(self, storage: SkillPackStorage) -> None:
        self.storage = storage
        self._packs: Dict[str, SkillPack] = {}
        self.reload()

    def reload(self) -> None:
        self._packs = {pack.pack_id: pack for pack in self.storage.list_packs()}

    # -- public API ----------------------------------------------------

    def list(self, scope: Optional[str] = None) -> List[SkillPack]:
        packs = list(self._packs.values())
        if scope:
            packs = [p for p in packs if p.scope == scope]
        return sorted(packs, key=lambda p: p.pack_id)

    def read(self, pack_id: str) -> SkillPack:
        if pack_id not in self._packs:
            raise SkillPackError(f"unknown pack: {pack_id}")
        return self._packs[pack_id]

    def exists(self, pack_id: str) -> bool:
        return pack_id in self._packs

    def search(self, query: str, *, scope: Optional[str] = None,
               limit: int = 5) -> List[PackRecall]:
        return self.recall(query, scope=scope, limit=limit)

    def recall(self, query: str, *, scope: Optional[str] = None,
               limit: int = 5) -> List[PackRecall]:
        """Score every pack by keyword overlap with the query. Returns
        the top ``limit`` matches. Scope filters the candidate set."""
        if not query.strip():
            return []
        query_terms = set(_tokenize(query))
        if not query_terms:
            return []
        candidates = self.list(scope=scope)
        hits: List[PackRecall] = []
        for pack in candidates:
            pack_terms = set(_tokenize(" ".join(pack.keywords + pack.tags + [pack.summary])))
            if not pack_terms:
                # Fall back to scanning the body. Cheap and only runs
                # over a few hundred chars.
                pack_terms = set(_tokenize(pack.body[:600]))
            matched = sorted(pack_terms & query_terms)
            if not matched:
                continue
            # Score: 1.0 if all query terms hit, scaled by coverage.
            coverage = len(matched) / max(1, len(query_terms))
            specificity = len(matched) / max(1, len(pack_terms))
            score = 0.6 * coverage + 0.4 * specificity
            hits.append(PackRecall(pack=pack, score=score, matched_keywords=matched))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[: max(1, int(limit or 5))]

    def recall_for_task(self, task: str, *, limit: int = 3) -> List[PackRecall]:
        """Recall packs that match a free-text task. Used by the
        UNDERSTAND stage to bootstrap a goal's context."""
        task_terms = set(_tokenize(task))
        if not task_terms:
            return []
        # Prefer engine packs first (they are project-specific and
        # matter for every goal), then genre, then project notes.
        ordered = self.list(scope=SCOPE_ENGINE) + self.list(scope=SCOPE_GENRE) + self.list(scope=SCOPE_PROJECT)
        seen: set[str] = set()
        result: List[PackRecall] = []
        for pack in ordered:
            pack_terms = set(_tokenize(" ".join(pack.keywords + pack.tags + [pack.summary])))
            matched = sorted(pack_terms & task_terms)
            if not matched:
                continue
            if pack.pack_id in seen:
                continue
            seen.add(pack.pack_id)
            coverage = len(matched) / max(1, len(task_terms))
            specificity = len(matched) / max(1, len(pack_terms))
            score = 0.6 * coverage + 0.4 * specificity
            result.append(PackRecall(pack=pack, score=score, matched_keywords=matched))
        result.sort(key=lambda h: h.score, reverse=True)
        return result[: max(1, int(limit or 3))]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SKILL_PACK_VERSION,
            "pack_dir": str(self.storage.pack_dir),
            "pack_count": len(self._packs),
            "packs": [p.to_dict() for p in self.list()],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_WORD_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(str(text or ""))]


__all__ = [
    "SKILL_PACK_VERSION",
    "SKILL_PACK_DEFAULT_DIR",
    "CAPABILITY_FAST",
    "CAPABILITY_BALANCED",
    "CAPABILITY_DEEP",
    "SCOPE_ENGINE",
    "SCOPE_GENRE",
    "SCOPE_PROJECT",
    "SkillPack",
    "PackRecall",
    "SkillPackError",
    "SkillPackStorage",
    "SkillPackRegistry",
]
