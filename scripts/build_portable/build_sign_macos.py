"""sign-macos — code-sign and notarize macOS bundles.

Usage:
    python scripts/build_portable/build_sign_macos.py \\
        --identity "Developer ID Application: Your Name (TEAMID)" \\
        --artifacts-dir src-tauri/target/release/bundle

Requires (macOS only):
- Xcode Command Line Tools (codesign, xcrun)
- An Apple Developer ID certificate in your login keychain
- An app-specific password stored as TTM_APPLE_APP_PASSWORD (for notarytool)

Behavior:
1. Recursively finds .app and .dmg artifacts.
2. codesign --deep --force --options runtime --timestamp
3. Submits to notarytool for notarization.
4. Staples the notarization ticket to the bundle.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


def _find_bundles(root: Path) -> List[Path]:
    if not root.exists():
        return []
    found: List[Path] = []
    found.extend(root.rglob("*.app"))
    found.extend(root.rglob("*.dmg"))
    return sorted(set(found))


def _codesign(identity: str, bundle: Path) -> bool:
    cmd = [
        "codesign",
        "--deep",
        "--force",
        "--options", "runtime",
        "--timestamp",
        "--sign", identity,
        str(bundle),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _notarize(bundle: Path, apple_id: str, team_id: str, password: str) -> bool:
    cmd = [
        "xcrun", "notarytool", "submit",
        str(bundle),
        "--apple-id", apple_id,
        "--team-id", team_id,
        "--password", password,
        "--wait",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        return False
    # Staple the ticket to the bundle so Gatekeeper accepts it offline.
    staple = subprocess.run(
        ["xcrun", "stapler", "staple", str(bundle)],
        capture_output=True,
        text=True,
    )
    return staple.returncode == 0


def main(args=None) -> int:
    parser = argparse.ArgumentParser(description="Sign + notarize macOS bundles")
    parser.add_argument(
        "--identity",
        required=True,
        help="Developer ID identity (e.g. 'Developer ID Application: Name (TEAMID)')",
    )
    parser.add_argument(
        "--apple-id",
        help="Apple ID email (falls back to TTM_APPLE_ID)",
    )
    parser.add_argument(
        "--team-id",
        help="Apple team ID (falls back to TTM_APPLE_TEAM_ID)",
    )
    parser.add_argument(
        "--app-password",
        help="App-specific password (falls back to TTM_APPLE_APP_PASSWORD)",
    )
    parser.add_argument(
        "--keychain",
        default="login",
        help="Keychain to use (default: login)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="src-tauri/target/release/bundle/macos",
    )
    parser.add_argument(
        "--skip-notarize",
        action="store_true",
        help="Only code-sign, skip notarytool submission",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing",
    )
    parsed = parser.parse_args(args)
    if not parsed.dry_run and not parsed.skip_notarize:
        if not (parsed.apple_id or os.environ.get("TTM_APPLE_ID")):
            print("[sign-macos] ERROR: --apple-id or TTM_APPLE_ID required for notarization")
            return 2

    bundles = _find_bundles(Path(parsed.artifacts_dir))
    if not bundles:
        print(f"[sign-macos] no bundles in {parsed.artifacts_dir}")
        return 0

    if parsed.dry_run:
        for bundle in bundles:
            print(f"[sign-macos] (dry-run) would sign: {bundle}")
        return 0

    # Use the login keychain by default; the developer is expected to have
    # already added the cert via Keychain Access.
    identity = parsed.identity
    apple_id = parsed.apple_id or os.environ.get("TTM_APPLE_ID", "")
    team_id = parsed.team_id or os.environ.get("TTM_APPLE_TEAM_ID", "")
    password = parsed.app_password or os.environ.get("TTM_APPLE_APP_PASSWORD", "")

    failures = 0
    for bundle in bundles:
        print(f"[sign-macos] signing: {bundle.name}")
        if not _codesign(identity, bundle):
            failures += 1
            print(f"[sign-macos] codesign FAIL: {bundle.name}")
            continue
        if not parsed.skip_notarize:
            print(f"[sign-macos] notarizing: {bundle.name}")
            if not _notarize(bundle, apple_id, team_id, password):
                failures += 1
                print(f"[sign-macos] notarize FAIL: {bundle.name}")
                continue
        print(f"[sign-macos] OK: {bundle.name}")
    print(f"[sign-macos] signed {len(bundles) - failures}/{len(bundles)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())