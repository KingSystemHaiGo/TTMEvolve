#!/usr/bin/env python3
"""
scripts/one_click_fix_maker.py — Maker MCP 一键修复脚本

独立于 App Server 运行，检测并自动修复常见的 Maker MCP 故障。
用法:
  python scripts/one_click_fix_maker.py [--target-dir DIR] [--fix]

--fix: 自动执行可修复的故障（预设仅检测）
--target-dir: Maker 项目目录（预设从 config.json 读取）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -- 常量 --------------------------------------------------

MAKER_PACKAGE = "@taptap/maker"
REQUIRED_ENV_VARS = ["TAPTAP_MAKER_HOME", "TTM_MAKER_HOME"]
REQUIRED_PROXY_TOOLS = [
    "generate_image", "batch_generate_images", "edit_image",
    "create_video_task", "query_video_task",
    "text_to_music",
    "create_3d_model_task", "query_3d_model_task",
]

# -- 工具函数 -----------------------------------------------

def _info(msg: str) -> None:
    print(f"  [i] {msg}", file=sys.stderr)

def _ok(msg: str) -> None:
    print(f"  [OK] {msg}", file=sys.stderr)

def _warn(msg: str) -> None:
    print(f"  [!] {msg}", file=sys.stderr)

def _err(msg: str) -> None:
    print(f"  [X] {msg}", file=sys.stderr)

def _print(*args, **kwargs):
    """Print diagnostic output to stderr so stdout stays clean for JSON."""
    print(*args, file=sys.stderr, **kwargs)

def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, timeout=timeout)
        # decode with gbk fallback for Windows compatibility
        def _decode(data: bytes) -> str:
            if not data:
                return ""
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    return data.decode(enc).strip()
                except (UnicodeDecodeError, LookupError):
                    continue
            return data.decode("utf-8", errors="replace").strip()
        return r.returncode, _decode(r.stdout), _decode(r.stderr)
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "command_not_found"

def _find_config() -> Path:
    """从常见路径查找 config.json"""
    candidates = [
        Path("config.json"),
        Path.cwd() / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    return candidates[-1].resolve()

def _load_config(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        return json.loads(raw)
    except Exception as e:
        return {"_error": str(e)}

def _read_project_id(config: Dict[str, Any]) -> str:
    maker_cfg = config.get("maker_mcp", {})
    cwd = maker_cfg.get("cwd", "")
    if cwd:
        mcp_config = Path(cwd) / ".maker-mcp" / "config.json"
        if mcp_config.exists():
            try:
                data = json.loads(mcp_config.read_text(encoding="utf-8"))
                return str(data.get("project_id", "0"))
            except Exception:
                pass
    return "0"

# -- 检测步骤 -----------------------------------------------

def check_npx() -> Tuple[bool, str]:
    """检查 npx 是否可用"""
    code, out, err = _run(["npx", "--version"])
    if code == 0:
        return True, out.strip()
    code2, out2, err2 = _run(["npx.cmd", "--version"])
    if code2 == 0:
        return True, out2.strip()
    return False, err or err2 or "npx not found"

def check_maker_mcp_installed() -> Tuple[bool, str]:
    """检查 @taptap/maker 是否已安装"""
    code, out, err = _run(["npx.cmd", "-y", "-p", MAKER_PACKAGE, "taptap-maker", "--help"])
    if code == 0:
        return True, "installed"
    return False, err or "not installed"

def check_maker_config(config_path: Path) -> Tuple[bool, Dict[str, Any]]:
    """检查 config.json 中的 maker_mcp 配置"""
    cfg = _load_config(config_path)
    maker_cfg = cfg.get("maker_mcp", {})
    if not maker_cfg:
        return False, {"reason": "maker_mcp config missing"}

    command = maker_cfg.get("command", "")
    args = maker_cfg.get("args", [])
    cwd = maker_cfg.get("cwd", "")
    env = maker_cfg.get("env", {})

    issues = []
    if not command:
        issues.append("command missing")
    if not cwd:
        issues.append("cwd missing")

    for var in REQUIRED_ENV_VARS:
        if not env.get(var):
            issues.append(f"{var} not set")

    args_text = " ".join(str(a) for a in args) if isinstance(args, list) else str(args)
    if "@taptap/maker" not in args_text:
        issues.append("args missing @taptap/maker")

    return len(issues) == 0, {"issues": issues, "config": maker_cfg}

def check_project_binding(target_dir: Path) -> Tuple[bool, Dict[str, Any]]:
    """检查项目是否绑定到 Maker 项目"""
    mcp_config = target_dir / ".maker-mcp" / "config.json"
    project_settings = target_dir / ".project" / "settings.json"

    result = {
        "mcp_config_exists": mcp_config.exists(),
        "project_settings_exists": project_settings.exists(),
        "project_id": "0",
        "project_bound": False,
    }

    if mcp_config.exists():
        try:
            data = json.loads(mcp_config.read_text(encoding="utf-8"))
            pid = str(data.get("project_id", "0") or "0")
            result["project_id"] = pid
            result["project_bound"] = pid not in ("0", "none", "null", "undefined", "")
        except Exception:
            pass

    bound = result["project_bound"] and result["project_settings_exists"]
    return bound, result

def check_env_vars(config_override: Optional[Dict[str, Optional[str]]] = None) -> Tuple[bool, Dict[str, Optional[str]]]:
    """检查 Maker 相关环境变量（OS 环境 + config 中的覆盖）"""
    env_state = {}
    for var in REQUIRED_ENV_VARS:
        # 先查 OS 环境，再查 config 覆盖
        val = os.environ.get(var)
        if config_override and config_override.get(var):
            val = config_override[var]
        env_state[var] = val

    both_set = all(env_state.get(v) for v in REQUIRED_ENV_VARS)
    match = both_set and env_state["TAPTAP_MAKER_HOME"] == env_state["TTM_MAKER_HOME"]
    return match, env_state

def check_tap_auth(target_dir: Path, maker_home: Optional[Path] = None) -> Tuple[bool, Dict[str, Any]]:
    """检查 TapTap 认证"""
    if not maker_home:
        maker_home = Path.home() / ".taptap-maker"
        portable_home = target_dir.parent / "portable" / "home" / ".taptap-maker"
        if portable_home.exists():
            maker_home = portable_home

    tap_auth = maker_home / "tap-auth.json"
    pat = maker_home / "pat.json"
    return tap_auth.exists() and pat.exists(), {
        "maker_home": str(maker_home),
        "tap_auth": tap_auth.exists(),
        "pat": pat.exists(),
    }

def check_git_branch(target_dir: Path) -> Tuple[bool, str]:
    """检查 Git 分支是否为 main"""
    code, out, err = _run(["git", "branch", "--show-current"], cwd=target_dir)
    if code == 0:
        branch = out.strip()
        return branch == "main", branch
    return False, f"git error: {err}"

# -- 修复步骤 -----------------------------------------------

def fix_maker_config(config_path: Path) -> Tuple[bool, str]:
    """修复 config.json 中的 maker_mcp 配置"""
    try:
        cfg = _load_config(config_path)
        maker_cfg = cfg.setdefault("maker_mcp", {})

        if os.name == "nt":
            maker_cfg["command"] = "cmd.exe"
            maker_cfg["args"] = ["/d", "/s", "/c", "npx.cmd", "-y", "-p", "@taptap/maker", "taptap-maker"]
        else:
            maker_cfg["command"] = "npx"
            maker_cfg["args"] = ["-y", "-p", "@taptap/maker", "taptap-maker"]

        project_root = cfg.get("project_root", "")
        if project_root:
            maker_cfg["cwd"] = str(Path(project_root).resolve())

        env = maker_cfg.setdefault("env", {})
        portable_root = cfg.get("runtime", {}).get("portable_root", "./portable")
        maker_home = str((Path(config_path).resolve().parent / portable_root / "home" / ".taptap-maker").resolve())
        env["TAPTAP_MAKER_HOME"] = maker_home
        env["TTM_MAKER_HOME"] = maker_home
        env["TAPTAP_MCP_ENV"] = "production"
        maker_cfg.setdefault("request_timeout_seconds", 30)

        config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, "Config written"
    except Exception as e:
        return False, str(e)

def run_maker_upgrade(target_dir: Path) -> Tuple[bool, str]:
    """升级 Maker MCP"""
    code, out, err = _run(
        ["npx.cmd", "-y", "-p", "@taptap/maker", "taptap-maker", "upgrade", "--target-dir", str(target_dir)],
        timeout=120
    )
    if code == 0:
        return True, out
    return False, err or out

def run_maker_init(target_dir: Path) -> Tuple[bool, str]:
    """在目录中执行 Maker 初始化"""
    _info("Running Maker init (may take 30+ seconds)...")
    code, out, err = _run(
        ["npx.cmd", "-y", "-p", "@taptap/maker", "taptap-maker", "init", "--skip-mcp-install"],
        cwd=target_dir, timeout=300
    )
    if code == 0:
        return True, out
    return False, err or out

# -- 主流程 -----------------------------------------------

def diagnose(target_dir: Path, config_path: Path) -> Dict[str, Any]:
    """执行完整诊断"""
    _print("")
    _print("=== TTMEvolve Maker MCP 诊断 ===")
    _print("")
    _print("目标目录: %s" % target_dir)
    _print("配置文件: %s" % config_path)
    _print("")

    results: Dict[str, Any] = {}

    # 1. npx
    _print("--- 1. npx 可用性 ---")
    npx_ok, npx_ver = check_npx()
    if npx_ok:
        _ok("npx 版本: %s" % npx_ver)
    else:
        _err("npx 不可用: %s" % npx_ver)
    results["npx"] = {"ok": npx_ok, "version": npx_ver}

    # 2. Maker MCP 安装
    _print("")
    _print("--- 2. @taptap/maker 安装状态 ---")
    maker_ok, maker_status = check_maker_mcp_installed()
    if maker_ok:
        _ok("@taptap/maker 已安装")
    else:
        _err("未安装: %s" % maker_status)
    results["maker_installed"] = {"ok": maker_ok, "status": maker_status}

    # 3. Config
    _print("")
    _print("--- 3. config.json maker_mcp 配置 ---")
    config_ok, config_detail = check_maker_config(config_path)
    issues = config_detail.get("issues", []) if isinstance(config_detail, dict) else []
    if config_ok:
        _ok("配置完整")
    else:
        for issue in issues:
            _err(issue)
    results["config"] = {"ok": config_ok, "detail": config_detail}

    # 4. 环境变量
    _print("")
    _print("--- 4. 环境变量 ---")
    cfg_env = (config_detail.get("config") or {}).get("env", {}) if isinstance(config_detail, dict) else {}
    env_ok, env_state = check_env_vars(config_override=cfg_env)
    for var, val in env_state.items():
        if val:
            _ok("%s = %s" % (var, val))
        else:
            _err("%s 未设置" % var)
    if env_ok:
        _ok("两者一致")
    elif env_state.get("TAPTAP_MAKER_HOME") and env_state.get("TTM_MAKER_HOME"):
        _warn("路径不一致")
    results["env"] = {"ok": env_ok, "state": env_state}

    # 5. 项目绑定
    _print("")
    _print("--- 5. 项目绑定 ---")
    bound, project_state = check_project_binding(target_dir)
    if bound:
        _ok("已绑定 project_id: %s" % project_state.get("project_id"))
    else:
        pid = project_state.get("project_id", "0")
        if pid == "0":
            _err("未绑定真实项目 (project_id=0)")
        else:
            _err("项目绑定不完整: project_id=%s" % pid)
    results["project"] = {"ok": bound, "state": project_state}

    # 6. TapTap 认证
    _print("")
    _print("--- 6. TapTap 认证 ---")
    auth_ok, auth_state = check_tap_auth(target_dir)
    if auth_state.get("tap_auth"):
        _ok("tap-auth: 存在")
    else:
        _err("tap-auth 缺失")
    if auth_state.get("pat"):
        _ok("PAT: 存在")
    else:
        _err("PAT 缺失")
    results["auth"] = {"ok": auth_ok, "state": auth_state}

    # 7. Git 分支
    _print("")
    _print("--- 7. Git 分支 ---")
    branch_ok, branch_name = check_git_branch(target_dir)
    if branch_ok:
        _ok("分支: %s" % branch_name)
    else:
        if branch_name:
            _warn("当前分支: %s (非 main)" % branch_name)
        else:
            _err("错误: %s" % branch_name)
    results["git"] = {"ok": branch_ok, "branch": branch_name}

    # 综合评估
    _print("")
    _print("=" * 50)
    all_ok = all([
        npx_ok, config_ok, env_ok, bound, auth_ok
    ])
    if all_ok:
        _ok("所有检查通过！Maker MCP 已准备好使用。")
        results["readiness"] = "ready"
    else:
        failures = []
        if not npx_ok: failures.append("npx_missing")
        if not config_ok: failures.append("config_incomplete")
        if not env_ok: failures.append("env_vars_missing")
        if not bound: failures.append("project_not_bound")
        if not auth_ok: failures.append("auth_missing")
        _warn("发现 %d 个问题: %s" % (len(failures), ", ".join(failures)))
        results["readiness"] = "blocked"
        results["blockers"] = failures

    return results


def repair(target_dir: Path, config_path: Path, results: Dict[str, Any]) -> Dict[str, Any]:
    """执行自动修复"""
    _print("")
    _print("=== 执行一键修复 ===")
    _print("")
    repair_log: List[Dict[str, Any]] = []

    # 修复 1: config.json
    if not results.get("config", {}).get("ok", True):
        _info("修复 config.json maker_mcp 配置...")
        ok, msg = fix_maker_config(config_path)
        if ok:
            _ok("配置已更新: %s" % msg)
        else:
            _err("修复失败: %s" % msg)
        repair_log.append({"target": "config", "ok": ok, "msg": msg})

    # 修复 2: 项目绑定
    if not results.get("project", {}).get("ok", True):
        _info("执行 Maker init 绑定项目...")
        ok, msg = run_maker_init(target_dir)
        if ok:
            _ok("项目初始化/绑定成功")
        else:
            _warn("初始化可能需要手动操作: %s" % msg[:200])
        repair_log.append({"target": "project_binding", "ok": ok, "msg": msg[:200]})

    # 修复 3: npx 缺失
    if not results.get("npx", {}).get("ok", True):
        _info("npx 缺失 -- 建议安装 Node.js/npm")
        _info("请从 https://nodejs.org/ 安装 Node.js")
        repair_log.append({"target": "npx", "ok": False, "msg": "需要手动安装 Node.js"})

    # 总结
    auto_fixable = [r for r in repair_log if r["ok"]]
    manual_needed = [r for r in repair_log if not r["ok"]]

    _print("")
    _print("=" * 50)
    _print("修复完成: %d 个自动修复, %d 个需要手动处理" % (len(auto_fixable), len(manual_needed)))

    return {
        "repairs": repair_log,
        "auto_fixed": len(auto_fixable),
        "manual_needed": len(manual_needed),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="TTMEvolve Maker MCP 一键修复工具")
    parser.add_argument("--target-dir", help="Maker 项目目录", default=None)
    parser.add_argument("--fix", action="store_true", help="自动执行可修复的故障")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    config_path = _find_config()
    cfg = _load_config(config_path)

    if args.target_dir:
        target_dir = Path(args.target_dir).resolve()
    else:
        target_dir = Path(cfg.get("project_root", config_path.parent)).resolve()

    results = diagnose(target_dir, config_path)

    if args.fix:
        repair_results = repair(target_dir, config_path, results)
        results["repair"] = repair_results
    else:
        results["repair"] = {"note": "Run with --fix to auto-repair"}
        if results.get("readiness") != "ready":
            _info("")
            _info("使用 --fix 参数来自动修复可修复的故障")

    if args.json:
        sys.stdout.buffer.write(json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    return 0 if results.get("readiness") == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
