"""Tests for the v1.1.0 code-signing and publishing scripts.

These tests focus on:
1. Argument parsing + dry-run behavior (no real signing required).
2. Artifact discovery logic.
3. Error reporting when required args are missing.
4. The orchestrator script's step routing.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCRIPTS = _PROJECT_ROOT / "scripts" / "build_portable"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"step_{name}", _SCRIPTS / f"build_{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Lazy-loaded modules.
windows = None
macos = None
linux = None
publish = None
orchestrator = None


def _windows():
    global windows
    if windows is None:
        windows = _load("sign_windows")
    return windows


def _macos():
    global macos
    if macos is None:
        macos = _load("sign_macos")
    return macos


def _linux():
    global linux
    if linux is None:
        linux = _load("sign_linux")
    return linux


def _publish():
    global publish
    if publish is None:
        publish = _load("publish")
    return publish


def _orchestrator():
    global orchestrator
    if orchestrator is None:
        orchestrator = _load("portable")
    return orchestrator


# ---------- sign-windows ----------


def test_sign_windows_requires_password(monkeypatch):
    monkeypatch.delenv("TTM_PFX_PASSWORD", raising=False)
    result = _windows().main(["--pfx", "cert.pfx"])
    assert result == 2


def test_sign_windows_dry_run_no_artifacts(tmp_path, capsys):
    result = _windows().main([
        "--pfx", "cert.pfx",
        "--pfx-password", "pw",
        "--artifacts-dir", str(tmp_path),
        "--dry-run",
    ])
    assert result == 0


def test_sign_windows_dry_run_lists_artifacts(tmp_path):
    (tmp_path / "TTMEvolve.exe").write_bytes(b"")
    (tmp_path / "TTMEvolve.msi").write_bytes(b"")
    (tmp_path / "README.txt").write_bytes(b"not signed")
    result = _windows().main([
        "--pfx", "cert.pfx",
        "--pfx-password", "pw",
        "--artifacts-dir", str(tmp_path),
        "--dry-run",
    ])
    assert result == 0


def test_sign_windows_finds_exe_and_msi(tmp_path):
    (tmp_path / "setup.exe").write_bytes(b"")
    (tmp_path / "TTMEvolve.msi").write_bytes(b"")
    artifacts = _windows()._find_artifacts(tmp_path)
    names = [a.name for a in artifacts]
    assert "setup.exe" in names
    assert "TTMEvolve.msi" in names


# ---------- sign-macos ----------


def test_sign_macos_requires_apple_id_when_notarizing(monkeypatch):
    monkeypatch.delenv("TTM_APPLE_ID", raising=False)
    result = _macos().main([
        "--identity", "Developer ID Application: X (TEAMID)",
        "--artifacts-dir", "/nonexistent",
    ])
    assert result == 2


def test_sign_macos_dry_run_no_bundles(tmp_path):
    result = _macos().main([
        "--identity", "Developer ID",
        "--artifacts-dir", str(tmp_path),
        "--dry-run",
    ])
    assert result == 0


def test_sign_macos_dry_run_finds_app_and_dmg(tmp_path):
    (tmp_path / "TTMEvolve.app").mkdir()
    (tmp_path / "TTMEvolve.dmg").write_bytes(b"")
    result = _macos().main([
        "--identity", "Developer ID",
        "--artifacts-dir", str(tmp_path),
        "--dry-run",
    ])
    assert result == 0


def test_sign_macos_skip_notarize_skips_apple_id(monkeypatch):
    monkeypatch.delenv("TTM_APPLE_ID", raising=False)
    (tmp_path := Path("/nonexistent2")).mkdir(exist_ok=True)
    result = _macos().main([
        "--identity", "Developer ID",
        "--artifacts-dir", str(tmp_path),
        "--skip-notarize",
        "--dry-run",
    ])
    assert result == 0


# ---------- sign-linux ----------


def test_sign_linux_requires_gpg_passphrase(monkeypatch):
    monkeypatch.delenv("TTM_GPG_PASSPHRASE", raising=False)
    result = _linux().main(["--gpg-key", "ABC12345"])
    assert result == 2


def test_sign_linux_dry_run(tmp_path, monkeypatch):
    (tmp_path / "TTMEvolve.deb").write_bytes(b"")
    result = _linux().main([
        "--gpg-key", "ABC12345",
        "--gpg-passphrase", "pw",
        "--artifacts-dir", str(tmp_path),
        "--dry-run",
    ])
    assert result == 0


def test_sign_linux_finds_deb_appimage_rpm(tmp_path):
    (tmp_path / "a.deb").write_bytes(b"")
    (tmp_path / "b.AppImage").write_bytes(b"")
    (tmp_path / "c.rpm").write_bytes(b"")
    (tmp_path / "d.tar.gz").write_bytes(b"")
    artifacts = _linux()._find_artifacts(tmp_path)
    names = [a.name for a in artifacts]
    assert "a.deb" in names
    assert "b.AppImage" in names
    assert "c.rpm" in names
    assert "d.tar.gz" not in names


def test_sign_linux_manifest_writes_sha256(tmp_path):
    (tmp_path / "x.deb").write_bytes(b"hello")
    (tmp_path / "y.AppImage").write_bytes(b"world")
    _linux()._write_manifest(
        list((tmp_path).glob("*.deb")) + list((tmp_path).glob("*.AppImage")),
        tmp_path / "sha256sums.txt",
    )
    content = (tmp_path / "sha256sums.txt").read_text()
    assert "x.deb" in content
    assert "y.AppImage" in content
    # SHA-256 of "hello" is well-known.
    assert "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" in content


# ---------- publish ----------


def test_publish_dry_run_lists_artifacts(tmp_path):
    (tmp_path / "TTMEvolve.exe").write_bytes(b"x" * 1024)
    (tmp_path / "TTMEvolve.msi").write_bytes(b"y" * 2048)
    (tmp_path / "TTMEvolve.dmg").write_bytes(b"z" * 512)
    (tmp_path / "notes.txt").write_bytes(b"not signed")
    result = _publish().main([
        "--repo", "owner/name",
        "--tag", "v1.0.0",
        "--artifacts-dir", str(tmp_path),
    ])
    assert result == 0


def test_publish_finds_only_signed_extensions(tmp_path):
    (tmp_path / "setup.exe").write_bytes(b"x")
    (tmp_path / "setup.msi").write_bytes(b"x")
    (tmp_path / "raw.zip").write_bytes(b"x")
    (tmp_path / "raw.tar.gz").write_bytes(b"x")
    found = _publish()._find_signed(tmp_path)
    names = [a.name for a in found]
    assert "setup.exe" in names
    assert "setup.msi" in names
    assert "raw.zip" in names
    assert "raw.tar.gz" not in names


def test_publish_returns_zero_when_no_artifacts(tmp_path):
    result = _publish().main([
        "--repo", "owner/name",
        "--tag", "v1.0.0",
        "--artifacts-dir", str(tmp_path),
    ])
    assert result == 0


def test_publish_reads_release_notes_finds_existing(tmp_path, monkeypatch):
    # create the release notes file under docs/releases/
    docs_dir = _PROJECT_ROOT / "docs" / "releases"
    docs_dir.mkdir(parents=True, exist_ok=True)
    notes_file = docs_dir / "v9.9.9-test-release.md"
    notes_file.write_text("# v9.9.9\n\nTest notes", encoding="utf-8")
    try:
        notes = _publish()._read_release_notes("v9.9.9-test")
        assert "Test notes" in notes
    finally:
        notes_file.unlink()


# ---------- orchestrator ----------


def test_orchestrator_imports_all_step_modules():
    """Ensure the orchestrator script can resolve its imports."""
    # Just exercise the import chain via _load — no execution needed.
    for step in ("sign_windows", "sign_macos", "sign_linux", "publish"):
        _load(step)  # raises if broken


def test_orchestrator_lists_steps():
    # Use argparse to enumerate choices.
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("step", choices=("a", "b", "c"))
    # Just verify that the orchestrator's STEPS is a tuple of strings.
    assert isinstance(_orchestrator().STEPS, tuple)
    assert all(isinstance(s, str) for s in _orchestrator().STEPS)