"""
scripts/import_mcp_config.py — 一键导入外部 MCP 配置

支持：Cursor (.cursor/mcp.json)、Claude Desktop (claude_desktop_config.json)、
OpenClaw (openclaw.json)、Hermes (~/.hermes/config.yaml)。
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from ecosystem.openclaw_adapter import load_openclaw_mcp_servers
from ecosystem.hermes_adapter import load_hermes_mcp_servers


CURSOR_PATH = Path.home() / ".cursor" / "mcp.json"
CLAUDE_DESKTOP_PATH = Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
OPENCLAW_PATH = Path("openclaw.json")
HERMES_PATH = Path.home() / ".hermes" / "config.yaml"


def load_cursor_mcp() -> dict:
    if not CURSOR_PATH.exists():
        return {}
    try:
        data = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
        return data.get("mcpServers", {})
    except Exception:
        return {}


def load_claude_desktop_mcp() -> dict:
    if not CLAUDE_DESKTOP_PATH.exists():
        return {}
    try:
        data = json.loads(CLAUDE_DESKTOP_PATH.read_text(encoding="utf-8"))
        return data.get("mcpServers", {})
    except Exception:
        return {}


def normalize_servers(servers: dict) -> dict:
    """统一为 TTMEvolve 的 mcp_servers 格式。"""
    result = {}
    for name, cfg in servers.items():
        entry = {}
        if "command" in cfg:
            entry["command"] = cfg["command"]
        if "args" in cfg:
            entry["args"] = cfg["args"]
        if "cwd" in cfg:
            entry["cwd"] = cfg["cwd"]
        if "env" in cfg:
            entry["env"] = cfg["env"]
        result[name] = entry
    return result


def main():
    config = Config(str(_PROJECT_ROOT / "config.json"))
    merged = {}

    sources = [
        ("cursor", load_cursor_mcp()),
        ("claude_desktop", load_claude_desktop_mcp()),
        ("openclaw", load_openclaw_mcp_servers(OPENCLAW_PATH)),
        ("hermes", load_hermes_mcp_servers(HERMES_PATH)),
    ]

    for source, servers in sources:
        if servers:
            print(f"[import] 从 {source} 导入 {len(servers)} 个 MCP server")
            merged.update(normalize_servers(servers))

    if not merged:
        print("[import] 未发现外部 MCP 配置")
        return

    # 合并到 config.json
    config_path = _PROJECT_ROOT / "config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data.setdefault("mcp_servers", {}).update(merged)
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[import] 已写入 {len(merged)} 个 server 到 config.json")


if __name__ == "__main__":
    main()
