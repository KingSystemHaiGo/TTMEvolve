# -*- coding: utf-8 -*-
"""
main.py -- TTMEvolve CLI entry point

CLI is now a thin client of App Server:
- If no App Server is running in background, start one automatically.
- User input is sent to Server via HTTP + SSE.
- --serve can start Server directly.
"""

from __future__ import annotations
import argparse
import json
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# Add project root to path
_HERE = Path(__file__).resolve().parent
import sys
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.portable_env import apply_portable_env

apply_portable_env(_HERE)

from core.config import Config
from server.app_server import create_default_app_server


APP_SERVER_HOST = "127.0.0.1"
APP_SERVER_PORT = 7345
APP_SERVER_URL = f"http://{APP_SERVER_HOST}:{APP_SERVER_PORT}"


def print_banner():
    print("""
+--------------------------------------------------------------+
|              TTMEvolve - Self-Evolving TapMaker Agent        |
|          Agent Layer . Runtime Layer . Learning Layer        |
+--------------------------------------------------------------+
|  Commands:                                                    |
|    any dev task      - ReAct + MCP execution                  |
|    --provider local  - default local GGUF model (MiniCPM5-1B) |
|    --provider claude - use Claude API                         |
|    --provider mock   - use Mock LLM test                      |
|    status            - view health status                     |
|    exit/quit         - exit                                   |
+--------------------------------------------------------------+
""")


