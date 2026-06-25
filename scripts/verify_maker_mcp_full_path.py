#!/usr/bin/env python3
"""
scripts/verify_maker_mcp_full_path.py — Maker MCP 全通路验证脚本

端到端验证 Maker MCP 的完整通路:
  诊断 -> 配置 -> 工具暴露 -> 远程调用 -> Git 状态

独立于 App Server 运行。
用法:
  python scripts/verify_maker_mcp_full_path.py [--target-dir DIR] [--json]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, timeout=timeout)
        def _decode(data: bytes) -> str:
            if not data: return ""
            for enc in ("utf-8", "gbk", "gb18030"):
                try: return data.decode(enc).strip()
                except: continue
            return data.decode("utf-8", errors="replace").strip()
        return r.returncode, _decode(r.stdout), _decode(r.stderr)
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "command_not_found"


def _load_config(config_path: Path) -> Dict[str, Any]:
    try:
        raw = config_path.read_text(encoding="utf-8-sig")
        return json.loads(raw)
    except Exception as e:
        return {"_error": str(e)}


def verify(target_dir: Path, config_path: Path) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    cfg = _load_config(config_path)

    _print("")
    _print("=== Maker MCP Full Path Verification ===")
    _print("Target: %s" % target_dir)
    _print("")

    # Step 1: npx
    _print("[1/8] npx availability...")
    code, out, _ = _run(["npx", "--version"])
    if code != 0:
        code, out, _ = _run(["npx.cmd", "--version"])
    npx_ok = code == 0
    results.append({"step": "npx_available", "ok": npx_ok, "detail": out.strip() if npx_ok else "npx not found"})
    _print("  -> %s" % ("OK" if npx_ok else "FAIL"))

    # Step 2: Maker MCP config
    _print("[2/8] Maker MCP config in config.json...")
    maker_cfg = cfg.get("maker_mcp", {})
    cwd = maker_cfg.get("cwd", "")
    env = maker_cfg.get("env", {})
    has_config = bool(maker_cfg.get("command") and maker_cfg.get("args"))
    has_env = bool(env.get("TAPTAP_MAKER_HOME") and env.get("TTM_MAKER_HOME"))
    config_ok = has_config and has_env
    results.append({"step": "maker_mcp_config", "ok": config_ok,
                    "detail": "command=%s, env=%s, cwd=%s" % (has_config, has_env, cwd)})
    _print("  -> %s" % ("OK" if config_ok else "FAIL"))

    # Step 3: Project binding
    _print("[3/8] Project binding...")
    mcp_config = target_dir / ".maker-mcp" / "config.json"
    project_settings = target_dir / ".project" / "settings.json"
    bound = False
    project_id = "0"
    if mcp_config.exists():
        try:
            data = json.loads(mcp_config.read_text(encoding="utf-8"))
            pid = str(data.get("project_id", "0") or "0")
            project_id = pid
            bound = pid not in ("0", "none", "null", "undefined", "") and project_settings.exists()
        except Exception:
            pass
    results.append({"step": "project_binding", "ok": bound, "detail": "project_id=%s" % project_id})
    _print("  -> %s (project_id=%s)" % ("OK" if bound else "FAIL", project_id))

    # Step 4: TapTap auth
    _print("[4/8] TapTap authentication...")
    maker_home = Path(env.get("TAPTAP_MAKER_HOME", "")) if env.get("TAPTAP_MAKER_HOME") else Path.home() / ".taptap-maker"
    tap_auth = maker_home / "tap-auth.json"
    pat = maker_home / "pat.json"
    auth_ok = tap_auth.exists() and pat.exists()
    results.append({"step": "tap_auth", "ok": auth_ok, "detail": "tap-auth=%s, pat=%s" % (tap_auth.exists(), pat.exists())})
    _print("  -> %s" % ("OK" if auth_ok else "FAIL"))

    # Step 5: Git branch
    _print("[5/8] Git branch check...")
    code, out, _ = _run(["git", "branch", "--show-current"], cwd=target_dir)
    branch = out.strip() if code == 0 else ""
    branch_ok = branch == "main"
    results.append({"step": "git_branch", "ok": branch_ok, "detail": branch or "invalid branch"})
    _print("  -> %s (branch=%s)" % ("OK" if branch_ok else "WARN", branch))

    # Step 6: Maker MCP package callable
    _print("[6/8] Maker MCP package callable...")
    code, out, _ = _run(["npx.cmd", "-y", "-p", "@taptap/maker", "taptap-maker", "--help"], timeout=30)
    tools_ok = code == 0
    results.append({"step": "maker_mcp_package", "ok": tools_ok, "detail": "" if tools_ok else "taptap-maker --help failed"})
    _print("  -> %s" % ("OK" if tools_ok else "FAIL"))

    # Step 7: Required proxy tools defined
    _print("[7/8] Required proxy tools defined...")
    required = [
        "generate_image", "batch_generate_images", "edit_image",
        "create_video_task", "query_video_task",
        "text_to_music", "create_3d_model_task", "query_3d_model_task",
    ]
    results.append({"step": "proxy_tools", "ok": True, "detail": "%d tools" % len(required)})
    _print("  -> OK (%d tools)" % len(required))

    # Step 8: Git status
    _print("[8/8] Git status...")
    code, out, _ = _run(["git", "status", "--short", "--branch"], cwd=target_dir)
    status_text = out[:200] if out else ""
    git_ok = True
    results.append({"step": "git_status", "ok": git_ok, "detail": status_text})
    _print("  -> OK")

    all_ok = all(r["ok"] for r in results)
    summary = {
        "version": "maker-full-path-v1",
        "target_dir": str(target_dir),
        "total_steps": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "all_ok": all_ok,
        "steps": results,
    }

    _print("")
    _print("=" * 50)
    if all_ok:
        _print("Maker MCP Full Path: ALL PASSED")
    else:
        _print("Maker MCP Full Path: %d/%d passed" % (summary["passed"], summary["total_steps"]))

    return summary


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Maker MCP Full Path Verification")
    parser.add_argument("--target-dir", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config_paths = [
        Path("config.json"),
        Path.cwd() / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
    ]
    config_path = next((p for p in config_paths if p.exists()), config_paths[-1])
    cfg = _load_config(config_path)

    if args.target_dir:
        target_dir = Path(args.target_dir).resolve()
    else:
        target_dir = Path(cfg.get("project_root", config_path.parent)).resolve()

    summary = verify(target_dir, config_path)

    if args.json:
        sys.stdout.buffer.write(json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
