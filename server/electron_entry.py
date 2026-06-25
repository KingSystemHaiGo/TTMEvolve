"""
server/electron_entry.py — Entry point for Electron-spawned Python backend.

Adds the project root to sys.path so that `agent`, `llm`, `core` packages can be
imported regardless of the current working directory.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.portable_env import apply_portable_env, portable_summary

apply_portable_env(_PROJECT_ROOT)

from server.app_server import create_default_app_server


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else str(_PROJECT_ROOT / "config.json")
    provider = sys.argv[2] if len(sys.argv) > 2 else os.getenv("TTM_GUI_PROVIDER") or None
    print(f"[ElectronEntry] project_root={_PROJECT_ROOT}", flush=True)
    print(f"[ElectronEntry] portable={portable_summary(_PROJECT_ROOT)}", flush=True)
    print(f"[ElectronEntry] config={config_path} provider={provider or 'config default'}", flush=True)
    print("[ElectronEntry] creating AppServer...", flush=True)
    server = create_default_app_server(config_path, provider=provider)
    print("[ElectronEntry] AppServer created, starting HTTP server...", flush=True)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
