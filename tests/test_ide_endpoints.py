"""
tests/test_ide_endpoints.py — IDE 文件系统端点测试
"""

from __future__ import annotations
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from llm.llm_factory import LLMFactory
from server.app_server import AppServer
from server.approval_bridge import ApprovalBridge

TEST_PORT = 17345


def _make_server(tmpdir: Path) -> AppServer:
    config_path = tmpdir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "llm": {"provider": "mock"},
                "project_root": str(tmpdir),
                "storage_root": str(tmpdir / "storage"),
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "on-request"},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(str(config_path))
    llm = LLMFactory.create("mock", cfg)
    agent = TapMakerAgent(llm=llm, config=cfg)
    return AppServer(agent, port=TEST_PORT, approval_bridge=ApprovalBridge())


@pytest.fixture
def server(tmp_path: Path):
    """为每个测试启动一个隔离的 AppServer。"""
    srv = _make_server(tmp_path)
    thread = threading.Thread(target=srv.start, daemon=True)
    thread.start()
    # 等待服务器就绪
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/health", timeout=0.1):
                break
        except Exception:
            time.sleep(0.05)
    yield srv
    srv.stop()


def _post_json(path: str, data: dict) -> dict:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{TEST_PORT}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}{path}", timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"error": body}
        data["_http_status"] = e.code
        return data


def test_ide_fs_crud(server: AppServer, tmp_path: Path):
    # write
    write_res = _post_json("/fs/write", {"path": "hello.txt", "content": "world"})
    assert write_res.get("ok") is True, write_res

    # list
    list_res = _get_json("/fs/list?path=.")
    assert list_res.get("ok") is True
    items = list_res["items"]
    assert any(item["name"] == "hello.txt" and not item["is_dir"] for item in items)

    # read
    read_res = _get_json("/fs/read?path=hello.txt")
    assert read_res.get("ok") is True
    assert read_res["content"] == "world"

    # preview raw
    with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/preview/file?path=hello.txt", timeout=2) as resp:
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert body == "world"

    # delete
    del_res = _post_json("/fs/delete", {"path": "hello.txt"})
    assert del_res.get("ok") is True

    list_res2 = _get_json("/fs/list?path=.")
    assert not any(item["name"] == "hello.txt" for item in list_res2["items"])
    print("[PASS] /fs CRUD")


def test_ide_sandbox_rejects_outside_path(server: AppServer):
    read_res = _get_json("/fs/read?path=../outside.txt")
    assert read_res.get("ok") is False or read_res.get("_http_status") == 403
    print("[PASS] sandbox rejects outside path")


def test_ide_directory_sorting(server: AppServer, tmp_path: Path):
    (tmp_path / "z_file.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_dir" / "inner.txt").write_text("i", encoding="utf-8")

    list_res = _get_json("/fs/list?path=.")
    assert list_res.get("ok") is True
    names = [item["name"] for item in list_res["items"]]
    assert names.index("a_dir") < names.index("z_file.txt")
    print("[PASS] directory sorting")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        server = _make_server(tmpdir)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            test_ide_fs_crud()
            test_ide_sandbox_rejects_outside_path()
            test_ide_directory_sorting(tmpdir)
            print("[PASS] all IDE endpoint tests")
        finally:
            server.stop()
