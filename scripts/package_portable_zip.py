"""package_portable_zip.py — Build a self-contained TTMEvolve v1.0.0 zip.

Bundles: Tauri release exe + vendor/ embedded runtime + models/ (if present)
+ launchers + minimal user-facing docs.

Usage:
    python scripts/package_portable_zip.py
    python scripts/package_portable_zip.py --output release-artifacts/TTMEvolve-v1.0.0-windows-x64.zip
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

# Paths that are NEVER included (same exclusions as package_release.py,
# except vendor/python, vendor/node, vendor/git, vendor/wheels, vendor/playwright
# which ARE included; embeddings and models are excluded — user downloads on demand)
BANNED_ARCHIVE_PREFIXES = {
    ".agents/",
    ".claude/",
    ".codex/",
    ".cursor/",
    ".git/",
    ".pytest_cache/",
    ".tmp/",
    ".ttmevolve/",
    ".venv/",
    "__pycache__/",
    "build/",
    "dist/",
    "electron/dist/",
    "frontend/dist/",
    "logs/",
    "node_modules/",
    "portable/",
    "release-artifacts/",
    "src-tauri/gen/",
    "src-tauri/target/",
    "storage/",
    "test_project/",
    "models/",                # GGUF model excluded — API-first, download on demand
    "vendor/",                # vendor/ root banned; specific subdirs re-enabled via _is_vendor_included
    "workspace/",
    "venv/",
    # Nested paths that are always banned even within vendor
    "src-tauri/target/release/vendor/",   # Tauri build intermediate output
}

# Sub-paths of vendor/ that ARE included in the portable zip
# Note: playwright (683MB Chromium) is EXCLUDED — user runs prepare_offline_env.py if needed
VENDOR_INCLUDED_SUBDIRS = {
    "vendor/python",
    "vendor/node",
    "vendor/git",
    "vendor/wheels",
}

BANNED_ARCHIVE_NAMES = {
    ".env",
    ".mcp.json",
    "config.json",
    "AGENT.md",
    "AGENTS.md",
}

# Files always included (minimal surface)
ALWAYS_INCLUDED = {
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "CHANGELOG.md",
    "requirements.txt",
    "config.example.json",
    "start.bat",
    "start.sh",
    "start-tauri.bat",
    "start-tauri.sh",
    "TTMEvolve.vbs",
    "TTMEvolve-Practice.vbs",
    # Tauri release binary
    "src-tauri/target/release/ttmevolve.exe",
}

# Directories always included
ALWAYS_INCLUDED_DIRS = {
    "core",
    "agent",
    "llm",
    "learning",
    "server",
    "memory",
    "ecosystem",
    "cli",
    "main.py",
    "gui.py",
}

EXCLUDED_FILE_PATTERNS = {
    "*.7z",
    "*.lnk",
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


def _as_posix(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def _is_banned(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    name = Path(rel_path).name
    if rel_path in BANNED_ARCHIVE_NAMES or name.startswith(".env"):
        return True
    if ".maker-mcp" in parts:
        return True
    for prefix in BANNED_ARCHIVE_PREFIXES:
        if rel_path == prefix.rstrip("/") or rel_path.startswith(prefix):
            return True
    return False


def _is_vendor_included(rel_path: str) -> bool:
    """Check if rel_path is an allowed sub-path of vendor/."""
    rel = _as_posix(rel_path)
    # Exact match
    if rel in VENDOR_INCLUDED_SUBDIRS:
        return True
    # Child of an included subdir
    for subdir in VENDOR_INCLUDED_SUBDIRS:
        if rel.startswith(subdir + "/"):
            return True
    return False


def _should_include(rel_path: str, is_dir: bool) -> bool:
    rel = _as_posix(rel_path)
    path = Path(rel)
    parts = path.parts

    # 0. Special cases first (before BANNED_PREFIXES)
    # Tauri release exe — must be included even though parent dir is banned
    if rel.endswith("/ttmevolve.exe") or rel == "src-tauri/target/release/ttmevolve.exe":
        return True
    # Allow traversal of src-tauri/target/ to reach ttmevolve.exe
    if is_dir and rel in ("src-tauri/target", "src-tauri/target/release"):
        return True

    # 1. Always ban .maker-mcp and config files
    if ".maker-mcp" in parts or path.name in BANNED_ARCHIVE_NAMES:
        return False
    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(path.name, pattern):
            return False

    # 2. vendor/ special case:
    #    - as a directory: vendor/ root = allow traversal; vendor/X/ = only if in VENDOR_INCLUDED_SUBDIRS
    #    - as a file: only include if inside VENDOR_INCLUDED_SUBDIRS
    vendor_p = _as_posix("vendor")
    if rel == vendor_p:
        # vendor/ root: allow traversal (return True for is_dir) but don't include the dir entry itself
        return True
    if rel.startswith(vendor_p + "/"):
        if is_dir:
            return _is_vendor_included(rel)
        else:
            return _is_vendor_included(rel)

    # 2. All other BANNED prefixes
    for prefix in BANNED_ARCHIVE_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            return False

    # 3. Directory-level fast-filters
    if is_dir:
        return True

    # 4. Always-included surface files / dirs
    if path.name in ALWAYS_INCLUDED or rel in ALWAYS_INCLUDED:
        return True
    if any(d in parts for d in ALWAYS_INCLUDED_DIRS):
        return True

    return True


def iter_bundle_files(project_root: Path = _PROJECT_ROOT) -> List[Path]:
    included: List[Path] = []
    for root, dirs, files in os.walk(project_root):
        root_path = Path(root)
        rel_root = root_path.relative_to(project_root)

        # Always skip node_modules and __pycache__ at the walk level
        dirs[:] = [
            d for d in dirs
            if d not in ("node_modules", "__pycache__", "electron", "frontend")
            and _should_include(str(rel_root / d), True)
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
        # Tauri exe always allowed
        if entry.endswith("/ttmevolve.exe") or entry == "src-tauri/target/release/ttmevolve.exe":
            continue
        if ".maker-mcp" in parts or name in BANNED_ARCHIVE_NAMES or name.startswith(".env"):
            forbidden.append(entry)
            continue
        for pattern in EXCLUDED_FILE_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                forbidden.append(entry)
                break
        else:
            # vendor/ special case: use _is_vendor_included
            vendor_p = _as_posix("vendor")
            if entry == vendor_p or entry.startswith(vendor_p + "/"):
                if not _is_vendor_included(entry):
                    forbidden.append(entry)
                continue
            # Other banned prefixes
            for prefix in BANNED_ARCHIVE_PREFIXES:
                if entry == prefix.rstrip("/") or entry.startswith(prefix):
                    forbidden.append(entry)
                    break
    return forbidden


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(output: Path, entries: List[str], forbidden: List[str]) -> Path:
    actual_sha = _sha256(output)
    actual_size = output.stat().st_size
    manifest = {
        "package": output.name,
        "sha256": actual_sha,
        "size_bytes": actual_size,
        "file_count": len(entries),
        "forbidden_entries": forbidden,
        "excluded_path_prefixes": sorted(BANNED_ARCHIVE_PREFIXES),
        "note": "Self-contained v1.0.0 zip; vendor/ and models/ included if present at bundle time.",
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def package_portable_zip(output: Optional[Path] = None, *, dry_run: bool = False) -> Path:
    version = "1.0.0"
    if output is None:
        output = _PROJECT_ROOT / "release-artifacts" / f"TTMEvolve-v{version}-windows-x64.zip"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"[package] Building portable zip: {output}")
    print(f"[package] Project root: {_PROJECT_ROOT}")

    # Check vendor/ and models/ presence
    vendor_exists = (_PROJECT_ROOT / "vendor").exists()
    models_exists = (_PROJECT_ROOT / "models").exists()
    print(f"[package] vendor/ present: {vendor_exists}")
    print(f"[package] models/ present: {models_exists}")

    # Tauri exe check
    tauri_exe = _PROJECT_ROOT / "src-tauri" / "target" / "release" / "ttmevolve.exe"
    if not tauri_exe.exists():
        raise RuntimeError(f"Tauri exe not found: {tauri_exe}. Run 'cargo build --release' first.")

    manifest_output = output.with_suffix(output.suffix + ".manifest.json")
    files = [
        rel for rel in iter_bundle_files(_PROJECT_ROOT)
        if (_PROJECT_ROOT / rel).resolve() not in {output, manifest_output}
    ]
    entries = [_as_posix(rel) for rel in files]
    forbidden = validate_archive_entries(entries)
    if forbidden:
        preview = ", ".join(forbidden[:10])
        raise RuntimeError(f"bundle would include forbidden entries: {preview}")

    if dry_run:
        print(f"[package] Dry run: {len(files)} files would be added")
        for f in files[:20]:
            print(f"  + {f}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
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
        raise RuntimeError(f"bundle included forbidden entries: {preview}")

    manifest_path = _write_manifest(output, archive_entries, forbidden)

    size_mb = output.stat().st_size / 1024 / 1024
    print(f"[package] Done: {included} files, {size_mb:.1f} MB -> {output}")
    print(f"[package] Manifest: {manifest_path}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Package TTMEvolve self-contained portable zip")
    parser.add_argument("--output", type=Path, help="output zip path")
    parser.add_argument("--dry-run", action="store_true", help="list files without writing zip")
    args = parser.parse_args()

    try:
        package_portable_zip(args.output, dry_run=args.dry_run)
        return 0
    except RuntimeError as e:
        print(f"[package] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
