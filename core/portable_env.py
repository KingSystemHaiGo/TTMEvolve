"""Portable runtime environment for TTMEvolve.

The desktop app should behave like a self-contained agent folder. This module
pins caches, temp files, Maker auth, npm/npx state, HuggingFace data, and
Playwright downloads inside the project directory before heavier modules start.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


PORTABLE_ENV_KEYS = [
    "TTMEVOLVE_ROOT",
    "TTMEVOLVE_PORTABLE_ROOT",
    "TTMEVOLVE_HOME",
    "TTMEVOLVE_CACHE",
    "TTMEVOLVE_TEMP",
    "TAPTAP_MAKER_HOME",
    "TTM_MAKER_HOME",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CACHE_HOME",
    "PIP_CACHE_DIR",
    "npm_config_cache",
    "npm_config_prefix",
    "NPM_CONFIG_CACHE",
    "NPM_CONFIG_PREFIX",
    "HF_HOME",
    "HUGGINGFACE_HUB_CACHE",
    "TRANSFORMERS_CACHE",
    "SENTENCE_TRANSFORMERS_HOME",
    "TORCH_HOME",
    "MPLCONFIGDIR",
    "PLAYWRIGHT_BROWSERS_PATH",
    "TMP",
    "TEMP",
    "TMPDIR",
]


def apply_portable_env(project_root: Path, *, force: bool = False) -> Dict[str, str]:
    """Apply repo-local runtime paths to the current process environment.

    ``force`` overwrites existing variables. The default respects explicit user
    overrides while still filling every unset cache/home path.
    """
    root = Path(project_root).resolve()
    portable = root / "portable"
    home = portable / "home"
    cache = portable / "cache"
    temp_dir = portable / "tmp"
    appdata = home / "AppData" / "Roaming"
    local_appdata = home / "AppData" / "Local"

    paths = {
        "TTMEVOLVE_ROOT": root,
        "TTMEVOLVE_PORTABLE_ROOT": portable,
        "TTMEVOLVE_HOME": home,
        "TTMEVOLVE_CACHE": cache,
        "TTMEVOLVE_TEMP": temp_dir,
        "TAPTAP_MAKER_HOME": home / ".taptap-maker",
        "TTM_MAKER_HOME": home / ".taptap-maker",
        "HOME": home,
        "USERPROFILE": home,
        "APPDATA": appdata,
        "LOCALAPPDATA": local_appdata,
        "XDG_CACHE_HOME": cache / "xdg",
        "PIP_CACHE_DIR": cache / "pip",
        "npm_config_cache": cache / "npm",
        "npm_config_prefix": portable / "node-global",
        "NPM_CONFIG_CACHE": cache / "npm",
        "NPM_CONFIG_PREFIX": portable / "node-global",
        "HF_HOME": cache / "huggingface",
        "HUGGINGFACE_HUB_CACHE": cache / "huggingface" / "hub",
        "TRANSFORMERS_CACHE": cache / "huggingface" / "transformers",
        "SENTENCE_TRANSFORMERS_HOME": _prefer_existing(root / "vendor" / "embeddings", cache / "sentence-transformers"),
        "TORCH_HOME": cache / "torch",
        "MPLCONFIGDIR": cache / "matplotlib",
        "PLAYWRIGHT_BROWSERS_PATH": _prefer_existing(root / "vendor" / "playwright", cache / "playwright"),
        "TMP": temp_dir,
        "TEMP": temp_dir,
        "TMPDIR": temp_dir,
    }

    for value in paths.values():
        Path(value).mkdir(parents=True, exist_ok=True)

    applied: Dict[str, str] = {}
    for key, value in paths.items():
        text = str(value)
        if force or not os.environ.get(key):
            os.environ[key] = text
            applied[key] = text

    # Keep tempfile aligned for libraries that cached tempdir lazily after import.
    tempfile.tempdir = str(temp_dir)
    return applied


def portable_summary(project_root: Path) -> Dict[str, str]:
    root = Path(project_root).resolve()
    portable = root / "portable"
    return {
        "root": str(root),
        "portable_root": str(portable),
        "home": str(portable / "home"),
        "cache": str(portable / "cache"),
        "temp": str(portable / "tmp"),
        "storage": str(root / "storage"),
        "vendor": str(root / "vendor"),
        "models": str(root / "models"),
    }


def portable_diagnostics(
    project_root: Path,
    *,
    configured_portable_root: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Return a no-side-effect snapshot of portable runtime path health."""
    root = Path(project_root).resolve()
    expected_portable = Path(configured_portable_root or (root / "portable")).resolve()
    current_env = env or os.environ
    rows = []
    unset = []
    outside_project = []
    user_dir_leaks = []

    for key in PORTABLE_ENV_KEYS:
        raw = current_env.get(key, "")
        if not raw:
            unset.append(key)
            rows.append({
                "key": key,
                "value": "",
                "exists": False,
                "under_project": False,
                "under_portable": False,
                "risk": "unset",
            })
            continue
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path.absolute()
        under_project = _is_relative_to(resolved, root)
        under_portable = _is_relative_to(resolved, expected_portable)
        risk = ""
        if _looks_like_windows_user_dir(resolved):
            risk = "windows_user_dir"
            user_dir_leaks.append(key)
        elif not under_project:
            risk = "outside_project"
            outside_project.append(key)
        rows.append({
            "key": key,
            "value": str(resolved),
            "exists": resolved.exists(),
            "under_project": under_project,
            "under_portable": under_portable,
            "risk": risk,
        })

    blockers = []
    warnings = []
    if unset:
        blockers.append("portable_env_unset")
    if user_dir_leaks:
        blockers.append("windows_user_dir_leak")
    if outside_project:
        warnings.append("portable_env_outside_project")
    if not _is_relative_to(expected_portable, root):
        blockers.append("configured_portable_root_outside_agent_root")

    return {
        "version": "portable-runtime.v1",
        "status": "blocked" if blockers else ("degraded" if warnings else "ready"),
        "agent_root": str(root),
        "configured_portable_root": str(expected_portable),
        "summary": portable_summary(root),
        "env": rows,
        "blockers": blockers,
        "warnings": warnings,
        "unset": unset,
        "outside_project": outside_project,
        "windows_user_dir_leaks": user_dir_leaks,
        "rule": "Runtime-generated state should stay under the TTMEvolve agent root; portable caches/auth/temp live under portable/ by default.",
    }


def _prefer_existing(primary: Path, fallback: Path) -> Path:
    return primary if primary.exists() else fallback


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _looks_like_windows_user_dir(path: Path) -> bool:
    text = str(path).replace("/", "\\").lower()
    return text.startswith("c:\\users\\")
