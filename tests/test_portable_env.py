from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from core.portable_env import PORTABLE_ENV_KEYS, apply_portable_env, portable_diagnostics
from server.maker_setup import _auth_state


def _with_env(fn):
    original = os.environ.copy()
    try:
        return fn()
    finally:
        os.environ.clear()
        os.environ.update(original)


def test_apply_portable_env_pins_runtime_paths_inside_agent_root():
    def run():
        with tempfile.TemporaryDirectory(dir=_PROJECT_ROOT) as tmp:
            root = Path(tmp)
            applied = apply_portable_env(root, force=True)
            diagnostics = portable_diagnostics(root)

            assert all(key in os.environ for key in PORTABLE_ENV_KEYS)
            assert "TAPTAP_MAKER_HOME" in applied
            assert "TTM_MAKER_HOME" in applied
            assert diagnostics["status"] == "ready"
            assert diagnostics["blockers"] == []
            assert diagnostics["outside_project"] == []
            assert diagnostics["windows_user_dir_leaks"] == []
            assert Path(os.environ["PIP_CACHE_DIR"]).is_relative_to(root)
            assert Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).is_relative_to(root)

    _with_env(run)


def test_maker_auth_state_uses_portable_maker_home():
    def run():
        with tempfile.TemporaryDirectory(dir=_PROJECT_ROOT) as tmp:
            root = Path(tmp)
            apply_portable_env(root, force=True)
            maker_home = Path(os.environ["TAPTAP_MAKER_HOME"])
            maker_home.mkdir(parents=True, exist_ok=True)
            (maker_home / "tap-auth.json").write_text("{}", encoding="utf-8")

            auth = _auth_state()

            assert auth["maker_home"] == str(maker_home.resolve())
            assert os.environ["TTM_MAKER_HOME"] == os.environ["TAPTAP_MAKER_HOME"]
            assert auth["tap_auth_present"] is True
            assert auth["tap_auth_path"].startswith(str(root.resolve()))

    _with_env(run)


def test_config_relative_paths_are_config_relative():
    with tempfile.TemporaryDirectory(dir=_PROJECT_ROOT) as tmp:
        root = Path(tmp)
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "project_root": "./workspace/default-maker-project",
                    "storage_root": "./storage",
                    "runtime": {"portable_root": "./portable"},
                    "llm": {
                        "provider": "mock",
                        "model_path": "./models/model.gguf",
                    },
                    "maker_mcp": {
                        "command": "npx",
                        "args": ["-y", "@taptap/maker"],
                        "cwd": "./workspace/default-maker-project",
                    },
                }
            ),
            encoding="utf-8",
        )

        cfg = Config(config_path)
        maker_cfg = cfg.maker_mcp_config()

        assert cfg.project_root() == (root / "workspace" / "default-maker-project").resolve()
        assert cfg.storage_root() == (root / "storage").resolve()
        assert cfg.portable_root() == (root / "portable").resolve()
        assert cfg.local_model_path() == (root / "models" / "model.gguf").resolve()
        assert maker_cfg["cwd"] == str((root / "workspace" / "default-maker-project").resolve())


if __name__ == "__main__":
    test_apply_portable_env_pins_runtime_paths_inside_agent_root()
    test_maker_auth_state_uses_portable_maker_home()
    test_config_relative_paths_are_config_relative()
    print("[PASS] portable env tests")
