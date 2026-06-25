"""Auto-update client — Python wrapper around tauri-plugin-updater.

Provides a stable Python-side API for the frontend (or other Python tools)
to query the latest release version, fetch release notes, and compute
update progress — without depending on the upstream plugin's types.

The actual update install + restart is handled by the Tauri shell. This
module only deals with information queries.

Usage:
    from core.updater_client import check_for_update, latest_release

    info = await check_for_update()
    if info.available:
        print(f"New version: {info.latest_version}")
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


UPDATER_CLIENT_VERSION = "updater-client.v1"


GITHUB_RELEASES_URL = os.environ.get(
    "TTM_GITHUB_RELEASES_URL",
    "https://api.github.com/repos/KingSystemHaiGo/TTMEvolve/releases/latest",
)

DEFAULT_CURRENT_VERSION = "0.9.0"


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    available: bool
    release_notes: Optional[str]
    pub_date: Optional[str]
    source: str  # "github" / "fallback"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_semver(version: str) -> tuple:
    """Parse a semver-like string into (numeric_components, is_prerelease).

    The numeric tuple is compared first; if equal, a release (no `-suffix`)
    is considered newer than a prerelease of the same base.
    """
    parts: list = []
    # Drop everything after the first '-' so "1.0.0-rc.1" splits into
    # ["1", "0", "0"] instead of ["1", "0", "0-rc", "1"].
    core = version.split("-", 1)[0]
    for segment in core.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    is_prerelease = "-" in version
    return tuple(parts), is_prerelease


def is_newer_version(latest: str, current: str) -> bool:
    """Return True if `latest` is strictly greater than `current` (semver).

    A prerelease (e.g. "1.0.0-rc.1") is treated as older than its release
    ("1.0.0") so a prerelease never looks newer than its tagged release.
    """
    latest_parts, latest_pre = _parse_semver(latest)
    current_parts, current_pre = _parse_semver(current)
    length = max(len(latest_parts), len(current_parts))
    for i in range(length):
        l = latest_parts[i] if i < len(latest_parts) else 0
        c = current_parts[i] if i < len(current_parts) else 0
        if l > c:
            return True
        if l < c:
            return False
    # Numeric parts equal — a release beats a prerelease of the same base.
    if latest_pre and not current_pre:
        # latest is prerelease, current is release → latest is older → not newer
        return False
    if not latest_pre and current_pre:
        # latest is release, current is prerelease → latest is newer
        return True
    return False


def summarize_release(notes: Optional[str], max_lines: int = 5) -> str:
    """Trim release notes to a short summary."""
    if notes is None:
        return "(no release notes provided)"
    lines = notes.splitlines()[:max_lines]
    if not lines:
        return "(empty release notes)"
    return "\n".join(lines)


def percent_complete(downloaded_bytes: int, total_bytes: int) -> float:
    """Compute percent complete (0-100)."""
    if total_bytes == 0:
        return 0.0
    pct = max(0.0, min(1.0, downloaded_bytes / total_bytes))
    return round(pct * 100.0, 2)


def _fetch_github_release() -> Optional[Dict[str, Any]]:
    """Hit GitHub Releases API. Returns the JSON payload or None on failure."""
    request = urllib.request.Request(
        GITHUB_RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "TTMEvolve-Updater/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def latest_release(*, current_version: str = DEFAULT_CURRENT_VERSION) -> UpdateInfo:
    """Fetch the latest release info and compare to `current_version`."""
    payload = _fetch_github_release()
    if payload is None:
        return UpdateInfo(
            current_version=current_version,
            latest_version=current_version,
            available=False,
            release_notes=None,
            pub_date=None,
            source="fallback",
        )
    latest_tag = payload.get("tag_name", "")
    # Strip leading 'v' from tag like "v1.0.0".
    if latest_tag.startswith("v"):
        latest_tag = latest_tag[1:]
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_tag or current_version,
        available=is_newer_version(latest_tag, current_version),
        release_notes=payload.get("body"),
        pub_date=payload.get("published_at"),
        source="github",
    )


def check_for_update(*, current_version: str = DEFAULT_CURRENT_VERSION) -> UpdateInfo:
    """Same as latest_release — kept as an explicit verb for the frontend."""
    return latest_release(current_version=current_version)


def release_card(info: UpdateInfo, *, max_lines: int = 5) -> str:
    """Render an UpdateInfo as a UI card text."""
    lines = ["# Update Status"]
    lines.append(f"\nCurrent: {info.current_version}")
    lines.append(f"Latest:  {info.latest_version}")
    lines.append(f"Available: {'yes' if info.available else 'no'}")
    lines.append(f"Source: {info.source}")
    if info.pub_date:
        lines.append(f"\nPublished: {info.pub_date}")
    if info.release_notes:
        lines.append("\nRelease Notes:")
        lines.append(summarize_release(info.release_notes, max_lines))
    return "\n".join(lines)