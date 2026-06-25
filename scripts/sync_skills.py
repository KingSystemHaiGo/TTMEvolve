from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ecosystem.skill_sync import (
    SkillSyncRegistry,
    apply_skill_export_plan,
    build_skill_sync_manifest,
    build_skill_export_plan,
    discover_skill_records,
    write_skill_sync_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a cross-agent skill sync manifest.")
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--skills-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--include-home", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true", help="Exit 2 when conflicts are detected.")
    parser.add_argument("--registry", action="store_true", help="Refresh and print storage/skill_sync/registry.json.")
    parser.add_argument("--export-plan", action="store_true", help="Include a safe export plan for canonical skills.")
    parser.add_argument("--apply-exports", action="store_true", help="Write non-reviewed export actions from the export plan.")
    parser.add_argument("--allow-review-actions", action="store_true", help="Also apply actions marked needs_review.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    skills_dir = Path(args.skills_dir).resolve() if args.skills_dir else None
    storage_root = (skills_dir.parent if skills_dir else project_root / "storage").resolve()
    if args.registry:
        registry = SkillSyncRegistry(
            project_root,
            storage_root,
            include_home=args.include_home,
        )
        payload = registry.refresh(force=True)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.check and payload["manifest"].get("conflicts"):
            return 2
        return 0

    records = discover_skill_records(
        project_root,
        skills_dir=skills_dir,
        include_home=args.include_home,
    )
    manifest = build_skill_sync_manifest(records)
    payload = manifest
    export_plan = None
    if args.export_plan or args.apply_exports:
        export_plan = build_skill_export_plan(
            project_root,
            skills_dir=skills_dir,
            records=records,
            manifest=manifest,
        )
        payload = {"manifest": manifest, "export_plan": export_plan}
    if args.write:
        output_path = Path(args.output).resolve() if args.output else None
        path = write_skill_sync_manifest(project_root, manifest, output_path=output_path)
        payload["manifest_path"] = str(path)
    if args.apply_exports:
        result = apply_skill_export_plan(
            export_plan or {},
            skills_dir=(skills_dir or project_root / "storage" / "skills").resolve(),
            require_review=not args.allow_review_actions,
            dry_run=False,
        )
        payload["apply_result"] = result
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.check and manifest.get("conflicts"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
