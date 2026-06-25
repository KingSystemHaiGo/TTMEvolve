"""Tests for the fast_ops client (Python fallback path is always exercised
when the Rust runtime is not wired up, which is the current state)."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import fast_ops_client


# ---------- fallback (Python) path ----------


def test_python_fallback_probe_port_unavailable():
    result = fast_ops_client.fast_probe_port("127.0.0.1", 1, timeout_ms=50)
    assert result["available"] is False
    assert result["port"] == 1


def test_python_fallback_probe_port_available():
    """Start a listener, then probe its port."""
    import socket
    import threading
    server = socket.create_server(("127.0.0.1", 0))
    port = server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) or server
    addr = server.getsockname()
    port = addr[1]
    # Run probe in background, then close server to free the port.
    try:
        result = fast_ops_client.fast_probe_port("127.0.0.1", port, timeout_ms=200)
        assert result["available"] is True
        assert result["port"] == port
    finally:
        server.close()


def test_python_fallback_find_available_port():
    """find_available_port should return the listener's port when bound."""
    import socket
    server = socket.create_server(("127.0.0.1", 0))
    addr = server.getsockname()
    bound_port = addr[1]
    try:
        result = fast_ops_client.fast_find_available_port(
            "127.0.0.1", start=bound_port, limit=1, timeout_ms=200,
        )
        # The bound port is taken, so the search should find the next one.
        assert result is not None
        assert result >= bound_port
    finally:
        server.close()


def test_python_fallback_tail_log_existing_file():
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
        for i in range(500):
            f.write(f"line {i}\n")
        path = f.name
    try:
        result = fast_ops_client.fast_tail_log(path, max_bytes=512)
        assert result["path"] == path
        assert result["total_bytes"] > 0
        assert result["lines"], "expected non-empty lines"
        assert result["truncated"] is True  # 500 lines > 512 bytes
    finally:
        Path(path).unlink()


def test_python_fallback_tail_log_missing_file():
    result = fast_ops_client.fast_tail_log("/nonexistent/path/that/does/not/exist")
    assert result["lines"] == []
    assert result["total_bytes"] == 0


def test_python_fallback_dir_size_empty():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = fast_ops_client.fast_dir_size(tmpdir)
        assert result["file_count"] == 0
        assert result["total_bytes"] == 0


def test_python_fallback_dir_size_with_files():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(3):
            (Path(tmpdir) / f"f{i}.txt").write_text("hello")
        result = fast_ops_client.fast_dir_size(tmpdir)
        assert result["file_count"] == 3
        assert result["total_bytes"] >= 15


def test_python_fallback_list_dir_returns_files_and_dirs():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "file.txt").write_text("x")
        (Path(tmpdir) / "subdir").mkdir()
        entries = fast_ops_client.fast_list_dir(tmpdir)
        names = {entry["name"] for entry in entries}
        assert "file.txt" in names
        assert "subdir" in names
        subdir_entry = next(e for e in entries if e["name"] == "subdir")
        assert subdir_entry["is_dir"] is True
        file_entry = next(e for e in entries if e["name"] == "file.txt")
        assert file_entry["is_dir"] is False
        assert file_entry["size_bytes"] == 1


def test_python_fallback_list_dir_missing_path():
    assert fast_ops_client.fast_list_dir("/nonexistent/path") == []


def test_python_fallback_format_bytes():
    assert fast_ops_client.fast_format_bytes(0) == "0B"
    assert fast_ops_client.fast_format_bytes(1024) == "1.00KiB"
    assert fast_ops_client.fast_format_bytes(1024 * 1024) == "1.00MiB"
    assert fast_ops_client.fast_format_bytes(2 * 1024 * 1024 * 1024) == "2.00GiB"


# ---------- runtime status ----------


def test_runtime_status_returns_version_and_host():
    status = fast_ops_client.runtime_status()
    assert status["version"] == fast_ops_client.FAST_OPS_VERSION
    assert "host" in status
    assert "port" in status
    assert "available" in status


def test_runtime_status_available_is_false_when_tauri_unreachable():
    fast_ops_client.reset_runtime_cache()
    status = fast_ops_client.runtime_status()
    # In test/CI without Tauri shell running, the bridge is unavailable.
    # The fallback path is exercised, so available should be False.
    assert status["available"] is False


# ---------- public symbols ----------


def test_module_exposes_expected_callables():
    for name in (
        "fast_probe_port",
        "fast_find_available_port",
        "fast_tail_log",
        "fast_dir_size",
        "fast_list_dir",
        "fast_format_bytes",
        "runtime_status",
        "reset_runtime_cache",
    ):
        assert callable(getattr(fast_ops_client, name)), f"missing callable: {name}"