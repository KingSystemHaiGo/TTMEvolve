from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.maker_practice import MakerPracticeRunner


def test_maker_practice_runner_skip_flow_finishes_ready():
    with tempfile.TemporaryDirectory(dir=_PROJECT_ROOT) as tmp:
        root = Path(tmp)
        project = root / "workspace" / "smoke"
        runner = MakerPracticeRunner(root)

        started = runner.start(project_dir=project, skip_install=True, skip_init=True)
        assert started["ok"] is True

        deadline = time.time() + 5
        status = runner.status()
        while status.get("running") and time.time() < deadline:
            time.sleep(0.05)
            status = runner.status()

        assert status["status"] == "ready"
        assert status["step"] == "done"
        assert status["exit_code"] == 0
        assert project.exists()
        assert any("已跳过 Maker MCP 安装" in row["text"] for row in status["logs"])
        assert any("已跳过 Maker 项目初始化" in row["text"] for row in status["logs"])


def test_maker_practice_runner_passes_app_selection_to_init():
    with tempfile.TemporaryDirectory(dir=_PROJECT_ROOT) as tmp:
        root = Path(tmp)
        project = root / "workspace" / "smoke"
        runner = MakerPracticeRunner(root)
        calls = []

        def fake_run_command(args, *, cwd, app_selection):
            calls.append((args, cwd, app_selection))

        runner._run_command = fake_run_command  # type: ignore[method-assign]
        started = runner.start(
            project_dir=project,
            skip_install=True,
            skip_init=False,
            app_selection="0",
        )
        assert started["ok"] is True

        deadline = time.time() + 5
        status = runner.status()
        while status.get("running") and time.time() < deadline:
            time.sleep(0.05)
            status = runner.status()

        assert status["status"] == "ready"
        assert calls
        assert calls[0][0] == ["-y", "@taptap/maker", "init", "0"]
        assert calls[0][1] == project.resolve()
        assert calls[0][2] == "0"


if __name__ == "__main__":
    test_maker_practice_runner_skip_flow_finishes_ready()
    test_maker_practice_runner_passes_app_selection_to_init()
    print("[PASS] maker practice")
