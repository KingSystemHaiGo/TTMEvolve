"""Project introspection for the agent layer.

Q2 of the 2026-06-30 multimodal roadmap. The agent now has six read-only
tools that let it actually know what the project IS instead of guessing:

- ``project.manifest`` — structured project map: engine, scenes, scripts,
  asset categories, build state.
- ``project.asset_read`` — one asset's metadata with optional thumbnail
  (multimodal). The result carries a ``content`` array so the LLM can
  see the sprite/scene preview when it picks the next action.
- ``project.asset_search`` — find assets by name + category, useful
  when the LLM needs to pick a sprite that fits the current scene.
- ``project.code_search`` — symbol search across Lua/Python files
  (skipping .git / node_modules / .venv / dist / build / .ttmevolve).
- ``project.preview_capture`` — best-effort scene capture. When the
  project carries a saved preview PNG it is returned as an
  ``ImageBlock``; otherwise a synthetic thumbnail is produced so the
  LLM still gets a placeholder.
- ``project.build_state`` — read the last recorded build state from
  ``.ttmevolve/build_state.json`` if it exists.

Design rules:
- Pure read-only. No side effects, no commit tracking, no approval gate.
- Every tool returns the standard ``{"ok", "output", "content"}`` shape
  so it is forward-compatible with the multimodal observation format
  established in Q1.
- Failure is structured: ``{"ok": False, "error": str, "error_type": "..."}``
  so the LLM can recover instead of guessing from a free-text message.
- The introspector never escapes the project root. Any path is checked
  against the configured root before being read.
"""

from __future__ import annotations

import base64
import re
import struct
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


PROJECT_INTROSPECTION_VERSION = "project-introspection.v1"

# File extensions used to classify project files.
SCRIPT_EXTS = {".lua", ".py"}
SCENE_EXTS = {".scene", ".xml", ".scene.json", ".tscn", ".scn"}
SPRITE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".bmp"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
CONFIG_EXTS = {".cfg", ".ini", ".toml", ".yaml", ".yml", ".json"}

# Directories we never walk even if present in the project root.
SKIP_DIRS = {
    ".git", ".venv", "node_modules", "dist", "build", "__pycache__",
    ".pytest_cache", ".ttmevolve", ".idea", ".vscode", "target",
}

# Heuristics for "is this a Maker / UrhoX project".
URHOX_MARKERS = (
    "urhox",
    "urho",
    "maker",
    "taptap",
)


@dataclass
class AssetRecord:
    name: str
    rel_path: str
    category: str
    size_bytes: int
    media_type: str = ""
    thumbnail_rel_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "rel_path": self.rel_path,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "thumbnail_rel_path": self.thumbnail_rel_path,
            "metadata": dict(self.metadata),
        }


@dataclass
class ProjectManifest:
    project_root: str
    engine: str
    engine_confidence: float
    scene_count: int
    script_count: int
    asset_counts: Dict[str, int]
    build_state: Dict[str, Any]
    categories: List[Dict[str, Any]] = field(default_factory=list)
    top_level: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": self.project_root,
            "engine": self.engine,
            "engine_confidence": self.engine_confidence,
            "scene_count": self.scene_count,
            "script_count": self.script_count,
            "asset_counts": dict(self.asset_counts),
            "build_state": dict(self.build_state),
            "categories": list(self.categories),
            "top_level": list(self.top_level),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Tool surface — every method is its own tool. Names use ``project.`` so
# they show up in the runtime contract and the agent's tool list.
# ---------------------------------------------------------------------------


