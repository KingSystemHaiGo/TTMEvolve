"""Tests for scripts/remove-electron.py — dry-run only (no actual deletion)."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import importlib.util

# Load the script as a module.
_script_path = _PROJECT_ROOT / "scripts" / "remove-electron.py"
_spec = importlib.util.spec_from_file_location("remove_electron", _script_path)
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


# ---------- constants ----------


def test_targets_includes_electron_directory():
    assert "electron" in module.TARGETS


def test_targets_includes_old_gui_launchers():
    assert "start-gui.bat" in module.TARGETS
    assert "start-gui.ps1" in module.TARGETS


def test_targets_includes_practice_launchers():
    assert "start-practice.bat" in module.TARGETS
    assert "start-practice.ps1" in module.TARGETS


def test_targets_excludes_tauri_artifacts():
    """v0.7.1 must preserve all Tauri-related files."""
    assert "src-tauri" not in module.TARGETS
    assert "start-tauri.bat" not in module.TARGETS
    assert "start-tauri.sh" not in module.TARGETS
    assert "frontend" not in module.TARGETS


def test_updates_targets_readme_and_package_json():
    assert "package.json" in module.UPDATES
    assert "README.md" in module.UPDATES


def test_all_targets_are_relative_to_project_root():
    for name in module.TARGETS:
        # Should not start with / or drive letter
        assert not name.startswith("/"), f"{name} should be relative"
        assert ":" not in name.split("/")[0], f"{name} should not be absolute"


# ---------- plan() ----------


def test_plan_lists_existing_targets():
    actions = module.plan()
    paths = {a["path"] for a in actions}
    assert "electron" in paths  # we know electron/ exists in this project
    # Old Electron launchers may already be gone in cleaned repositories.
    for target in module.TARGETS:
        if target.endswith((".bat", ".ps1")) and (_PROJECT_ROOT / target).exists():
            assert target in paths


def test_plan_action_shape():
    actions = module.plan()
    for action in actions:
        assert "action" in action
        assert "path" in action
        assert "kind" in action
        assert "size_bytes" in action
        assert action["kind"] in {"file", "directory"}


def test_plan_size_estimate_includes_electron_directory():
    actions = module.plan()
    electron_action = next(
        (a for a in actions if a["path"] == "electron"),
        None,
    )
    assert electron_action is not None
    # electron/ is at least several MB in any real checkout
    assert electron_action["size_bytes"] > 1_000_000  # > 1MB


# ---------- safety ----------


def test_safe_target_rejects_paths_outside_project():
    outside = Path("C:/Windows/System32/notepad.exe")
    assert module._safe_target(outside) is False


def test_safe_target_accepts_inside_project():
    inside = _PROJECT_ROOT / "electron"
    assert module._safe_target(inside) is True


def test_safe_target_handles_nonexistent_paths():
    nonexistent = _PROJECT_ROOT / "definitely_does_not_exist_12345"
    assert module._safe_target(nonexistent) is False


# ---------- size helper ----------


def test_size_returns_zero_for_missing_path():
    assert module._size(_PROJECT_ROOT / "missing") == 0


def test_size_returns_positive_for_existing_file():
    test_file = _PROJECT_ROOT / "tests" / "test_remove_electron.py"
    if test_file.exists():
        assert module._size(test_file) > 0


def test_size_recurses_into_directories():
    if (_PROJECT_ROOT / "electron").exists():
        size = module._size(_PROJECT_ROOT / "electron")
        # Should be much larger than any single file
        assert size > 10_000_000  # > 10MB


# ---------- main() dry-run ----------


def test_main_dry_run_does_not_remove_files(monkeypatch, tmp_path):
    """Run main() without --apply: must not delete any file."""
    # Capture initial state
    electron_path = _PROJECT_ROOT / "electron"
    electron_existed = electron_path.exists()

    # Run with no args (dry-run by default)
    monkeypatch.setattr(sys, "argv", ["remove-electron.py"])
    result = module.main()

    # No removal should have happened
    assert electron_path.exists() == electron_existed
    assert result == 0


def test_main_apply_requires_explicit_flag():
    """main() default must be dry-run; --apply is required."""
    import inspect
    source = inspect.getsource(module.main)
    assert '"--apply"' in source or "'--apply'" in source
    # Confirm the apply branch is gated
    assert "args.apply" in source
