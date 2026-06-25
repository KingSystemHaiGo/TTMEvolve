"""
tests/test_asset_endpoints.py — 素材库端点与媒体预览测试
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

TEST_PORT = 17346


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
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/health", timeout=0.1):
                break
        except Exception:
            time.sleep(0.05)
    yield srv
    srv.stop()


def _get_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{TEST_PORT}{path}", timeout=2
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"error": body}
        data["_http_status"] = e.code
        return data


def test_assets_scan_and_filter(server: AppServer, tmp_path: Path):
    (tmp_path / "img.png").write_bytes(b"png")
    (tmp_path / "audio.mp3").write_bytes(b"mp3")
    (tmp_path / "video.mp4").write_bytes(b"mp4")
    (tmp_path / "text.txt").write_text("text", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "bad.png").write_bytes(b"bad")

    res = _get_json("/fs/assets?path=.")
    assert res.get("ok") is True, res
    assets = res["assets"]
    names = {a["name"] for a in assets}
    assert "img.png" in names
    assert "audio.mp3" in names
    assert "video.mp4" in names
    assert "text.txt" not in names
    assert "bad.png" not in names

    for a in assets:
        assert a["type"] in {"image", "audio", "video"}
        assert "size" in a
        assert "path" in a

    res2 = _get_json("/fs/assets?path=.&extensions=.png,.mp4")
    names2 = {a["name"] for a in res2["assets"]}
    assert names2 == {"img.png", "video.mp4"}
    print("[PASS] assets scan and filter")


def test_stat_file(server: AppServer, tmp_path: Path):
    (tmp_path / "foo.txt").write_text("hello", encoding="utf-8")
    res = _get_json("/fs/stat?path=foo.txt")
    assert res.get("ok") is True, res
    assert res["name"] == "foo.txt"
    assert res["size"] == 5
    assert res["is_dir"] is False
    assert "modified" in res
    print("[PASS] stat file")


def test_stat_sandbox_rejects_outside(server: AppServer):
    res = _get_json("/fs/stat?path=../outside.txt")
    assert res.get("ok") is False or res.get("_http_status") == 403
    print("[PASS] stat sandbox rejection")


def test_preview_mime_for_media(server: AppServer, tmp_path: Path):
    (tmp_path / "pic.webp").write_bytes(b"RIFF....WEBP")
    (tmp_path / "snd.ogg").write_bytes(b"OggS")
    (tmp_path / "clip.mkv").write_bytes(b"\x1a\x45\xdf\xa3")

    cases = [
        ("pic.webp", "image/webp"),
        ("snd.ogg", "audio/ogg"),
        ("clip.mkv", "video/x-matroska"),
    ]
    for fname, expected_mime in cases:
        req = urllib.request.Request(
            f"http://127.0.0.1:{TEST_PORT}/preview/file?path={fname}"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Type") == expected_mime
    print("[PASS] preview MIME for media")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        server = _make_server(tmpdir)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            test_assets_scan_and_filter(tmpdir)
            test_stat_file(tmpdir)
            test_stat_sandbox_rejects_outside()
            test_preview_mime_for_media(tmpdir)
            print("[PASS] all asset endpoint tests")
        finally:
            server.stop()
