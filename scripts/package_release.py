"""Build an auditable TTMEvolve source release checkpoint.

This packager intentionally excludes local runtime state, private config,
downloaded runtimes, model/vendor caches, workspace assets, and build output.
It is a safe source checkpoint packager; a fully offline distributable runtime
layout is a separate release step.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_PATH_PREFIXES = {
    ".agents",
    ".claude",
    ".codex",
    ".cursor",
    ".git",
    ".pytest_cache",
    ".tmp",
    ".ttmevolve",
    ".venv",
    "build",
    "dist",
    "electron/dist",
    "frontend/dist",
    "logs",
    "models",
    "node_modules",
    "portable",
    "release-artifacts",
    "src-tauri/gen",
    "src-tauri/target",
    "storage",
    "test_project",
    "vendor",
    "venv",
    "workspace",
    "__pycache__",
}

EXCLUDED_ROOT_FILES = {
    ".env.embedded",
    ".mcp.json",
    "config.json",
}

EXCLUDED_FILE_PATTERNS = {
    "*.7z",
    "*.log",
    "*.pyc",
    "*.pyo",
    "*.rar",
    "*.tar",
    "*.tar.gz",
    "*.zip",
    ".env",
    ".env.*",
}

BANNED_ARCHIVE_PREFIXES = {
    ".git/",
    ".venv/",
    "logs/",
    "models/",
    "node_modules/",
    "portable/",
    "release-artifacts/",
    "src-tauri/target/",
    "storage/",
    "vendor/",
    "workspace/",
}

BANNED_ARCHIVE_NAMES = {
    ".env",
    ".mcp.json",
    "config.json",
}


def _load_version() -> str:
    try:
        version_file = _PROJECT_ROOT / "core" / "version_manager.py"
        if version_file.exists():
            text = version_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "VERSION" in line and "=" in line:
                    return line.split("=")[-1].strip().strip('"\'')
    except Exception:
        pass
    try:
        pkg = json.loads((_PROJECT_ROOT / "electron" / "package.json").read_text(encoding="utf-8"))
        return pkg.get("version", "0.4.0")
    except Exception:
        return "0.4.0"


def _as_posix(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def _is_under_prefix(rel_path: str, prefix: str) -> bool:
    rel = _as_posix(rel_path)
    pref = _as_posix(prefix)
    return rel == pref or rel.startswith(f"{pref}/")


def _should_include(rel_path: str, is_dir: bool) -> bool:
    """Return whether a project-relative path belongs in the release zip."""
    rel = _as_posix(rel_path)
    path = Path(rel)

    for prefix in EXCLUDED_PATH_PREFIXES:
        if _is_under_prefix(rel, prefix):
            return False

    if is_dir:
        parts = set(path.parts)
        if "__pycache__" in parts or "node_modules" in parts:
            return False
        return True

    if rel in EXCLUDED_ROOT_FILES:
        return False
    if ".maker-mcp" in path.parts:
        return False
    if path.name.startswith(".env"):
        return False
    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(path.name, pattern):
            return False
    return True


def iter_release_files(project_root: Path = _PROJECT_ROOT) -> List[Path]:
    included: List[Path] = []
    for root, dirs, files in os.walk(project_root):
        root_path = Path(root)
        rel_root = root_path.relative_to(project_root)

        dirs[:] = [
            d for d in dirs
            if _should_include(str(rel_root / d), True)
        ]

        for file in files:
            file_path = root_path / file
            rel_path = file_path.relative_to(project_root)
            if _should_include(str(rel_path), False):
                included.append(rel_path)
    return sorted(included, key=lambda item: _as_posix(item))


def validate_archive_entries(entries: Iterable[str]) -> List[str]:
    forbidden: List[str] = []
    for raw in entries:
        entry = _as_posix(raw)
        parts = Path(entry).parts
        name = Path(entry).name
        if entry in BANNED_ARCHIVE_NAMES or name.startswith(".env"):
            forbidden.append(entry)
            continue
        if ".maker-mcp" in parts:
            forbidden.append(entry)
            continue
        if any(entry.startswith(prefix) for prefix in BANNED_ARCHIVE_PREFIXES):
            forbidden.append(entry)
    return forbidden


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(output: Path, entries: List[str], forbidden: List[str]) -> Path:
    manifest = {
        "package": output.name,
        "sha256": _sha256(output),
        "size_bytes": output.stat().st_size,
        "file_count": len(entries),
        "forbidden_entries": forbidden,
        "excluded_path_prefixes": sorted(EXCLUDED_PATH_PREFIXES),
        "note": "Source checkpoint package; runtime/vendor/model/private state excluded.",
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def package_release(output: Optional[Path] = None, *, dry_run: bool = False) -> Path:
    version = _load_version()
    if output is None:
        output = _PROJECT_ROOT / "release-artifacts" / f"TTMEvolve-source-v{version}.zip"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"[package] Building release: {output}")
    print(f"[package] Project root: {_PROJECT_ROOT}")

    manifest_output = output.with_suffix(output.suffix + ".manifest.json")
    files = [
        rel for rel in iter_release_files(_PROJECT_ROOT)
        if (_PROJECT_ROOT / rel).resolve() not in {output, manifest_output}
    ]
    entries = [_as_posix(rel) for rel in files]
    forbidden = validate_archive_entries(entries)
    if forbidden:
        preview = ", ".join(forbidden[:10])
        raise RuntimeError(f"release package would include forbidden entries: {preview}")

    if dry_run:
        print(f"[package] Dry run: {len(files)} files would be added")
        return output

    included = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in files:
            file_path = _PROJECT_ROOT / rel_path
            arcname = _as_posix(rel_path)
            zf.write(file_path, arcname)
            included += 1
            if included % 1000 == 0:
                print(f"[package] ... {included} files added")

    with zipfile.ZipFile(output) as zf:
        archive_entries = zf.namelist()
    forbidden = validate_archive_entries(archive_entries)
    if forbidden:
        output.unlink(missing_ok=True)
        preview = ", ".join(forbidden[:10])
        raise RuntimeError(f"release package included forbidden entries: {preview}")

    manifest_path = _write_manifest(output, archive_entries, forbidden)

    size_mb = output.stat().st_size / 1024 / 1024
    print(f"[package] Done: {included} files, {size_mb:.1f} MB -> {output}")
    print(f"[package] Manifest: {manifest_path}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Package TTMEvolve source release checkpoint")
    parser.add_argument("--output", type=Path, help="output zip path")
    parser.add_argument("--dry-run", action="store_true", help="list package size without writing zip")
    args = parser.parse_args()

    package_release(args.output, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
