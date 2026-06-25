"""Tauri lifecycle tests — verify the bridge+backend startup sequence.

These tests focus on the Python side of the Tauri ↔ Python integration. They
don't require the Rust binary to be compiled; instead they validate that the
Python `fast_ops_client` honors the bridge lifecycle (start, health check,
fallback on disconnect) and that the bridge contract is stable.

For the Rust-side integration tests, see `src-tauri/src/fast_ops_http.rs`
(in-module tests) and the `tests/test_fast_ops_http.py` protocol emulator.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import fast_ops_client


# ---------- in-process bridge emulator (full protocol) ----------


def _spawn_bridge_emulator() -> tuple:
    """Start a tiny HTTP server emulating the Rust bridge.

    Returns (host, port, shutdown_event, server).
    """
    import threading

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # silence
            pass

        def do_POST(self):  # type: ignore[no-untyped-def]
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"bad json"}')
                return
            command = self.path.strip("/").split("/")[-1]
            response = _dispatch(command, payload)
            body_out = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body_out)))
            self.end_headers()
            self.wfile.write(body_out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return host, port, server


def _dispatch(command: str, payload: dict) -> dict:
    if command == "fast_probe_port":
        return fast_ops_client._python_probe_port(
            payload.get("host", "127.0.0.1"),
            int(payload.get("port", 0)),
            int(payload.get("timeout_ms", 200)),
        )
    if command == "fast_format_bytes":
        return {"formatted": fast_ops_client._python_format_bytes(int(payload.get("bytes", 0)))}
    if command == "fast_dir_size":
        return fast_ops_client._python_dir_size(payload.get("path", ""))
    if command == "fast_list_dir":
        return fast_ops_client._python_list_dir(payload.get("path", ""))
    if command == "fast_tail_log":
        return fast_ops_client._python_tail_log(
            payload.get("path", ""),
            int(payload.get("max_bytes", 262144)),
        )
    return {"error": f"unknown: {command}"}


# ---------- fixtures ----------


@pytest.fixture
def live_bridge(monkeypatch):
    """Spawn an in-process bridge emulator and point fast_ops_client at it."""
    host, port, server = _spawn_bridge_emulator()
    monkeypatch.setattr(fast_ops_client, "_TAURI_HOST", host)
    monkeypatch.setattr(fast_ops_client, "_TAURI_PORT", port)
    monkeypatch.setattr(fast_ops_client, "_RUNTIME_AVAILABLE", None)
    yield host, port
    server.shutdown()
    server.server_close()


# ---------- bridge lifecycle ----------


def test_bridge_starts_and_accepts_connections(live_bridge):
    """When the Rust bridge starts, the Python client can detect it."""
    host, port = live_bridge
    # Sanity check: connect directly to verify the server is up.
    with socket.create_connection((host, port), timeout=1.0):
        pass


def test_python_client_detects_active_bridge(live_bridge):
    status = fast_ops_client.runtime_status()
    assert status["available"] is True


def test_python_client_falls_back_when_bridge_stops(monkeypatch):
    """If the bridge is unreachable, client falls back to Python."""
    monkeypatch.setattr(fast_ops_client, "_TAURI_HOST", "127.0.0.1")
    monkeypatch.setattr(fast_ops_client, "_TAURI_PORT", 1)
    monkeypatch.setattr(fast_ops_client, "_RUNTIME_AVAILABLE", None)
    status = fast_ops_client.runtime_status()
    assert status["available"] is False
    # Function should still return a result via Python fallback.
    result = fast_ops_client.fast_format_bytes(2048)
    assert result == "2.00KiB"


def test_runtime_cache_can_be_reset(monkeypatch, live_bridge):
    """After reset, runtime_status re-probes the bridge."""
    # First call — bridge is up
    status = fast_ops_client.runtime_status()
    assert status["available"] is True
    # Reset and pretend bridge died
    fast_ops_client.reset_runtime_cache()
    monkeypatch.setattr(fast_ops_client, "_TAURI_HOST", "127.0.0.1")
    monkeypatch.setattr(fast_ops_client, "_TAURI_PORT", 1)
    status = fast_ops_client.runtime_status()
    assert status["available"] is False


# ---------- protocol roundtrip ----------


def test_bridge_roundtrip_format_bytes(live_bridge):
    for value in [0, 512, 1024, 4096, 1024 * 1024, 5 * 1024 * 1024]:
        result = fast_ops_client.fast_format_bytes(value)
        expected = fast_ops_client._python_format_bytes(value)
        assert result == expected


def test_bridge_roundtrip_probe_port(live_bridge):
    """Bridge returns same shape as Python fallback."""
    a = fast_ops_client.fast_probe_port("127.0.0.1", 1, timeout_ms=50)
    b = fast_ops_client._python_probe_port("127.0.0.1", 1, timeout_ms=50)
    assert set(a.keys()) == set(b.keys())


def test_bridge_roundtrip_dir_size(live_bridge, tmp_path):
    (tmp_path / "f.txt").write_text("hello world")
    a = fast_ops_client.fast_dir_size(str(tmp_path))
    b = fast_ops_client._python_dir_size(str(tmp_path))
    assert a["file_count"] == b["file_count"]
    assert a["total_bytes"] == b["total_bytes"]


# ---------- error handling ----------


def test_bridge_call_timeout_falls_back(monkeypatch):
    """Calls to an unreachable bridge should fall back, not hang forever."""
    # Point at an unused port to force timeout
    monkeypatch.setattr(fast_ops_client, "_TAURI_HOST", "127.0.0.1")
    monkeypatch.setattr(fast_ops_client, "_TAURI_PORT", 1)
    monkeypatch.setattr(fast_ops_client, "_RUNTIME_AVAILABLE", None)

    started = time.time()
    result = fast_ops_client.fast_format_bytes(1024)
    elapsed = time.time() - started
    # Fallback path should complete quickly
    assert elapsed < 5.0
    assert result == "1.00KiB"


def test_bridge_call_with_unreachable_host_falls_back_quickly(monkeypatch):
    """An unreachable host should not block the caller."""
    monkeypatch.setattr(fast_ops_client, "_TAURI_HOST", "127.0.0.1")
    monkeypatch.setattr(fast_ops_client, "_TAURI_PORT", 64555)  # unlikely to be bound
    monkeypatch.setattr(fast_ops_client, "_RUNTIME_AVAILABLE", None)

    started = time.time()
    fast_ops_client.fast_dir_size("/tmp")
    elapsed = time.time() - started
    # Should fall back fast — well under the bridge timeout.
    assert elapsed < 3.0


# ---------- invariants ----------


def test_bridge_default_host_and_port():
    """The default bridge location matches Rust constants."""
    assert fast_ops_client._TAURI_HOST == "127.0.0.1"
    assert fast_ops_client._TAURI_PORT == 8766


def test_module_version_constant():
    assert fast_ops_client.FAST_OPS_VERSION == "fast-ops-client.v1"


def test_all_public_callables_exist():
    expected = [
        "fast_probe_port",
        "fast_find_available_port",
        "fast_tail_log",
        "fast_dir_size",
        "fast_list_dir",
        "fast_format_bytes",
        "runtime_status",
        "reset_runtime_cache",
    ]
    for name in expected:
        assert callable(getattr(fast_ops_client, name))