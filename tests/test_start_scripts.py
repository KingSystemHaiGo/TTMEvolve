"""Tests for the cross-platform TTMEvolve launchers.

These tests verify the launcher scripts:
1. Exist at the expected paths.
2. Contain the expected portable-environment priority logic.
3. Support GUI / CLI / headless modes on both Windows and POSIX.

The actual GUI / CLI dispatch logic is not executed (we can't open a window
in CI), but we can verify that the right mode flags are wired.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------- file existence ----------


def test_start_tauri_bat_exists():
    path = _PROJECT_ROOT / "start-tauri.bat"
    assert path.exists(), "start-tauri.bat is required for Windows"


def test_start_tauri_sh_exists():
    path = _PROJECT_ROOT / "start-tauri.sh"
    assert path.exists(), "start-tauri.sh is required for Linux/macOS"


def test_start_tauri_sh_is_executable():
    """POSIX permission check — Windows skips this test."""
    if sys.platform.startswith("win"):
        # Skip on Windows; executable bit is not meaningful.
        return
    path = _PROJECT_ROOT / "start-tauri.sh"
    assert path.stat().st_mode & 0o111, "start-tauri.sh should be executable"


# ---------- portable priority ----------


def test_start_tauri_bat_priority_order():
    """The Windows launcher must prefer portable → venv → system."""
    text = (_PROJECT_ROOT / "start-tauri.bat").read_text(encoding="utf-8")
    # The labels appear in this order: portable → venv → where python
    portable_pos = text.find("portable\\python")
    venv_pos = text.find(".venv\\Scripts\\python")
    system_pos = text.find("where python")
    assert portable_pos != -1, "portable check missing"
    assert venv_pos != -1, "venv check missing"
    assert system_pos != -1, "system fallback missing"
    assert portable_pos < venv_pos < system_pos, (
        f"priority order broken: portable={portable_pos} venv={venv_pos} system={system_pos}"
    )


def test_start_tauri_sh_priority_order():
    text = (_PROJECT_ROOT / "start-tauri.sh").read_text(encoding="utf-8")
    portable_pos = text.find("./portable/python/bin/python3")
    venv_pos = text.find("./.venv/bin/python3")
    system_pos = text.find("command -v python3")
    assert portable_pos != -1, "portable check missing"
    assert venv_pos != -1, "venv check missing"
    assert system_pos != -1, "system fallback missing"
    assert portable_pos < venv_pos < system_pos, (
        f"priority order broken: portable={portable_pos} venv={venv_pos} system={system_pos}"
    )


# ---------- mode flags ----------


def test_start_tauri_bat_supports_cli_mode():
    text = (_PROJECT_ROOT / "start-tauri.bat").read_text(encoding="utf-8")
    assert "--cli" in text, "Windows launcher should support --cli flag"
    assert "--headless" in text, "Windows launcher should support --headless flag"


def test_start_tauri_sh_supports_cli_mode():
    text = (_PROJECT_ROOT / "start-tauri.sh").read_text(encoding="utf-8")
    assert "--cli" in text, "POSIX launcher should support --cli flag"
    assert "--headless" in text, "POSIX launcher should support --headless flag"


def test_start_tauri_bat_includes_friendly_error_messages():
    text = (_PROJECT_ROOT / "start-tauri.bat").read_text(encoding="utf-8")
    # v0.9.0 enhanced error messages
    assert "ERROR" in text, "launcher should print ERROR on missing python"
    assert "build-portable" in text or "build_all" in text, "should hint at build_portable"


def test_start_tauri_sh_includes_friendly_error_messages():
    text = (_PROJECT_ROOT / "start-tauri.sh").read_text(encoding="utf-8")
    assert "ERROR" in text, "launcher should print ERROR on missing python"
    assert "build-portable" in text or "build_all" in text, "should hint at build_portable"


# ---------- platform detection ----------


def test_start_turi_sh_detects_platform():
    text = (_PROJECT_ROOT / "start-tauri.sh").read_text(encoding="utf-8")
    # POSIX uname-based detection
    assert "uname" in text or "Darwin" in text or "Linux" in text, (
        "POSIX launcher should detect platform via uname or branch on OS"
    )


# ---------- version stamp ----------


def test_start_tauri_bat_includes_v090_marker():
    text = (_PROJECT_ROOT / "start-tauri.bat").read_text(encoding="utf-8")
    assert "v0.9.0" in text


def test_start_tauri_sh_includes_v090_marker():
    text = (_PROJECT_ROOT / "start-tauri.sh").read_text(encoding="utf-8")
    assert "v0.9.0" in text


# ---------- shellcheck / bash sanity ----------


def test_start_turi_sh_uses_set_e():
    text = (_PROJECT_ROOT / "start-tauri.sh").read_text(encoding="utf-8")
    assert re.search(r"^set\s+-[a-z]*e", text, re.MULTILINE), (
        "POSIX launcher should use `set -e` for fail-fast"
    )


def test_start_turi_bat_uses_setlocal():
    text = (_PROJECT_ROOT / "start-tauri.bat").read_text(encoding="utf-8")
    assert "setlocal" in text, "Windows launcher should use setlocal for variable isolation"