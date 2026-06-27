"""Safely clean generated portable runtime state.

The cleaner removes browser/system caches that can bloat ``portable/home``
while preserving auth and runtime assets. Dry-run is the default.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PROTECTED_RELATIVE_PREFIXES = (
    "portable/home/.taptap-maker",
    "portable/python",
    "portable/node",
    "portable/electron",
    "portable/maker-mcp",
)

CLEAN_TARGETS = (
    "portable/tmp",
    "portable/home/AppData/Local/Temp",
    "portable/home/AppData/LocalLow/NVIDIA/DXCache",
    "portable/home/AppData/LocalLow/SogouPY",
    "portable/home/AppData/LocalLow/SogouPY.users",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/ProvenanceData",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/component_crx_cache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/extensions_crx_cache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/Edge Entity Extraction",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/EdgeLanguageDetectionModel",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/Subresource Filter",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/Default/Cache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/Default/Code Cache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/Default/GPUCache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/GrShaderCache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/ShaderCache",
    "portable/home/AppData/Local/Microsoft/Edge/User Data/OneAuth/WebView2/EBWebView/GrShaderCache",
)

FILE_GLOBS = (
    "portable/home/AppData/Local/Microsoft/Edge/User Data/BrowserMetrics*",
)


@dataclass(frozen=True)
class CleanupEntry:
    path: Path
    kind: str
    size_bytes: int

    def to_json(self, project_root: Path) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": _relative_display(self.path, project_root),
            "kind": self.kind,
            "size_bytes": self.size_bytes,
        }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _dir_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
    return total


def _is_protected(path: Path, project_root: Path) -> bool:
    relative = _relative_display(path, project_root).replace("\\", "/").rstrip("/")
    for prefix in PROTECTED_RELATIVE_PREFIXES:
        clean_prefix = prefix.rstrip("/")
        if relative == clean_prefix or relative.startswith(clean_prefix + "/"):
            return True
    return False


def _resolve_candidate(project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve()
    path = (root / relative_path).resolve()
    portable = (root / "portable").resolve()
    if not _is_relative_to(path, portable):
        raise ValueError(f"cleanup target outside portable/: {path}")
    if _is_protected(path, root):
        raise ValueError(f"cleanup target is protected: {path}")
    return path


def build_cleanup_plan(project_root: Path = PROJECT_ROOT) -> List[CleanupEntry]:
    root = Path(project_root).resolve()
    entries: List[CleanupEntry] = []
    seen: set[Path] = set()

    for relative in CLEAN_TARGETS:
        path = _resolve_candidate(root, relative)
        if path.exists() and path not in seen:
            entries.append(CleanupEntry(path=path, kind="directory", size_bytes=_dir_size(path)))
            seen.add(path)

    for pattern in FILE_GLOBS:
        base = pattern.split("*", 1)[0]
        _resolve_candidate(root, base)
        for path in root.glob(pattern):
            resolved = path.resolve()
            _resolve_candidate(root, _relative_display(resolved, root))
            if resolved.exists() and resolved not in seen:
                kind = "directory" if resolved.is_dir() else "file"
                entries.append(CleanupEntry(path=resolved, kind=kind, size_bytes=_dir_size(resolved)))
                seen.add(resolved)

    entries.sort(key=lambda entry: entry.size_bytes, reverse=True)
    return entries


def apply_cleanup(entries: Iterable[CleanupEntry], *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = Path(project_root).resolve()
    removed: List[dict[str, Any]] = []
    failures: List[dict[str, str]] = []

    for entry in entries:
        try:
            _resolve_candidate(root, _relative_display(entry.path.resolve(), root))
            if _is_protected(entry.path.resolve(), root):
                raise ValueError(f"refusing protected path: {entry.path}")
            if entry.path.is_dir():
                shutil.rmtree(entry.path)
            elif entry.path.exists():
                entry.path.unlink()
            removed.append(entry.to_json(root))
        except Exception as exc:
            failures.append({"path": str(entry.path), "error": str(exc)})

    return {
        "removed": removed,
        "failures": failures,
        "removed_bytes": sum(item["size_bytes"] for item in removed),
    }


def cleanup_report(
    *,
    project_root: Path = PROJECT_ROOT,
    apply: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    entries = build_cleanup_plan(root)
    planned_bytes = sum(entry.size_bytes for entry in entries)
    result = {
        "version": "portable-cleanup.v1",
        "project_root": str(root),
        "mode": "apply" if apply else "dry-run",
        "planned_count": len(entries),
        "planned_bytes": planned_bytes,
        "planned_entries": [entry.to_json(root) for entry in entries],
        "protected_prefixes": list(PROTECTED_RELATIVE_PREFIXES),
        "auth_state_preserved": str(root / "portable" / "home" / ".taptap-maker"),
    }
    if apply:
        result.update(apply_cleanup(entries, project_root=root))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely clean generated portable caches")
    parser.add_argument("--apply", action="store_true", help="delete planned cache entries")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)

    report = cleanup_report(project_root=args.project_root, apply=args.apply)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mb = report["planned_bytes"] / (1024 * 1024)
        print(f"portable cleanup ({report['mode']}): {report['planned_count']} entries, {mb:.1f}MB")
        print(f"auth preserved: {report['auth_state_preserved']}")
        for entry in report["planned_entries"][:20]:
            size_mb = entry["size_bytes"] / (1024 * 1024)
            print(f"- {entry['relative_path']} ({size_mb:.1f}MB)")
        if report.get("failures"):
            print("failures:")
            for failure in report["failures"]:
                print(f"- {failure['path']}: {failure['error']}")
    return 1 if report.get("failures") else 0


if __name__ == "__main__":
    raise SystemExit(main())
