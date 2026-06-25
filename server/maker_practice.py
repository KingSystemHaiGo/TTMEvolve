"""In-GUI Maker practice setup runner."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.portable_env import apply_portable_env


AUTH_URL_RE = re.compile(r"https://maker\.taptap\.cn/\S+")
PROMPT_MARKERS = [
    "Choose app by index",
    "Create a new Maker project",
    "创建新项目",
]


class MakerPracticeRunner:
    """Run Maker install/init as an observable background workflow."""

    def __init__(self, app_root: Path):
        self.app_root = Path(app_root).resolve()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen[str]] = None
        self._logs: List[Dict[str, Any]] = []
        self._max_logs = 500
        self._state: Dict[str, Any] = {
            "version": "maker-practice.v1",
            "running": False,
            "status": "idle",
            "step": "idle",
            "project_dir": "",
            "auth_url": "",
            "awaiting_input": False,
            "prompt": "",
            "exit_code": None,
            "error": "",
            "started_at": None,
            "finished_at": None,
        }

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._state,
                "logs": list(self._logs[-160:]),
                "log_count": len(self._logs),
            }

    def start(
        self,
        *,
        project_dir: Path,
        skip_install: bool = False,
        skip_init: bool = False,
        app_selection: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            if self._state.get("running"):
                busy = True
            else:
                busy = False
        if busy:
            return {"ok": False, "error": "Maker practice setup is already running.", "status": self.status()}
        with self._lock:
            self._logs = []
            self._state.update({
                "running": True,
                "status": "running",
                "step": "starting",
                "project_dir": str(Path(project_dir).resolve()),
                "auth_url": "",
                "awaiting_input": False,
                "prompt": "",
                "exit_code": None,
                "error": "",
                "started_at": time.time(),
                "finished_at": None,
            })
        self._thread = threading.Thread(
            target=self._run,
            kwargs={
                "project_dir": Path(project_dir).resolve(),
                "skip_install": skip_install,
                "skip_init": skip_init,
                "app_selection": app_selection,
            },
            name="ttmevolve-maker-practice",
            daemon=True,
        )
        self._thread.start()
        return {"ok": True, "status": self.status()}

    def send_input(self, text: str) -> Dict[str, Any]:
        value = str(text or "")
        if not value.endswith("\n"):
            value += "\n"
        with self._lock:
            proc = self._process
        if not proc or proc.poll() is not None or not proc.stdin:
            return {"ok": False, "error": "No Maker CLI process is waiting for input.", "status": self.status()}
        try:
            proc.stdin.write(value)
            proc.stdin.flush()
            self._append_log("input", value.rstrip("\n"))
            with self._lock:
                self._state["awaiting_input"] = False
                self._state["prompt"] = ""
            return {"ok": True, "status": self.status()}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "status": self.status()}

    def cancel(self) -> Dict[str, Any]:
        with self._lock:
            proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            self._append_log("system", "已停止 Maker 接入流程。")
        with self._lock:
            self._state.update({
                "running": False,
                "status": "canceled",
                "step": "canceled",
                "finished_at": time.time(),
            })
        return {"ok": True, "status": self.status()}

    def _run(
        self,
        *,
        project_dir: Path,
        skip_install: bool,
        skip_init: bool,
        app_selection: str,
    ) -> None:
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            if not skip_install:
                self._set_step("maker_install")
                self._run_command(
                    ["-y", "@taptap/maker", "install", "--ide", "codex,cursor,claude"],
                    cwd=self.app_root,
                    app_selection="",
                )
            else:
                self._append_log("system", "已跳过 Maker MCP 安装。")

            if skip_init:
                self._append_log("system", "已跳过 Maker 项目初始化。")
            elif self._maker_initialized(project_dir):
                self._append_log("system", "Maker 项目已初始化。")
            else:
                self._set_step("maker_init")
                init_args = ["-y", "@taptap/maker", "init"]
                if app_selection:
                    init_args.append(app_selection)
                self._run_command(
                    init_args,
                    cwd=project_dir,
                    app_selection=app_selection,
                )
            with self._lock:
                self._state.update({
                    "running": False,
                    "status": "ready",
                    "step": "done",
                    "exit_code": 0,
                    "finished_at": time.time(),
                    "awaiting_input": False,
                    "prompt": "",
                })
        except Exception as exc:
            self._append_log("error", str(exc))
            with self._lock:
                self._state.update({
                    "running": False,
                    "status": "error",
                    "error": str(exc),
                    "finished_at": time.time(),
                })
        finally:
            with self._lock:
                self._process = None

    def _run_command(self, args: List[str], *, cwd: Path, app_selection: str) -> None:
        npx = self._resolve_npx()
        command = [npx, *args]
        self._append_log("system", f"{' '.join(command)}")
        self._append_log("system", f"cwd: {cwd}")
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=self._env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        with self._lock:
            self._process = proc
        buffer = ""
        auto_sent = False
        assert proc.stdout is not None
        while True:
            char = proc.stdout.read(1)
            if char == "" and proc.poll() is not None:
                break
            if not char:
                time.sleep(0.05)
                continue
            buffer += char
            if char in {"\n", "\r"}:
                self._handle_output(buffer.strip())
                buffer = ""
            else:
                self._detect_prompt(buffer)
                if app_selection and not auto_sent and self._looks_like_prompt(buffer):
                    self.send_input(app_selection)
                    auto_sent = True
        if buffer.strip():
            self._handle_output(buffer.strip())
        code = proc.wait()
        self._append_log("system", f"exit code: {code}")
        if code != 0:
            hint = self._friendly_error_hint()
            if hint:
                raise RuntimeError(f"Maker command failed with exit code {code}. {hint}")
            raise RuntimeError(f"Maker command failed with exit code {code}")

    def _handle_output(self, line: str) -> None:
        if not line:
            return
        self._append_log("stdout", line)
        match = AUTH_URL_RE.search(line)
        if match:
            with self._lock:
                self._state["auth_url"] = match.group(0).rstrip(".,)")
        self._detect_prompt(line)

    def _detect_prompt(self, text: str) -> None:
        if self._looks_like_prompt(text):
            with self._lock:
                self._state["awaiting_input"] = True
                self._state["prompt"] = text[-500:]

    def _looks_like_prompt(self, text: str) -> bool:
        return any(marker in text for marker in PROMPT_MARKERS)

    def _append_log(self, kind: str, text: str) -> None:
        with self._lock:
            self._logs.append({
                "kind": kind,
                "text": text,
                "time": time.time(),
            })
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def _friendly_error_hint(self) -> str:
        with self._lock:
            recent = "\n".join(str(row.get("text") or "") for row in self._logs[-20:])
        if "Choose app by index" in recent and "required in non-interactive mode" in recent:
            return "Maker 初始化需要选择项目；TTMEvolve 下次会自动选择“创建新项目”。"
        if "Assertion failed" in recent and "UV_HANDLE_CLOSING" in recent:
            return "Maker CLI 在项目选择阶段异常退出；请重新点击初始化，或先重新选择/新建项目目录。"
        return ""

    def _set_step(self, step: str) -> None:
        with self._lock:
            self._state["step"] = step

    def _env(self) -> Dict[str, str]:
        apply_portable_env(self.app_root)
        env = os.environ.copy()
        vendor_node = self.app_root / "vendor" / "node"
        vendor_git = self.app_root / "vendor" / "git" / "cmd"
        additions = [str(path) for path in [vendor_node, vendor_git] if path.exists()]
        if additions:
            env["PATH"] = os.pathsep.join([*additions, env.get("PATH", "")])
        return env

    def _resolve_npx(self) -> str:
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        if not npx:
            vendor = self.app_root / "vendor" / "node" / "npx.cmd"
            if vendor.exists():
                return str(vendor)
            raise RuntimeError("npx not found. Install Node.js or place portable Node under vendor/node.")
        return npx

    def _maker_initialized(self, project_dir: Path) -> bool:
        return (
            (project_dir / ".maker-mcp" / "config.json").exists()
            or (project_dir / ".project" / "settings.json").exists()
        )
