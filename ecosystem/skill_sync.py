"""Cross-ecosystem skill sync status and drift detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from ecosystem.claude_code_adapter import export_to_claude_code, load_claude_code_skill
from ecosystem.hermes_adapter import export_to_hermes, load_hermes_skill
from ecosystem.openclaw_adapter import export_to_openclaw, load_openclaw_skill
from ecosystem.skill_schema import CanonicalSkill


@dataclass(frozen=True)
class SkillSyncRecord:
    ecosystem: str
    id: str
    name: str
    version: str
    fingerprint: str
    path: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ecosystem": self.ecosystem,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "path": self.path,
            "description": self.description,
        }


@dataclass(frozen=True)
class CanonicalSkillSource:
    skill: CanonicalSkill
    path: Path


@dataclass(frozen=True)
class SkillExportTarget:
    ecosystem: str
    relative_path: str
    exporter: Callable[[CanonicalSkill], str]


DEFAULT_EXPORT_TARGETS: Dict[str, SkillExportTarget] = {
    "hermes": SkillExportTarget("hermes", ".hermes/skills/{id}/SKILL.md", export_to_hermes),
    "openclaw": SkillExportTarget("openclaw", ".openclaw/skills/{id}/SKILL.md", export_to_openclaw),
    "claude_code": SkillExportTarget("claude_code", ".claude/skills/{id}/SKILL.md", export_to_claude_code),
    "codex": SkillExportTarget("codex", ".codex/skills/{id}/SKILL.md", export_to_claude_code),
}


def skill_fingerprint(skill: CanonicalSkill) -> str:
    """Hash the portable content that should stay aligned across agents."""
    payload = {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "tags": sorted(str(tag) for tag in skill.tags),
        "body": skill.body,
        "code": skill.code,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_from_skill(skill: CanonicalSkill, ecosystem: str, path: Path) -> SkillSyncRecord:
    return SkillSyncRecord(
        ecosystem=ecosystem,
        id=str(skill.id),
        name=str(skill.name),
        version=str(skill.version or "0.0.0"),
        fingerprint=skill_fingerprint(skill),
        path=str(path),
        description=str(skill.description or ""),
    )


def _load_canonical_skill(skill_json: Path) -> Optional[CanonicalSkill]:
    try:
        data = json.loads(skill_json.read_text(encoding="utf-8"))
        skill = CanonicalSkill.from_dict(data)
        code_path = skill_json.with_name("skill.py")
        if code_path.exists():
            skill.code = code_path.read_text(encoding="utf-8")
        return skill
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def load_canonical_skill_sources(skills_dir: Path) -> List[CanonicalSkillSource]:
    sources: List[CanonicalSkillSource] = []
    if not skills_dir.exists():
        return sources
    for skill_json in sorted(skills_dir.rglob("skill.json")):
        skill = _load_canonical_skill(skill_json)
        if skill:
            sources.append(CanonicalSkillSource(skill=skill, path=skill_json))
    return sources


def discover_canonical_skill_records(skills_dir: Path) -> List[SkillSyncRecord]:
    return [
        _record_from_skill(source.skill, "canonical", source.path)
        for source in load_canonical_skill_sources(skills_dir)
    ]


def _canonical_roots(
    project_root: Path,
    skills_dir: Optional[Path],
    extra_skills_dirs: Optional[Iterable[Path]] = None,
) -> List[Path]:
    if skills_dir is not None:
        return [skills_dir.resolve()]
    roots = [
        project_root / "skills",
        project_root / "storage" / "skills",
    ]
    roots.extend(extra_skills_dirs or [])
    unique: List[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _discover_skill_md_records(
    roots: Iterable[Path],
    *,
    ecosystem: str,
    loader,
) -> List[SkillSyncRecord]:
    records: List[SkillSyncRecord] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists() or root in seen:
            continue
        seen.add(root)
        for skill_file in sorted(root.rglob("SKILL.md")):
            skill = loader(skill_file)
            if skill:
                records.append(_record_from_skill(skill, ecosystem, skill_file))
    return records


def discover_skill_records(
    project_root: Path,
    *,
    skills_dir: Optional[Path] = None,
    extra_skills_dirs: Optional[Iterable[Path]] = None,
    include_home: bool = False,
) -> List[SkillSyncRecord]:
    """Discover local skill copies without mutating any ecosystem."""
    project_root = project_root.resolve()

    records: List[SkillSyncRecord] = []
    for canonical_root in _canonical_roots(project_root, skills_dir, extra_skills_dirs):
        records.extend(discover_canonical_skill_records(canonical_root))
    records.extend(
        _discover_skill_md_records(
            [
                project_root / ".hermes" / "skills",
                project_root / "exported_skills" / "hermes",
            ],
            ecosystem="hermes",
            loader=load_hermes_skill,
        )
    )
    records.extend(
        _discover_skill_md_records(
            [
                project_root / ".openclaw" / "skills",
                project_root / "exported_skills" / "openclaw",
            ],
            ecosystem="openclaw",
            loader=load_openclaw_skill,
        )
    )
    records.extend(
        _discover_skill_md_records(
            [
                project_root / ".claude" / "skills",
                project_root / "exported_skills" / "claude_code",
            ],
            ecosystem="claude_code",
            loader=load_claude_code_skill,
        )
    )
    records.extend(
        _discover_skill_md_records(
            [
                project_root / ".codex" / "skills",
                project_root / "exported_skills" / "codex",
            ],
            ecosystem="codex",
            loader=load_claude_code_skill,
        )
    )

    if include_home:
        home = Path.home()
        records.extend(
            _discover_skill_md_records(
                [home / ".hermes" / "skills"],
                ecosystem="hermes",
                loader=load_hermes_skill,
            )
        )
        records.extend(
            _discover_skill_md_records(
                [home / ".openclaw" / "skills"],
                ecosystem="openclaw",
                loader=load_openclaw_skill,
            )
        )
        records.extend(
            _discover_skill_md_records(
                [home / ".claude" / "skills"],
                ecosystem="claude_code",
                loader=load_claude_code_skill,
            )
        )
        records.extend(
            _discover_skill_md_records(
                [home / ".codex" / "skills"],
                ecosystem="codex",
                loader=load_claude_code_skill,
            )
        )

    return sorted(records, key=lambda item: (item.id, item.ecosystem, item.path))


def _group_records(records: Iterable[SkillSyncRecord]) -> Dict[str, List[SkillSyncRecord]]:
    grouped: Dict[str, List[SkillSyncRecord]] = {}
    for record in records:
        grouped.setdefault(record.id, []).append(record)
    return grouped


def _version_conflict(skill_id: str, records: List[SkillSyncRecord]) -> Optional[Dict[str, Any]]:
    versions: Dict[str, List[str]] = {}
    for record in records:
        versions.setdefault(record.version, []).append(record.ecosystem)
    if len(versions) <= 1:
        return None
    return {
        "type": "version_conflict",
        "skill_id": skill_id,
        "versions": {version: sorted(set(sources)) for version, sources in versions.items()},
    }


def _fingerprint_conflicts(skill_id: str, records: List[SkillSyncRecord]) -> List[Dict[str, Any]]:
    by_version: Dict[str, Dict[str, List[str]]] = {}
    for record in records:
        by_version.setdefault(record.version, {}).setdefault(record.fingerprint, []).append(record.ecosystem)

    conflicts: List[Dict[str, Any]] = []
    for version, fingerprints in sorted(by_version.items()):
        if len(fingerprints) <= 1:
            continue
        conflicts.append(
            {
                "type": "fingerprint_mismatch",
                "skill_id": skill_id,
                "version": version,
                "fingerprints": {
                    fingerprint: sorted(set(sources))
                    for fingerprint, sources in fingerprints.items()
                },
            }
        )
    return conflicts


def build_skill_sync_manifest(records: Iterable[SkillSyncRecord]) -> Dict[str, Any]:
    record_list = sorted(records, key=lambda item: (item.id, item.ecosystem, item.path))
    grouped = _group_records(record_list)
    conflicts: List[Dict[str, Any]] = []
    for skill_id, skill_records in sorted(grouped.items()):
        version_conflict = _version_conflict(skill_id, skill_records)
        if version_conflict:
            conflicts.append(version_conflict)
        conflicts.extend(_fingerprint_conflicts(skill_id, skill_records))

    ecosystems = sorted({record.ecosystem for record in record_list})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_records": len(record_list),
            "total_skills": len(grouped),
            "total_conflicts": len(conflicts),
            "ecosystems": ecosystems,
        },
        "records": [record.to_dict() for record in record_list],
        "conflicts": conflicts,
    }


def skill_sync_signature(manifest: Dict[str, Any]) -> str:
    payload = {
        "records": [
            {
                "ecosystem": record.get("ecosystem"),
                "id": record.get("id"),
                "version": record.get("version"),
                "fingerprint": record.get("fingerprint"),
            }
            for record in manifest.get("records", [])
        ],
        "conflicts": manifest.get("conflicts", []),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_index(records: Iterable[SkillSyncRecord]) -> Dict[tuple[str, str], SkillSyncRecord]:
    indexed: Dict[tuple[str, str], SkillSyncRecord] = {}
    for record in records:
        indexed.setdefault((record.ecosystem, record.id), record)
    return indexed


def _conflict_ids(manifest: Dict[str, Any]) -> set[str]:
    return {
        str(conflict.get("skill_id"))
        for conflict in manifest.get("conflicts", [])
        if conflict.get("skill_id")
    }


def _export_target_path(project_root: Path, target: SkillExportTarget, skill_id: str) -> Path:
    return project_root / target.relative_path.format(id=skill_id)


def build_skill_export_plan(
    project_root: Path,
    *,
    skills_dir: Optional[Path] = None,
    extra_skills_dirs: Optional[Iterable[Path]] = None,
    records: Optional[Iterable[SkillSyncRecord]] = None,
    manifest: Optional[Dict[str, Any]] = None,
    target_ecosystems: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    project_root = project_root.resolve()
    record_list = list(records) if records is not None else discover_skill_records(
        project_root,
        skills_dir=skills_dir,
        extra_skills_dirs=extra_skills_dirs,
    )
    manifest = manifest or build_skill_sync_manifest(record_list)
    canonical_sources: List[CanonicalSkillSource] = []
    for canonical_root in _canonical_roots(project_root, skills_dir, extra_skills_dirs):
        canonical_sources.extend(load_canonical_skill_sources(canonical_root))
    indexed = _record_index(record_list)
    conflict_skill_ids = _conflict_ids(manifest)
    targets = [
        DEFAULT_EXPORT_TARGETS[name]
        for name in (target_ecosystems or DEFAULT_EXPORT_TARGETS.keys())
        if name in DEFAULT_EXPORT_TARGETS
    ]

    actions: List[Dict[str, Any]] = []
    for source in canonical_sources:
        skill = source.skill
        canonical_fingerprint = skill_fingerprint(skill)
        has_conflict = skill.id in conflict_skill_ids
        for target in targets:
            target_path = _export_target_path(project_root, target, skill.id)
            existing = indexed.get((target.ecosystem, skill.id))
            action = "skip"
            reason = "target already matches canonical skill"
            needs_review = False
            if existing is None:
                action = "create"
                reason = "target skill is missing"
            elif existing.version != str(skill.version):
                action = "update"
                reason = "target version differs from canonical"
                needs_review = has_conflict
            elif existing.fingerprint != canonical_fingerprint:
                action = "update"
                reason = "target content fingerprint differs from canonical"
                needs_review = True

            actions.append(
                {
                    "skill_id": skill.id,
                    "target": target.ecosystem,
                    "action": action,
                    "reason": reason,
                    "needs_review": needs_review,
                    "source_path": str(source.path),
                    "target_path": str(target_path),
                    "canonical_version": str(skill.version),
                    "current_version": existing.version if existing else None,
                    "current_fingerprint": existing.fingerprint if existing else None,
                    "canonical_fingerprint": canonical_fingerprint,
                }
            )

    summary = {
        "total_actions": len(actions),
        "create": sum(1 for item in actions if item["action"] == "create"),
        "update": sum(1 for item in actions if item["action"] == "update"),
        "skip": sum(1 for item in actions if item["action"] == "skip"),
        "needs_review": sum(1 for item in actions if item["needs_review"]),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "actions": actions,
    }


def build_dynamic_skill_graph(
    project_root: Path,
    *,
    skills_dir: Optional[Path] = None,
    extra_skills_dirs: Optional[Iterable[Path]] = None,
    records: Optional[Iterable[SkillSyncRecord]] = None,
    manifest: Optional[Dict[str, Any]] = None,
    export_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    project_root = project_root.resolve()
    record_list = list(records) if records is not None else discover_skill_records(
        project_root,
        skills_dir=skills_dir,
        extra_skills_dirs=extra_skills_dirs,
    )
    manifest = manifest or build_skill_sync_manifest(record_list)
    export_plan = export_plan or build_skill_export_plan(
        project_root,
        skills_dir=skills_dir,
        extra_skills_dirs=extra_skills_dirs,
        records=record_list,
        manifest=manifest,
    )

    canonical_by_id: Dict[str, CanonicalSkill] = {}
    for canonical_root in _canonical_roots(project_root, skills_dir, extra_skills_dirs):
        for source in load_canonical_skill_sources(canonical_root):
            canonical_by_id.setdefault(source.skill.id, source.skill)

    conflicts_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for conflict in manifest.get("conflicts", []):
        skill_id = str(conflict.get("skill_id", ""))
        if skill_id:
            conflicts_by_id.setdefault(skill_id, []).append(conflict)

    actions_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for action in export_plan.get("actions", []):
        skill_id = str(action.get("skill_id", ""))
        if skill_id:
            actions_by_id.setdefault(skill_id, []).append(action)

    grouped = _group_records(record_list)
    nodes: List[Dict[str, Any]] = []
    for skill_id, skill_records in sorted(grouped.items()):
        canonical = canonical_by_id.get(skill_id)
        providers = [
            {
                "ecosystem": record.ecosystem,
                "version": record.version,
                "fingerprint": record.fingerprint,
                "path": record.path,
            }
            for record in sorted(skill_records, key=lambda item: (item.ecosystem, item.path))
        ]
        pending_actions = [
            action for action in actions_by_id.get(skill_id, [])
            if action.get("action") != "skip"
        ]
        nodes.append(
            {
                "skill_id": skill_id,
                "name": canonical.name if canonical else skill_records[0].name,
                "description": canonical.description if canonical else skill_records[0].description,
                "versions": sorted({record.version for record in skill_records}),
                "providers": providers,
                "input_schema": canonical.parameters if canonical else {"type": "object", "properties": {}},
                "output_schema": {"type": "object"},
                "preconditions": {
                    "source": canonical.source if canonical else "",
                    "tags": canonical.tags if canonical else [],
                },
                "conflicts": conflicts_by_id.get(skill_id, []),
                "pending_export_actions": pending_actions,
                "callability": "blocked_by_conflict" if conflicts_by_id.get(skill_id) else "available",
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_skills": len(nodes),
            "available": sum(1 for node in nodes if node["callability"] == "available"),
            "blocked_by_conflict": sum(1 for node in nodes if node["callability"] == "blocked_by_conflict"),
            "pending_export_actions": sum(len(node["pending_export_actions"]) for node in nodes),
        },
        "nodes": nodes,
    }


def render_export_for_action(action: Dict[str, Any], skills_dir: Path) -> Optional[str]:
    target = DEFAULT_EXPORT_TARGETS.get(str(action.get("target")))
    if not target:
        return None
    source_path = Path(str(action.get("source_path", "")))
    if not source_path.exists():
        source_path = skills_dir / str(action.get("skill_id", "")) / "skill.json"
    skill = _load_canonical_skill(source_path)
    if not skill:
        return None
    return target.exporter(skill)


def apply_skill_export_plan(
    plan: Dict[str, Any],
    *,
    skills_dir: Path,
    require_review: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for action in plan.get("actions", []):
        if action.get("action") == "skip":
            skipped.append({**action, "skip_reason": "already_matching"})
            continue
        if action.get("needs_review") and require_review:
            skipped.append({**action, "skip_reason": "needs_review"})
            continue
        rendered = render_export_for_action(action, skills_dir)
        if rendered is None:
            skipped.append({**action, "skip_reason": "render_failed"})
            continue
        if not dry_run:
            target_path = Path(str(action["target_path"]))
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(rendered, encoding="utf-8")
        applied.append({**action, "dry_run": dry_run})
    return {
        "dry_run": dry_run,
        "applied": applied,
        "skipped": skipped,
        "summary": {
            "applied": len(applied),
            "skipped": len(skipped),
        },
    }


def write_skill_sync_manifest(
    project_root: Path,
    manifest: Dict[str, Any],
    *,
    output_path: Optional[Path] = None,
) -> Path:
    path = output_path or project_root / "storage" / "skill_sync" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class SkillSyncRegistry:
    def __init__(
        self,
        project_root: Path,
        storage_root: Path,
        *,
        refresh_interval_seconds: int = 30,
        include_home: bool = False,
    ):
        self.project_root = project_root.resolve()
        self.storage_root = storage_root.resolve()
        self.skills_dir: Optional[Path] = None
        self.extra_skills_dirs = [self.storage_root / "skills"]
        self.refresh_interval_seconds = max(1, int(refresh_interval_seconds))
        self.include_home = include_home
        self._last_refresh_at = 0.0
        self._status: Optional[Dict[str, Any]] = None

    @property
    def registry_path(self) -> Path:
        return self.storage_root / "skill_sync" / "registry.json"

    def refresh(self, *, force: bool = False) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        records = discover_skill_records(
            self.project_root,
            skills_dir=self.skills_dir,
            extra_skills_dirs=self.extra_skills_dirs,
            include_home=self.include_home,
        )
        manifest = build_skill_sync_manifest(records)
        signature = skill_sync_signature(manifest)
        previous_signature = None
        if self._status:
            previous_signature = self._status.get("registry", {}).get("signature")
        elif self.registry_path.exists():
            try:
                previous = json.loads(self.registry_path.read_text(encoding="utf-8"))
                previous_signature = previous.get("registry", {}).get("signature")
            except (OSError, json.JSONDecodeError):
                previous_signature = None
        export_plan = build_skill_export_plan(
            self.project_root,
            skills_dir=self.skills_dir,
            extra_skills_dirs=self.extra_skills_dirs,
            records=records,
            manifest=manifest,
        )
        skill_graph = build_dynamic_skill_graph(
            self.project_root,
            skills_dir=self.skills_dir,
            extra_skills_dirs=self.extra_skills_dirs,
            records=records,
            manifest=manifest,
            export_plan=export_plan,
        )
        status = {
            "registry": {
                "generated_at": now.isoformat(),
                "refresh_interval_seconds": self.refresh_interval_seconds,
                "force": force,
                "state": "conflicts" if manifest["summary"]["total_conflicts"] else "ok",
                "signature": signature,
                "previous_signature": previous_signature,
                "changed": previous_signature is not None and previous_signature != signature,
                "registry_path": str(self.registry_path),
            },
            "manifest": manifest,
            "export_plan": export_plan,
            "skill_graph": skill_graph,
        }
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        write_skill_sync_manifest(self.project_root, manifest, output_path=self.storage_root / "skill_sync" / "manifest.json")
        self._status = status
        self._last_refresh_at = now.timestamp()
        return status

    def status(self, *, force: bool = False) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).timestamp()
        stale = (now - self._last_refresh_at) >= self.refresh_interval_seconds
        if force or self._status is None or stale:
            return self.refresh(force=force)
        return self._status
