"""Audit TTMEvolve release readiness from local evidence.

This is a no-network gate. It verifies concrete local artifacts and keeps
unproven release claims explicit instead of treating missing evidence as pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.package_release import validate_archive_entries

DEFAULT_PACKAGE = PROJECT_ROOT / "release-artifacts" / "TTMEvolve-source-v0.4.5-one-click-practice-entry.zip"
SOURCE_CHECKPOINT_MODE = "source-checkpoint"
FULL_OFFLINE_MODE = "full-offline"
RELEASE_MODES = (SOURCE_CHECKPOINT_MODE, FULL_OFFLINE_MODE)
MODE_REQUIRED_CHECKS = {
    SOURCE_CHECKPOINT_MODE: (
        "source_package",
        "launch_surface",
        "release_artifacts_ignored",
    ),
    FULL_OFFLINE_MODE: (
        "source_package",
        "launch_surface",
        "release_artifacts_ignored",
        "offline_runtime_bundle",
        "signed_installer",
        "maker_remote_build",
        "production_rag_quality",
    ),
}

PRIVATE_PROBES = [
    "config.json",
    ".env",
    ".env.embedded",
    ".mcp.json",
    "storage/",
    "portable/",
    "vendor/",
    "models/",
    "workspace/",
    "src-tauri/target/",
    "node_modules/",
    "release-artifacts/",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(ok: bool, status: str, message: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": ok, "status": status, "message": message}
    result.update(extra)
    return result


def _probe_hits(entries: Iterable[str]) -> Dict[str, List[str]]:
    names = list(entries)
    hits: Dict[str, List[str]] = {}
    for probe in PRIVATE_PROBES:
        matched = [name for name in names if name == probe.rstrip("/") or name.startswith(probe)]
        if matched:
            hits[probe] = matched[:10]
    return hits


def audit_source_package(package_path: Path) -> Dict[str, Any]:
    manifest_path = package_path.with_suffix(package_path.suffix + ".manifest.json")
    if not package_path.exists():
        return _check(False, "blocked", f"source package missing: {package_path}")
    if not manifest_path.exists():
        return _check(False, "blocked", f"source package manifest missing: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _check(False, "blocked", f"manifest is not readable JSON: {exc}")

    try:
        with zipfile.ZipFile(package_path) as zf:
            entries = zf.namelist()
    except Exception as exc:
        return _check(False, "blocked", f"source package is not a readable zip: {exc}")

    forbidden = validate_archive_entries(entries)
    hits = _probe_hits(entries)
    actual_sha = _sha256(package_path)
    actual_size = package_path.stat().st_size
    manifest_mismatches = []
    if manifest.get("file_count") != len(entries):
        manifest_mismatches.append("file_count")
    if manifest.get("size_bytes") != actual_size:
        manifest_mismatches.append("size_bytes")
    if manifest.get("sha256") != actual_sha:
        manifest_mismatches.append("sha256")
    if manifest.get("forbidden_entries") not in ([], None):
        manifest_mismatches.append("forbidden_entries")

    ok = not forbidden and not hits and not manifest_mismatches
    return _check(
        ok,
        "ready" if ok else "blocked",
        "source package audit passed" if ok else "source package audit failed",
        package=str(package_path),
        manifest=str(manifest_path),
        file_count=len(entries),
        size_bytes=actual_size,
        sha256=actual_sha,
        forbidden_count=len(forbidden),
        forbidden_preview=forbidden[:10],
        probe_hits=hits,
        manifest_mismatches=manifest_mismatches,
    )


def audit_launch_surface(project_root: Path) -> Dict[str, Any]:
    required = [
        project_root / "TTMEvolve.vbs",
        project_root / "TTMEvolve-Practice.vbs",
        project_root / "start-tauri.bat",
        project_root / "src-tauri" / "target" / "release" / "ttmevolve.exe",
        project_root / "vendor" / "python" / "python.exe",
    ]
    missing = [str(path) for path in required if not path.exists()]
    return _check(
        not missing,
        "ready" if not missing else "blocked",
        "visible launch surface is present" if not missing else "visible launch surface is incomplete",
        missing=missing,
        checked=[str(path) for path in required],
    )


def audit_git_artifacts_ignored(project_root: Path) -> Dict[str, Any]:
    release_dir = project_root / "release-artifacts"
    if not release_dir.exists():
        return _check(False, "blocked", f"release artifact directory missing: {release_dir}")
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(release_dir)],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return _check(
        result.returncode == 0,
        "ready" if result.returncode == 0 else "blocked",
        "release-artifacts is git-ignored" if result.returncode == 0 else "release-artifacts is not git-ignored",
        path=str(release_dir),
    )


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def audit_offline_runtime_bundle(project_root: Path, *, max_budget_mb: int = 500) -> Dict[str, Any]:
    vendor = project_root / "vendor"
    python_exe = vendor / "python" / ("python.exe" if sys.platform.startswith("win") else "bin/python3")
    node_exe = vendor / "node" / ("node.exe" if sys.platform.startswith("win") else "bin/node")
    site_packages = vendor / "python" / ("Lib/site-packages" if sys.platform.startswith("win") else "lib")
    size_bytes = _dir_size(vendor)
    budget_bytes = max_budget_mb * 1024 * 1024
    failures: List[str] = []
    warnings: List[str] = []

    if not vendor.exists():
        failures.append(f"vendor directory missing: {vendor}")
    if not python_exe.exists():
        failures.append(f"vendor Python missing: {python_exe}")
    if python_exe.exists() and not site_packages.exists():
        failures.append(f"vendor site-packages missing: {site_packages}")
    if not node_exe.exists():
        warnings.append(f"vendor Node missing: {node_exe}")
    if size_bytes == 0:
        failures.append("vendor directory is empty")
    elif size_bytes > budget_bytes:
        failures.append(
            f"vendor size {size_bytes / (1024 * 1024):.1f}MB exceeds budget {max_budget_mb}MB"
        )

    return _check(
        not failures,
        "ready" if not failures else "blocked",
        "offline runtime bundle audit passed" if not failures else "offline runtime bundle audit failed",
        vendor_root=str(vendor),
        python=str(python_exe),
        node=str(node_exe),
        site_packages=str(site_packages),
        size_bytes=size_bytes,
        budget_bytes=budget_bytes,
        failures=failures,
        warnings=warnings,
    )


def build_release_readiness_report(
    *,
    project_root: Path = PROJECT_ROOT,
    package_path: Optional[Path] = None,
    mode: str = FULL_OFFLINE_MODE,
) -> Dict[str, Any]:
    if mode not in RELEASE_MODES:
        raise ValueError(f"unsupported release readiness mode: {mode}")
    package = (package_path or DEFAULT_PACKAGE).resolve()
    checks = {
        "source_package": audit_source_package(package),
        "launch_surface": audit_launch_surface(project_root),
        "release_artifacts_ignored": audit_git_artifacts_ignored(project_root),
        "offline_runtime_bundle": audit_offline_runtime_bundle(project_root),
        "signed_installer": _check(
            False,
            "unproven",
            "signed installer artifacts are not claimed by the source checkpoint",
        ),
        "maker_remote_build": _check(
            False,
            "unproven",
            "Maker remote build side-effect smoke has not been proven by this audit",
        ),
        "production_rag_quality": _check(
            False,
            "unproven",
            "production RAG semantic quality needs a real golden corpus and embedding artifact",
        ),
    }
    required_checks = list(MODE_REQUIRED_CHECKS[mode])
    informational_checks = [key for key in checks if key not in required_checks]
    blocker_ids = [
        key for key in required_checks if checks[key]["status"] == "blocked"
    ]
    unproven_ids = [
        key for key in required_checks if checks[key]["status"] == "unproven"
    ]
    out_of_scope = {
        key: checks[key]["status"]
        for key in informational_checks
        if checks[key]["status"] in {"blocked", "unproven"}
    }
    return {
        "version": "release-readiness.v1",
        "mode": mode,
        "status": "blocked" if blocker_ids else "partial" if unproven_ids else "ready",
        "project_root": str(project_root),
        "package": str(package),
        "checks": checks,
        "required_checks": required_checks,
        "informational_checks": informational_checks,
        "blockers": blocker_ids,
        "unproven": unproven_ids,
        "out_of_scope": out_of_scope,
        "closure_gate": {
            "can_claim_source_checkpoint_ready": checks["source_package"]["ok"]
            and checks["launch_surface"]["ok"]
            and checks["release_artifacts_ignored"]["ok"],
            "can_claim_full_publishable_release": all(
                checks[key]["status"] == "ready"
                for key in MODE_REQUIRED_CHECKS[FULL_OFFLINE_MODE]
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TTMEvolve release readiness")
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE, help="source release zip to audit")
    parser.add_argument(
        "--mode",
        choices=RELEASE_MODES,
        default=FULL_OFFLINE_MODE,
        help="claim level to gate: source-checkpoint or full-offline",
    )
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    args = parser.parse_args()

    report = build_release_readiness_report(package_path=args.package, mode=args.mode)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"release readiness ({report['mode']}): {report['status']}")
        for name, check in report["checks"].items():
            scope = "required" if name in report["required_checks"] else "informational"
            print(f"- {name}: {check['status']} ({scope}) - {check['message']}")
        print(f"closure_gate: {report['closure_gate']}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
