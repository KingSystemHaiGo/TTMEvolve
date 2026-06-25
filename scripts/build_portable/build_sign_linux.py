"""sign-linux — GPG-sign Linux .deb / .AppImage / .rpm artifacts.

Usage:
    python scripts/build_portable/build_sign_linux.py \\
        --gpg-key YOUR_KEY_ID \\
        --artifacts-dir src-tauri/target/release/bundle

Requires:
- gpg on PATH
- A GPG key whose passphrase is in TTM_GPG_PASSPHRASE (or --gpg-passphrase)

Behavior:
1. Recursively finds .deb, .AppImage, .rpm artifacts.
2. Runs gpg --armor --detach-sign for each, producing .asc sidecar files.
3. Optionally creates a sha256sums.txt manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


def _find_artifacts(root: Path) -> List[Path]:
    if not root.exists():
        return []
    found: List[Path] = []
    for pattern in ("*.deb", "*.AppImage", "*.rpm"):
        found.extend(root.rglob(pattern))
    return sorted(set(found))


def _sign(gpg: str, key: str, passphrase: str, target: Path) -> bool:
    sig_path = target.with_suffix(target.suffix + ".asc")
    cmd = [
        gpg,
        "--batch",
        "--yes",
        "--pinentry-mode", "loopback",
        "--armor",
        "--detach-sign",
        "--local-user", key,
        "--passphrase-fd", "0",
        "--output", str(sig_path),
        str(target),
    ]
    result = subprocess.run(
        cmd,
        input=passphrase,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and sig_path.exists()


def _write_manifest(artifacts: List[Path], manifest: Path) -> None:
    lines: List[str] = []
    for art in artifacts:
        sha = hashlib.sha256(art.read_bytes()).hexdigest()
        lines.append(f"{sha}  {art.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(args=None) -> int:
    parser = argparse.ArgumentParser(description="GPG-sign Linux installers")
    parser.add_argument("--gpg-key", required=True, help="GPG key ID (e.g. ABC12345)")
    parser.add_argument(
        "--gpg-passphrase",
        default=None,
        help="GPG passphrase (falls back to TTM_GPG_PASSPHRASE)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="src-tauri/target/release/bundle",
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Also write sha256sums.txt manifest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing gpg",
    )
    parsed = parser.parse_args(args)
    passphrase = parsed.gpg_passphrase or os.environ.get("TTM_GPG_PASSPHRASE", "")
    if not passphrase:
        print("[sign-linux] ERROR: --gpg-passphrase or TTM_GPG_PASSPHRASE required")
        return 2

    artifacts = _find_artifacts(Path(parsed.artifacts_dir))
    if not artifacts:
        print(f"[sign-linux] no artifacts in {parsed.artifacts_dir}")
        return 0

    if parsed.dry_run:
        for art in artifacts:
            print(f"[sign-linux] (dry-run) would sign: {art}")
        return 0

    gpg = shutil.which("gpg") or "gpg"
    failures = 0
    for art in artifacts:
        print(f"[sign-linux] signing: {art.name}")
        if not _sign(gpg, parsed.gpg_key, passphrase, art):
            failures += 1
            print(f"[sign-linux] FAIL: {art.name}")
            continue
        print(f"[sign-linux] OK: {art.name}")
    if parsed.manifest:
        manifest_path = Path(parsed.artifacts_dir) / "sha256sums.txt"
        _write_manifest(artifacts, manifest_path)
        print(f"[sign-linux] manifest: {manifest_path}")
    print(f"[sign-linux] signed {len(artifacts) - failures}/{len(artifacts)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())