class ProjectIntrospector:
    """Walk a Maker / UrhoX project and answer read-only questions about it.

    The class is intentionally framework-free: it does not depend on the
    executor, the registry, or the LLM. That keeps the unit tests fast
    and lets the same logic be used by background services.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        preview_dir: Optional[Path] = None,
        build_state_path: Optional[Path] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.preview_dir = Path(preview_dir) if preview_dir else (self.project_root / ".previews")
        self.build_state_path = (
            Path(build_state_path)
            if build_state_path
            else (self.project_root / ".ttmevolve" / "build_state.json")
        )

    # -- safety helpers --------------------------------------------------

    def _safe_path(self, rel_path: str) -> Optional[Path]:
        """Resolve ``rel_path`` against the project root and ensure it
        does not escape. Returns ``None`` when the path is invalid."""
        if not rel_path:
            return None
        raw = str(rel_path).replace("\\", "/").lstrip("/")
        if ".." in Path(raw).parts:
            return None
        target = (self.project_root / raw).resolve()
        try:
            target.relative_to(self.project_root)
        except ValueError:
            return None
        return target

    def _deny(self, reason: str, error_type: str = "invalid_path") -> Dict[str, Any]:
        return {"ok": False, "error": reason, "error_type": error_type}

    # -- public tool methods --------------------------------------------

    def project_manifest(
        self,
        include_assets: bool = True,
        max_assets: int = 200,
    ) -> Dict[str, Any]:
        """Structured project map. Cheap: it does not open files."""
        manifest = self._build_manifest(max_assets=max_assets)
        out = manifest.to_dict()
        if not include_assets:
            out["asset_counts"] = dict(manifest.asset_counts)
        return {"ok": True, "output": self._manifest_summary(manifest), "manifest": out}

    def project_asset_read(self, name: str) -> Dict[str, Any]:
        """Read one asset's metadata. Returns a multimodal ``content``
        array carrying a thumbnail ``ImageBlock`` when one is available
        so the LLM can see the sprite / scene preview."""
        if not name:
            return self._deny("name is required", "missing_param")
        target = self._safe_path(name)
        if target is None or not target.is_file():
            return self._deny(f"asset not found: {name}", "not_found")
        record = self._classify_file(target)
        if record is None:
            return self._deny(f"file is not a recognised asset: {name}", "unsupported_type")
        # Probe for a sibling thumbnail or a preview file.
        thumbnail_rel = self._find_thumbnail(target)
        if thumbnail_rel:
            try:
                rel = thumbnail_rel.relative_to(self.project_root)
            except ValueError:
                rel = Path(thumbnail_rel.name)
            record.thumbnail_rel_path = str(rel).replace("\\", "/")
        text = (
            f"asset {record.name} ({record.category}, {record.size_bytes} bytes, "
            f"{record.media_type or 'unknown'}) at {record.rel_path}"
        )
        content: List[Dict[str, Any]] = [{"type": "text", "text": text}]
        if thumbnail_rel and thumbnail_rel.is_file():
            content.append({
                "type": "image",
                "source": str(thumbnail_rel.resolve()),
                "media_type": self._guess_media_type(thumbnail_rel),
                "caption": f"thumbnail for {record.name}",
            })
        return {
            "ok": True,
            "output": text,
            "asset": record.to_dict(),
            "content": content,
        }

    def project_asset_search(
        self,
        query: str = "",
        category: str = "",
        limit: int = 10,
    ) -> Dict[str, Any]:
        query_lower = str(query or "").lower()
        category_lower = str(category or "").lower()
        limit = max(1, min(int(limit or 10), 50))
        matches: List[AssetRecord] = []
        for record in self._iter_assets(max_records=500):
            if category_lower and record.category != category_lower:
                continue
            if query_lower and query_lower not in record.name.lower():
                continue
            matches.append(record)
            if len(matches) >= limit:
                break
        return {
            "ok": True,
            "output": f"{len(matches)} asset(s) matched.",
            "assets": [record.to_dict() for record in matches],
            "content": [
                {
                    "type": "text",
                    "text": "\n".join(
                        f"- {r.category}: {r.name} ({r.size_bytes}B) at {r.rel_path}"
                        for r in matches
                    ) or "no assets matched",
                }
            ],
        }

    def project_code_search(
        self,
        symbol: str,
        file_glob: str = "*.lua",
        limit: int = 20,
    ) -> Dict[str, Any]:
        if not symbol:
            return self._deny("symbol is required", "missing_param")
        limit = max(1, min(int(limit or 20), 200))
        pattern = re.compile(re.escape(str(symbol)))
        matches: List[Dict[str, Any]] = []
        scanned = 0
        for path in self._iter_files(file_glob):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            scanned += 1
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append({
                        "file": str(path.relative_to(self.project_root)),
                        "line": line_no,
                        "text": line.strip()[:240],
                    })
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit:
                break
        return {
            "ok": True,
            "output": f"{len(matches)} match(es) for '{symbol}' across {scanned} file(s).",
            "matches": matches,
            "scanned_files": scanned,
        }

    def project_preview_capture(
        self,
        scene_id: str = "",
        save_path: str = "",
    ) -> Dict[str, Any]:
        """Best-effort preview capture. If a saved preview PNG exists for
        ``scene_id`` it is returned as an ``ImageBlock``; otherwise a
        synthetic placeholder PNG is generated so the LLM still gets a
        visual signal. ``save_path`` overrides the auto-generated path."""
        preview_path: Optional[Path] = None
        if save_path:
            target = self._safe_path(save_path)
            if target is None:
                return self._deny(f"save_path escapes project root: {save_path}", "invalid_path")
            preview_path = target
        else:
            preview_path = self._auto_preview_path(scene_id)
        if preview_path is None:
            return self._deny("could not determine preview path", "missing_param")
        if not preview_path.is_file():
            try:
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_placeholder_png(preview_path, label=scene_id or "preview")
            except Exception as exc:
                return self._deny(f"could not write preview: {exc}", "io_error")
        text = f"preview captured for {scene_id or 'project'}"
        return {
            "ok": True,
            "output": text,
            "preview_path": str(preview_path.relative_to(self.project_root)).replace("\\", "/"),
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "image",
                    "source": str(preview_path.resolve()),
                    "media_type": "image/png",
                    "caption": f"preview for {scene_id or 'project'}",
                },
            ],
        }

    def project_build_state(self) -> Dict[str, Any]:
        if not self.build_state_path.is_file():
            return {
                "ok": True,
                "output": "no build state recorded",
                "build_state": {"available": False, "reason": "no file"},
            }
        try:
            import json
            data = json.loads(self.build_state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._deny(f"could not read build state: {exc}", "io_error")
        return {
            "ok": True,
            "output": f"last build: {data.get('status', 'unknown')}",
            "build_state": data,
        }

    # ------------------------------------------------------------------
    # Skill pack surface. Project-side knowledge the agent can recall.
    # ------------------------------------------------------------------

    def project_skill_pack(
        self,
        action: str = "list",
        query: str = "",
        pack_id: str = "",
        scope: str = "",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Read or search project-side skill packs.

        ``action`` is one of:
        - ``"list"`` — list every pack, optionally filtered by ``scope``.
        - ``"read"`` — return the full body of a single pack by id.
        - ``"search"`` — keyword-scored recall against ``query``.

        The default pack directory is ``docs/skill_packs/``. Empty
        directories are auto-seeded with the engine / genre defaults
        on first access so the agent has working knowledge available
        without the user authoring anything.
        """
        from agent.skill_packs import (
            SkillPackError,
            SkillPackRegistry,
            SkillPackStorage,
        )
        from agent.skill_packs.bootstrap import (
            DEFAULT_SEED_DIR,
            bootstrap_default_packs,
        )
        action = str(action or "list").lower().strip()
        storage = SkillPackStorage(self.project_root)
        if not list(storage.iter_pack_files()):
            bootstrap_default_packs(self.project_root, seed_dir=DEFAULT_SEED_DIR)
        registry = SkillPackRegistry(storage)
        if action == "list":
            packs = registry.list(scope=str(scope or "") or None)
            return {
                "ok": True,
                "output": f"{len(packs)} pack(s)",
                "packs": [p.to_dict() for p in packs],
            }
        if action == "read":
            if not pack_id:
                return self._deny("pack_id is required for action=read", "missing_param")
            try:
                pack = registry.read(pack_id)
            except SkillPackError as exc:
                return self._deny(str(exc), "not_found")
            return {
                "ok": True,
                "output": f"pack {pack.pack_id} ({pack.scope})",
                "pack": pack.to_dict(),
                "body": pack.body,
            }
        if action == "search":
            if not query:
                return self._deny("query is required for action=search", "missing_param")
            hits = registry.search(query, scope=str(scope or "") or None, limit=max(1, min(int(limit or 5), 20)))
            return {
                "ok": True,
                "output": f"{len(hits)} match(es) for '{query}'",
                "matches": [h.to_dict() for h in hits],
            }
        return self._deny(f"unknown action: {action}", "bad_param")

    # -- internal helpers -----------------------------------------------

    def _manifest_summary(self, manifest: ProjectManifest) -> str:
        return (
            f"{manifest.engine} project at {manifest.project_root}: "
            f"{manifest.scene_count} scene(s), {manifest.script_count} script(s), "
            f"asset counts = {manifest.asset_counts}"
        )

    def _build_manifest(self, *, max_assets: int) -> ProjectManifest:
        asset_counts: Dict[str, int] = {}
        scene_count = 0
        script_count = 0
        top_level: List[Dict[str, Any]] = []
        warnings: List[str] = []
        root = self.project_root
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except FileNotFoundError:
            return ProjectManifest(
                project_root=str(root),
                engine="unknown",
                engine_confidence=0.0,
                scene_count=0,
                script_count=0,
                asset_counts={},
                build_state={"available": False, "reason": "project root not found"},
                warnings=["project_root does not exist"],
            )
        for entry in entries:
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            top_level.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
            })
        engine, confidence = self._detect_engine()
        for record in self._iter_assets(max_records=max_assets):
            asset_counts[record.category] = asset_counts.get(record.category, 0) + 1
            if record.category == "scene":
                scene_count += 1
            elif record.category == "script":
                script_count += 1
        build_state: Dict[str, Any]
        if self.build_state_path.is_file():
            try:
                import json
                build_state = json.loads(self.build_state_path.read_text(encoding="utf-8"))
            except Exception as exc:
                build_state = {"available": False, "reason": f"unreadable: {exc}"}
                warnings.append(f"build_state unreadable: {exc}")
        else:
            build_state = {"available": False, "reason": "no file"}
        return ProjectManifest(
            project_root=str(root),
            engine=engine,
            engine_confidence=confidence,
            scene_count=scene_count,
            script_count=script_count,
            asset_counts=asset_counts,
            build_state=build_state,
            top_level=top_level[:30],
            warnings=warnings,
        )

    def _detect_engine(self) -> Tuple[str, float]:
        """Cheap heuristic: file extensions + path-name + top-level
        directory markers. Returns ``("urhox", 0.0-1.0)`` or similar."""
        score = 0.0
        names = " ".join(p.name.lower() for p in self._iter_files("*"))
        names += " " + self.project_root.name.lower()
        for marker in URHOX_MARKERS:
            if marker in names:
                score += 0.5
        # Count Lua files (UrhoX projects are Lua-heavy).
        lua_count = 0
        scene_count = 0
        sprite_count = 0
        for path in self._iter_files("*.lua"):
            lua_count += 1
            if lua_count >= 3:
                break
        for path in self._iter_files("*.scene"):
            scene_count += 1
        for path in self._iter_files("*.png"):
            sprite_count += 1
        if lua_count >= 1:
            score += 0.25
        if scene_count >= 1:
            score += 0.1
        if sprite_count >= 1:
            score += 0.05
        score = min(score, 1.0)
        if score >= 0.5:
            return "urhox", score
        if score >= 0.25:
            return "urhox-like", score
        return "unknown", score

    def _iter_files(self, glob: str) -> List[Path]:
        results: List[Path] = []
        try:
            for path in self.project_root.rglob(glob):
                if not path.is_file():
                    continue
                rel_parts = path.relative_to(self.project_root).parts
                if any(part in SKIP_DIRS for part in rel_parts):
                    continue
                results.append(path)
                if len(results) >= 5000:
                    break
        except Exception:
            return results
        return results

    def _iter_assets(self, *, max_records: int) -> List[AssetRecord]:
        records: List[AssetRecord] = []
        for path in self._iter_files("*"):
            record = self._classify_file(path)
            if record is None:
                continue
            records.append(record)
            if len(records) >= max_records:
                break
        return records

    def _classify_file(self, path: Path) -> Optional[AssetRecord]:
        ext = path.suffix.lower()
        rel = str(path.relative_to(self.project_root))
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if ext in SCRIPT_EXTS:
            return AssetRecord(
                name=path.name, rel_path=rel, category="script",
                size_bytes=size, media_type="text/plain",
            )
        if ext in SCENE_EXTS:
            return AssetRecord(
                name=path.name, rel_path=rel, category="scene",
                size_bytes=size, media_type=self._guess_media_type(path),
            )
        if ext in SPRITE_EXTS:
            return AssetRecord(
                name=path.name, rel_path=rel, category="sprite",
                size_bytes=size, media_type=self._guess_media_type(path),
            )
        if ext in AUDIO_EXTS:
            return AssetRecord(
                name=path.name, rel_path=rel, category="audio",
                size_bytes=size, media_type=self._guess_media_type(path),
            )
        if ext in CONFIG_EXTS:
            return AssetRecord(
                name=path.name, rel_path=rel, category="config",
                size_bytes=size, media_type="text/plain",
            )
        return None

    @staticmethod
    def _guess_media_type(path: Path) -> str:
        from mimetypes import guess_type
        guessed, _ = guess_type(str(path))
        return guessed or "application/octet-stream"

    def _find_thumbnail(self, target: Path) -> Optional[Path]:
        """Look for a sibling or .previews/ thumbnail. Returns absolute
        path or ``None``. Cheap: only checks well-known names."""
        candidates = [
            target.with_suffix(".thumb.png"),
            target.with_suffix(".thumb.jpg"),
            target.with_name(target.stem + ".thumb.png"),
            self.preview_dir / (target.stem + ".png"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _auto_preview_path(self, scene_id: str) -> Optional[Path]:
        if not scene_id:
            return self.preview_dir / "default.png"
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", scene_id).strip("_") or "scene"
        return self.preview_dir / f"{safe}.png"

    @staticmethod
    def _write_placeholder_png(path: Path, *, label: str) -> None:
        """Write a tiny 64x64 solid-color PNG. No external libs.

        The placeholder is a single grey square; the LLM only needs *some*
        image to look at so its multimodal path can fire.
        """
        width, height = 64, 64
        # Raw RGBA pixels: medium grey.
        row = bytes((128, 128, 128, 255)) * width
        raw = b""
        for _ in range(height):
            raw += b"\x00" + row
        compressed = zlib.compress(raw, 9)

        def chunk(kind: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(kind + data)
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

        signature = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        png = signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
        path.write_bytes(png)


# ---------------------------------------------------------------------------
# Tool registration. We hand the introspector to the executor via
# ``register_dynamic_tool`` so the read-only tools get the standard
# dynamic-tool plumbing (sandbox, approval at low risk, no commit
# tracking) without polluting the global builtin tool list.
# ---------------------------------------------------------------------------

INTROSPECTION_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "project.manifest",
        "description": (
            "Return a structured project map: engine type, scene count, "
            "script count, asset category counts, top-level layout, and "
            "the last build state. Use this first when you join a new "
            "project or resume work after a long pause."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "include_assets": {"type": "boolean", "default": True},
                "max_assets": {"type": "integer", "default": 200},
            },
        },
        "method": "project_manifest",
    },
    {
        "name": "project.asset_read",
        "description": (
            "Read one asset's metadata, optionally returning a thumbnail "
            "as a multimodal image. Pass the asset's relative path or "
            "its file name. The result is multimodal: text + image when "
            "a thumbnail exists."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "method": "project_asset_read",
    },
    {
        "name": "project.asset_search",
        "description": (
            "Search assets by name and category. ``category`` is one of "
            "sprite, scene, audio, script, config. Useful when picking a "
            "sprite for a new entity or finding reusable scenes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
        },
        "method": "project_asset_search",
    },
    {
        "name": "project.code_search",
        "description": (
            "Grep a symbol across project scripts. ``file_glob`` defaults "
            "to ``*.lua`` (UrhoX). Returns file + line + trimmed text. "
            "Use this before editing a function to find call sites."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "file_glob": {"type": "string", "default": "*.lua"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["symbol"],
        },
        "method": "project_code_search",
    },
    {
        "name": "project.preview_capture",
        "description": (
            "Capture (or generate) a preview image for ``scene_id``. The "
            "result is multimodal so the LLM can see the scene. If a real "
            "preview PNG is missing a small placeholder is written so the "
            "multimodal path always returns something visual."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scene_id": {"type": "string"},
                "save_path": {"type": "string"},
            },
        },
        "method": "project_preview_capture",
    },
    {
        "name": "project.build_state",
        "description": (
            "Read the last recorded build state from .ttmevolve/"
            "build_state.json. Returns status, errors, and the last "
            "build timestamp when available."
        ),
        "parameters": {"type": "object", "properties": {}},
        "method": "project_build_state",
    },
    {
        "name": "project.skill_pack",
        "description": (
            "Read or search the project-side skill packs. The "
            "default directory is docs/skill_packs/. Use action=list "
            "to enumerate packs (optionally filtered by scope: "
            "engine, genre, project), action=read to fetch a single "
            "pack by id, or action=search to keyword-rank packs "
            "against a free-text query. Empty pack directories are "
            "auto-seeded with engine and genre defaults on first "
            "access."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "read", "search"]},
                "query": {"type": "string"},
                "pack_id": {"type": "string"},
                "scope": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
        },
        "method": "project_skill_pack",
    },
]


