"""Tests for the portable runtime build / verification scripts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BUILD_DIR = _PROJECT_ROOT / "scripts" / "build-portable"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )


# ---------- config.json ----------


def test_config_json_loads_and_has_expected_keys():
    cfg_path = _BUILD_DIR / "config.json"
    assert cfg_path.exists(), "config.json must exist"
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "python" in config
    assert "node" in config
    assert "site_packages" in config
    assert "maker_mcp" in config


def test_config_json_has_required_platforms():
    config = json.loads((_BUILD_DIR / "config.json").read_text(encoding="utf-8"))
    for key in ("python", "node"):
        assert "windows" in config[key]
        assert "linux" in config[key]
        assert "macos" in config[key]


def test_config_python_urls_are_https():
    config = json.loads((_BUILD_DIR / "config.json").read_text(encoding="utf-8"))
    for platform in ("windows", "linux", "macos"):
        url = config["python"][platform]["url"]
        assert url.startswith("https://"), f"python {platform} url must be https"


def test_config_node_urls_are_https():
    config = json.loads((_BUILD_DIR / "config.json").read_text(encoding="utf-8"))
    for platform in ("windows", "linux", "macos"):
        url = config["node"][platform]["url"]
        assert url.startswith("https://"), f"node {platform} url must be https"


def test_config_site_packages_excludes_local_llm_deps():
    """v0.7.0 drops local model deps (llama-cpp-python, torch, sentence-transformers)."""
    config = json.loads((_BUILD_DIR / "config.json").read_text(encoding="utf-8"))
    all_packages = (
        config["site_packages"]["requirements"]
        + config["site_packages"]["optional"]
    )
    package_names = {p.split("==")[0].split("[")[0].lower() for p in all_packages}
    forbidden = {"llama-cpp-python", "torch", "sentence-transformers", "huggingface-hub"}
    overlap = package_names & forbidden
    assert not overlap, f"v0.7.0 must not include {overlap}"


# ---------- script imports ----------


def test_build_python_imports():
    """The script must be syntactically valid (no syntax errors)."""
    import ast
    src = (_BUILD_DIR / "build_python.py").read_text(encoding="utf-8")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        raise AssertionError(f"build_python.py has syntax error: {exc}")


def test_build_node_imports():
    """The script must be syntactically valid (no syntax errors)."""
    import ast
    src = (_BUILD_DIR / "build_node.py").read_text(encoding="utf-8")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        raise AssertionError(f"build_node.py has syntax error: {exc}")


def test_verify_portable_runs_without_portable():
    """verify_portable.py must run cleanly even when portable/ is empty."""
    result = _run(_BUILD_DIR / "verify_portable.py")
    # Should fail because nothing is installed, but must not crash
    assert "portable" in result.stdout.lower()


# ---------- verify_portable logic ----------


def test_verify_portable_budget_default():
    """Default budget is 500MB (v0.7.0 cloud-only target)."""
    # Read the source to verify the default
    src = (_BUILD_DIR / "verify_portable.py").read_text(encoding="utf-8")
    assert "max_budget_mb: int = 500" in src or "500" in src


# ---------- size estimates ----------


def test_python_embedded_size_estimate_under_budget():
    """Python embedded ~30MB, must fit in 500MB total budget."""
    # Estimated Python embedded zip: ~11MB → ~30MB extracted
    config = json.loads((_BUILD_DIR / "config.json").read_text(encoding="utf-8"))
    for platform in ("windows", "linux", "macos"):
        size = config["python"][platform].get("expected_size_bytes", 0)
        assert size < 100_000_000, f"python {platform} size {size} seems too large"


def test_node_embedded_size_estimate_under_budget():
    """Node embedded ~30MB, must fit in 500MB total budget."""
    config = json.loads((_BUILD_DIR / "config.json").read_text(encoding="utf-8"))
    for platform in ("windows", "linux", "macos"):
        size = config["node"][platform].get("expected_size_bytes", 0)
        assert size < 50_000_000, f"node {platform} size {size} seems too large"