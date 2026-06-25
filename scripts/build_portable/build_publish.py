"""publish — upload signed artifacts to GitHub Releases.

Usage:
    python scripts/build_portable/build_publish.py \\
        --repo KingSystemHaiGo/TTMEvolve \\
        --tag v1.0.0 \\
        --artifacts-dir src-tauri/target/release/bundle

Requires:
- gh (GitHub CLI) on PATH and authenticated, OR
- GITHUB_TOKEN env var + curl, OR
- curl + jq for manual upload

Behavior:
1. Reads artifacts dir; filters by signed extensions.
2. Optionally generates release notes from docs/releases/<tag>.md.
3. Creates the GitHub release (or updates an existing one).
4. Uploads each artifact.

By default this script is a no-op orchestrator: it prints the planned
actions and exits 0 unless --apply is passed. Use --apply in CI.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


SIGNED_EXTENSIONS = (".exe", ".msi", ".deb", ".AppImage", ".rpm", ".dmg", ".zip")


def _find_signed(artifacts_dir: Path) -> List[Path]:
    if not artifacts_dir.exists():
        return []
    found: List[Path] = []
    for ext in SIGNED_EXTENSIONS:
        found.extend(artifacts_dir.rglob(f"*{ext}"))
    return sorted(set(found))


def _gh_release_create(
    repo: str,
    tag: str,
    title: str,
    notes_file: Path,
    artifacts: List[Path],
) -> bool:
    if not shutil.which("gh"):
        print("[publish] gh CLI not found; skipping release creation")
        return False
    cmd = [
        "gh", "release", "create", tag,
        "--repo", repo,
        "--title", title,
        "--notes-file", str(notes_file),
    ]
    for art in artifacts:
        cmd.append(str(art))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _read_release_notes(tag: str) -> str:
    """Read release notes from docs/releases/<tag>.md or fall back."""
    candidates = [
        Path(f"docs/releases/{tag}-grand-release.md"),
        Path(f"docs/releases/{tag}-release.md"),
        Path(f"docs/releases/{tag}.md"),
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return f"# Release {tag}\n\nSee docs/releases for the changelog."


def main(args=None) -> int:
    parser = argparse.ArgumentParser(description="Publish signed artifacts to GitHub Releases")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/name)")
    parser.add_argument("--tag", required=True, help="Release tag (e.g. v1.0.0)")
    parser.add_argument(
        "--title",
        default=None,
        help="Release title (defaults to 'Release <tag>')",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="src-tauri/target/release/bundle",
    )
    parser.add_argument(
        "--notes-file",
        default=None,
        help="Markdown file with release notes (defaults to docs/releases/<tag>*.md)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create the release (default: dry-run)",
    )
    parsed = parser.parse_args(args)

    artifacts = _find_signed(Path(parsed.artifacts_dir))
    if not artifacts:
        print(f"[publish] no signed artifacts in {parsed.artifacts_dir}")
        return 0

    title = parsed.title or f"Release {parsed.tag}"
    notes_file = Path(parsed.notes_file) if parsed.notes_file else None

    print(f"[publish] repo: {parsed.repo}")
    print(f"[publish] tag:  {parsed.tag}")
    print(f"[publish] title: {title}")
    print(f"[publish] artifacts ({len(artifacts)}):")
    for art in artifacts:
        print(f"  - {art.name} ({art.stat().st_size // 1024}KB)")

    if not parsed.apply:
        print("[publish] dry-run — pass --apply to upload")
        return 0

    # Write the notes file if a default exists in docs/.
    if notes_file is None:
        notes = _read_release_notes(parsed.tag)
        notes_file = Path("docs") / f"_publish-{parsed.tag}.md"
        notes_file.write_text(notes, encoding="utf-8")
        print(f"[publish] wrote notes to {notes_file}")

    return 0 if _gh_release_create(
        parsed.repo, parsed.tag, title, notes_file, artifacts,
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())