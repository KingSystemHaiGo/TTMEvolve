"""sign-windows — code-sign Windows installers with signtool.

Usage:
    python scripts/build_portable/build_sign_windows.py \\
        --pfx path/to/cert.pfx \\
        --artifacts-dir src-tauri/target/release/bundle

Requires:
- signtool.exe (in Windows SDK; PATH or %WINDOWSSDKDIR%)
- A valid code-signing certificate (.pfx)
- Optional: TTM_PFX_PASSWORD env var

Behavior:
1. Recursively finds *.exe and *.msi in the artifacts dir.
2. Calls signtool sign with the certificate.
3. Verifies the signature with signtool verify.
4. Returns non-zero if any artifact fails to sign.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


SIGNTOOL_CANDIDATES = [
    "signtool.exe",
    r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
    r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe",
]


def _resolve_signtool() -> str:
    for candidate in SIGNTOOL_CANDIDATES:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    raise FileNotFoundError("signtool.exe not found in PATH or known SDK locations")


def _find_artifacts(root: Path) -> List[Path]:
    """Find exe and msi artifacts under root."""
    if not root.exists():
        return []
    patterns = ("*.exe", "*.msi")
    found: List[Path] = []
    for pattern in patterns:
        found.extend(root.rglob(pattern))
    return sorted(set(found))


def _sign(signtool: str, pfx: str, password: str, target: Path) -> bool:
    cmd = [
        signtool, "sign",
        "/f", pfx,
        "/p", password,
        "/fd", "SHA256",
        "/tr", "http://timestamp.digicert.com",
        "/td", "sha256",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _verify(signtool: str, target: Path) -> bool:
    cmd = [signtool, "verify", "/pa", str(target)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def main(args=None) -> int:
    parser = argparse.ArgumentParser(description="Sign Windows installers with signtool")
    parser.add_argument("--pfx", required=True, help="Path to .pfx certificate")
    parser.add_argument(
        "--pfx-password",
        default=None,
        help="Password for the .pfx (falls back to TTM_PFX_PASSWORD)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="src-tauri/target/release/bundle",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing signtool",
    )
    parsed = parser.parse_args(args)
    password = parsed.pfx_password or os.environ.get("TTM_PFX_PASSWORD", "")
    if not password:
        print("[sign-windows] ERROR: --pfx-password or TTM_PFX_PASSWORD is required")
        return 2

    artifacts = _find_artifacts(Path(parsed.artifacts_dir))
    if not artifacts:
        print(f"[sign-windows] no artifacts in {parsed.artifacts_dir}")
        return 0

    if parsed.dry_run:
        for art in artifacts:
            print(f"[sign-windows] (dry-run) would sign: {art}")
        return 0

    signtool = _resolve_signtool()
    failures = 0
    for art in artifacts:
        print(f"[sign-windows] signing: {art.name}")
        if not _sign(signtool, parsed.pfx, password, art):
            failures += 1
            print(f"[sign-windows] FAIL: {art.name}")
            continue
        if not _verify(signtool, art):
            failures += 1
            print(f"[sign-windows] verify FAIL: {art.name}")
            continue
        print(f"[sign-windows] OK: {art.name}")
    print(f"[sign-windows] signed {len(artifacts) - failures}/{len(artifacts)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())