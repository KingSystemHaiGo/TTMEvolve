"""build_portable.py — orchestrate all v1.1.0 packaging steps.

Steps:
1. sign-windows — code-sign the Tauri installer with signtool
2. sign-macos   — notarize the .app and .dmg with codesign
3. sign-linux   — GPG-sign the .deb / .AppImage
4. publish      — upload artifacts to GitHub Releases

Each step is an independent script under scripts/build_portable/.

Usage:
    python scripts/build_portable/build_portable.py sign-windows --pfx PATH
    python scripts/build_portable/build_portable.py sign-macos --identity "Developer ID"
    python scripts/build_portable/build_portable.py sign-linux --gpg-key ID
    python scripts/build_portable/build_portable.py publish --repo org/repo --tag v1.0.0

This script is a thin orchestrator — it imports each step's main() and
passes CLI args through. The actual signing logic lives in separate
modules so each platform's flow stays testable in isolation.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_step(name: str):
    """Import a step module by file name."""
    spec = importlib.util.spec_from_file_location(
        f"build_{name}",
        SCRIPTS_DIR / f"build_{name}.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import build step: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STEPS = (
    "sign-windows",
    "sign-macos",
    "sign-linux",
    "publish",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="TTMEvolve packaging orchestrator")
    parser.add_argument(
        "step",
        choices=STEPS,
        help="Which packaging step to run",
    )
    parser.add_argument(
        "--pfx",
        help="Path to .pfx code-signing certificate (Windows)",
    )
    parser.add_argument(
        "--pfx-password",
        help="Password for the .pfx (or use TTM_PFX_PASSWORD env)",
    )
    parser.add_argument(
        "--identity",
        help="Developer ID for macOS code-signing",
    )
    parser.add_argument(
        "--keychain",
        default="login",
        help="macOS keychain profile (default: login)",
    )
    parser.add_argument(
        "--gpg-key",
        help="GPG key ID for Linux signing",
    )
    parser.add_argument(
        "--gpg-passphrase",
        help="GPG passphrase (or use TTM_GPG_PASSPHRASE env)",
    )
    parser.add_argument(
        "--repo",
        help="GitHub repo (owner/name) for the publish step",
    )
    parser.add_argument(
        "--tag",
        help="Release tag (e.g. v1.0.0)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="src-tauri/target/release/bundle",
        help="Directory containing signed installers",
    )
    args, unknown = parser.parse_known_args()

    step = _load_step(args.step)
    # Forward known args by name; step scripts use argparse so unknown args
    # won't break anything if we re-parse them.
    sys.argv = [sys.argv[0]] + unknown
    return step.main(args)


if __name__ == "__main__":
    raise SystemExit(main())