def confirm_callback(message: str) -> bool:
    try:
        answer = input(f"\n[Confirm] {message} (y/n): ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _http_get(path: str, timeout: float = 2.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"{APP_SERVER_URL}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _http_post(path: str, payload: dict) -> Optional[dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{APP_SERVER_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def _is_server_running() -> bool:
    return _http_get("/health") is not None


def _start_server_in_thread(config_path: str, provider: Optional[str] = None) -> None:
    def _run():
        try:
            from server.app_server import create_default_app_server
            server = create_default_app_server(config_path, provider)
            server.start()
        except Exception as e:
            print(f"[CLI] Failed to start App Server in background: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    for _ in range(20):
        if _is_server_running():
            return
        time.sleep(0.2)


def _ensure_server(config_path: str, provider: Optional[str] = None) -> bool:
    if _is_server_running():
        return True
    print("[CLI] Starting App Server...")
    _start_server_in_thread(config_path, provider)
    return _is_server_running()


def _stream_events(session_id: str) -> None:
    url = f"{APP_SERVER_URL}/sessions/{session_id}/events"
    try:
        with urllib.request.urlopen(url, timeout=None) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                if text.startswith("data: "):
                    try:
                        event = json.loads(text[6:])
                        _print_event(event)
                        if event.get("type") == "status" and event.get("payload", {}).get("done"):
                            break
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"[CLI] Event stream broken: {e}")


def _print_event(event: dict) -> None:
    event_type = event.get("type")
    payload = event.get("payload", {})
    if event_type == "thought":
        print(f"\n[Think] {payload.get('thought', '')[:200]}")
    elif event_type == "tool_call":
        print(f"[Tool] {payload.get('tool')}({payload.get('params')})")
    elif event_type == "observation":
        ok = payload.get("observation", {}).get("ok", False)
        icon = "[OK]" if ok else "[FAIL]"
        print(f"{icon} Observation: {payload.get('observation', {})}")
    elif event_type == "output":
        print(f"\n[Result] {payload.get('output', '')}")
    elif event_type == "error":
        print(f"[Error] {payload.get('message', '')}")
    elif event_type == "status":
        msg = payload.get("message", "")
        if payload.get("done"):
            print(f"\n[Done] {msg}")
        else:
            print(f"\n[Status] {msg}")


def _run_task(task: str, profile: Optional[str] = None, provider: Optional[str] = None) -> None:
    payload: dict = {"task": task}
    if profile:
        payload["profile"] = profile
    if provider:
        payload["provider"] = provider
    resp = _http_post("/sessions", payload)
    if not resp or "session_id" not in resp:
        print(f"[Error] Failed to create session: {resp}")
        return
    sid = resp["session_id"]
    print(f"\n[Task] {task}")
    _stream_events(sid)

    final = _http_get(f"/sessions/{sid}/status")
    if final:
        status = "done" if final.get("done") else "running"
        print(f"[Summary] status={status} error={final.get('error') or 'none'}")


def main():
    parser = argparse.ArgumentParser(description="TTMEvolve CLI")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: config.llm.server_port or 7345)",
    )
    parser.add_argument(
        "--provider",
        choices=["local", "deepseek", "openai", "claude", "mock"],
        default=None,
        help="LLM provider (default reads config.llm.provider)",
    )
    parser.add_argument("--profile", default=None, help="Active profile (default/safe/autonomous)")
    parser.add_argument("--mock", action="store_true", help="Same as --provider mock")
    parser.add_argument("--serve", action="store_true", help="Start App Server and block")
    parser.add_argument("--gui", action="store_true", help="Open desktop GUI window")
    parser.add_argument("--rescue-test", action="store_true", help="Run a mini rescue loop benchmark locally")
    parser.add_argument("task", nargs="?", help="Task to execute")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    config = Config(args.config)

    provider = args.provider
    if args.mock:
        provider = "mock"
    if not provider:
        provider = config.llm_provider()

    if args.serve:
        server = create_default_app_server(args.config, provider, port=args.port)
        try:
            server.start()
        except KeyboardInterrupt:
            server.stop()
        return

    if args.rescue_test:
        _run_rescue_test(args.config)
        return

    if args.gui:
        from gui import open_gui
        server = create_default_app_server(args.config, provider)
        try:
            open_gui(server, task=args.task)
        except Exception as e:
            print(f"[GUI] Failed to open desktop window: {e}")
            print("[GUI] Falling back to browser...")
            from gui import open_browser
            open_browser(task=args.task)
        return

    if not _ensure_server(args.config, provider):
        print("[Warn] App Server unavailable, falling back to local direct mode")
        _run_local(args.config, provider, args.profile, args.task)
        return

    print(f"[LLM] {provider}")

    if args.task:
        _run_task(args.task, profile=args.profile, provider=provider)
        return

    print_banner()
    while True:
        try:
            user_input = input("\n[You] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break
        if user_input.lower() == "status":
            state = _http_get("/health")
            if state:
                print(f"\n[Health] {state}")
            else:
                print("App Server not responding")
            continue

        _run_task(user_input, profile=args.profile, provider=provider)


def _run_local(config_path: str, provider: str, profile: Optional[str], task: Optional[str]) -> None:
    """Fallback local direct mode when App Server cannot start."""
    from agent.agent import TapMakerAgent
    from llm.llm_factory import LLMFactory

    config = Config(config_path)
    if profile:
        config._active_profile = profile
    try:
        llm = LLMFactory.create(provider, config)
        print(f"[LLM] {provider}")
    except Exception as e:
        print(f"[Error] LLM init failed: {e}")
        sys.exit(1)

    agent = TapMakerAgent(
        llm=llm,
        config=config,
        human_confirm_callback=confirm_callback,
    )

    if task:
        print(f"\n[Task] {task}")
        result = agent.run(task)
        print(f"\n[Result]\n{result.get('output', '')}")
        print(f"[Stats] iterations={result.get('iteration_count')} repair={result.get('repair_status')}")
        agent.close()
        return

    print_banner()
    while True:
        try:
            user_input = input("\n[You] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break
        if user_input.lower() == "status":
            state = agent.health.get_state()
            if state:
                print(f"\n[Health] {state.status}")
                print(f"  iterations: {state.iteration_count}")
                print(f"  errors: {state.error_count}")
                print(f"  token: {state.token_usage_ratio:.2%}")
            else:
                print("No health state")
            continue

        if user_input.lower().startswith("mock "):
            task = user_input[5:]
            agent_mock = TapMakerAgent(
                llm=LLMFactory.create("mock"),
                config=config,
                human_confirm_callback=confirm_callback,
            )
            result = agent_mock.run(task)
            print(f"\n[Mock Result]\n{result.get('output', '')}")
            agent_mock.close()
            continue

        result = agent.run(user_input)
        print(f"\n[Result]\n{result.get('output', '')}")
        print(f"[Stats] iterations={result.get('iteration_count')} repair={result.get('repair_status')}")

    agent.close()


def _run_rescue_test(config_path: str) -> None:
    """快速观察救援事件与遥测的 CLI 入口（使用 ScriptedExpertLLM，避免真实 API 费用）。"""
    import tempfile
    from pathlib import Path

    from agent.agent import TapMakerAgent
    from core.config import Config
    from tests.helpers.degraded_mock_llm import DegradedMockLLM
    from tests.helpers.scripted_expert_llm import ScriptedExpertLLM

    base_cfg = Config(config_path)
    tmpdir = Path(tempfile.mkdtemp(prefix="ttm_rescue_test_"))
    storage = tmpdir / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    (tmpdir / "hello.txt").write_text("hello from rescue test", encoding="utf-8")

    base_cfg.data["project_root"] = str(tmpdir)
    base_cfg.data["storage_root"] = str(storage)
    base_cfg.data["sandbox"] = {"mode": "workspace-write"}
    base_cfg.data["approval"] = {"policy": "never"}
    base_cfg.data["expert"] = base_cfg.data.get("expert", {})
    base_cfg.data["expert"]["enabled"] = True
    base_cfg.data["rescue"] = {
        "max_consecutive_errors": 2,
        "max_iterations_ratio": 0.75,
        "detect_repeated_actions": False,
        "health_degraded": False,
        "max_rescue_per_session": 1,
        "cooldown_seconds": 0,
        "max_takeover_steps": 5,
        "distill_after_rescue": True,
        "skip_if_no_expert_key": False,
    }
    base_cfg.data["learning"] = base_cfg.data.get("learning", {})
    base_cfg.data["learning"]["skill_generation_enabled"] = True

    local_llm = DegradedMockLLM(
        fail_steps=2,
        fail_action={"tool": "read_file", "params": {"path": "missing.txt"}},
        scripted_actions=[{"done": True, "output": "rescue test completed"}],
    )

    agent = TapMakerAgent(llm=local_llm, config=base_cfg, project_root=tmpdir, storage_root=storage)
    if agent.expert_rescuer:
        agent.expert_rescuer._llm = ScriptedExpertLLM([
            {
                "mode": "direct_action",
                "action": {"tool": "read_file", "params": {"path": "hello.txt"}},
                "thought": "先读取存在的 hello.txt",
                "skill_seed": {
                    "domain": "file",
                    "rule": "读取文件前先确认路径存在",
                    "context": "避免 missing.txt 类错误",
                },
            }
        ])

    print("[RescueTest] running mini rescue scenario...")
    result = agent.run("读取 hello.txt 的内容")

    print("\n[RescueTest] events:")
    for ev in agent.get_events(result.get("session_id", "")):
        if ev.get("type", "").startswith("rescue"):
            print(f"  {ev['type']}: {ev.get('payload', {})}")

    print(f"\n[RescueTest] output: {result.get('output', '')}")
    print(f"[RescueTest] iterations: {result.get('iteration_count')}")
    agent.close()


if __name__ == "__main__":
    main()