def register_introspection_tools(
    tools: Any,
    executor: Any,
    project_root: Path,
) -> ProjectIntrospector:
    """Register the six introspection tools with the tool registry and
    the executor. Returns the introspector instance so callers can call
    the methods directly (e.g. from background services)."""
    introspector = ProjectIntrospector(Path(project_root))
    for spec in INTROSPECTION_TOOL_SPECS:
        method = getattr(introspector, spec["method"])
        # ``register_dynamic_tool`` is the right home: read-only, low
        # risk, no commit tracking, but still routed through the
        # standard tool pipeline so preflight + sandbox apply.
        if hasattr(executor, "register_dynamic_tool"):
            executor.register_dynamic_tool(spec["name"], method, risk_level="low")
        elif hasattr(executor, "_tool_handlers"):
            # Fallback for older executors that do not yet expose the
            # dynamic registration helper.
            executor._tool_handlers[spec["name"]] = method
        if hasattr(tools, "register"):
            tools.register(
                name=spec["name"],
                description=spec["description"],
                parameters=spec["parameters"],
                handler=method,
                source="introspection",
            )
    return introspector


__all__ = [
    "PROJECT_INTROSPECTION_VERSION",
    "AssetRecord",
    "ProjectManifest",
    "ProjectIntrospector",
    "INTROSPECTION_TOOL_SPECS",
    "register_introspection_tools",
]
