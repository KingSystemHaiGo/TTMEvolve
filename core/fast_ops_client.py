"""Fast ops client — Python wrapper around Rust-side fast_ops commands.

The Tauri Rust shell exposes a set of fast operations (port probing, log
tailing, dir sizing, file listing, byte formatting) that replace the
equivalent Python implementations when running inside the desktop app.

This module provides a clean Python interface so the rest of TTMEvolve can
call into Rust without caring about the underlying transport.

Usage:
    from core.fast_ops_client import fast_probe_port, fast_tail_log

    result = fast_probe_port("127.0.0.1", 8765)
    if not result["available"]:
        log_tail = fast_tail_log("/var/log/ttmevolve.log")

When the Rust runtime is unavailable (browser dev / tests), the module
silently falls back to a Python implementation so callers don't need to
branch on environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


FAST_OPS_VERSION = "fast-ops-client.v1"


_TAURI_HOST = os.environ.get("TTM_TAURI_HOST", "127.0.0.1")
_TAURI_PORT = int(os.environ.get("TTM_TAURI_PORT", "8766"))
_RUNTIME_AVAILABLE: Optional[bool] = None


def _runtime_available() -> bool:
    """Cache whether the Rust runtime is reachable."""
    global _RUNTIME_AVAILABLE
    if _RUNTIME_AVAILABLE is not None:
        return _RUNTIME_AVAILABLE
    # We probe a port that the Rust shell may expose; if it's reachable we
    # assume the fast_ops bridge is live. In production this is wired up by
    # server_manager::start (future v0.7.2 work).
    try:
        import socket
        with socket.create_connection((_TAURI_HOST, _TAURI_PORT), timeout=0.1):
            _RUNTIME_AVAILABLE = True
            return True
    except OSError:
        _RUNTIME_AVAILABLE = False
        return False


def _python_probe_port(host: str, port: int, timeout_ms: int = 200) -> Dict[str, Any]:
    """Pure-Python fallback for port probing."""
    import socket
    started_at = _now()
    try:
        with socket.create_connection((host, port), timeout=timeout_ms / 1000):
            return {
                "host": host,
                "port": port,
                "available": True,
                "latency_ms": (_now() - started_at) * 1000,
            }
    except OSError:
        return {
            "host": host,
            "port": port,
            "available": False,
            "latency_ms": (_now() - started_at) * 1000,
        }


def _python_tail_log(path: str, max_bytes: int = 262144) -> Dict[str, Any]:
    """Pure-Python fallback for log tailing."""
    p = Path(path)
    if not p.exists():
        return {
            "path": path,
            "total_bytes": 0,
            "tail_bytes": 0,
            "lines": [],
            "truncated": False,
        }
    total = p.stat().st_size
    read_bytes = min(max_bytes, total)
    with p.open("rb") as f:
        if total > read_bytes:
            f.seek(total - read_bytes)
        data = f.read(read_bytes)
    text = data.decode("utf-8", errors="replace")
    return {
        "path": path,
        "total_bytes": total,
        "tail_bytes": read_bytes,
        "lines": text.splitlines(),
        "truncated": total > read_bytes,
    }


def _python_dir_size(path: str) -> Dict[str, Any]:
    """Pure-Python fallback for directory size."""
    total = 0
    file_count = 0
    for root, _, files in os.walk(path):
        for filename in files:
            file_path = Path(root) / filename
            try:
                total += file_path.stat().st_size
                file_count += 1
            except OSError:
                pass
    return {"path": path, "file_count": file_count, "total_bytes": total}


def _python_list_dir(path: str) -> List[Dict[str, Any]]:
    """Pure-Python fallback for directory listing."""
    p = Path(path)
    if not p.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for entry in p.iterdir():
        try:
            stat = entry.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size,
            }
        )
    return entries


def _python_format_bytes(n: int) -> str:
    """Pure-Python IEC byte formatter."""
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    if n < 1024:
        return f"{n}B"
    value = float(n)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:.2f}{units[idx]}"


def _now() -> float:
    import time
    return time.perf_counter()


# ---------- public API ----------


def fast_probe_port(host: str, port: int, timeout_ms: int = 200) -> Dict[str, Any]:
    if _runtime_available():
        try:
            return _invoke_rust("fast_probe_port", {
                "host": host, "port": port, "timeout_ms": timeout_ms,
            })
        except Exception:
            pass
    return _python_probe_port(host, port, timeout_ms)


def fast_find_available_port(
    host: str, start: int, limit: int, timeout_ms: int = 200,
) -> Optional[int]:
    if _runtime_available():
        try:
            return _invoke_rust(
                "fast_find_available_port",
                {"host": host, "start": start, "limit": limit, "timeout_ms": timeout_ms},
            )
        except Exception:
            pass
    for offset in range(limit + 1):
        port = start + offset
        if _python_probe_port(host, port, timeout_ms)["available"]:
            return port
    return None


def fast_tail_log(path: str, max_bytes: int = 262144) -> Dict[str, Any]:
    if _runtime_available():
        try:
            return _invoke_rust(
                "fast_tail_log", {"path": path, "max_bytes": max_bytes},
            )
        except Exception:
            pass
    return _python_tail_log(path, max_bytes)


def fast_dir_size(path: str) -> Dict[str, Any]:
    if _runtime_available():
        try:
            return _invoke_rust("fast_dir_size", {"path": path})
        except Exception:
            pass
    return _python_dir_size(path)


def fast_list_dir(path: str) -> List[Dict[str, Any]]:
    if _runtime_available():
        try:
            return _invoke_rust("fast_list_dir", {"path": path})
        except Exception:
            pass
    return _python_list_dir(path)


def fast_format_bytes(n: int) -> str:
    if _runtime_available():
        try:
            return _invoke_rust("fast_format_bytes", {"bytes": n})
        except Exception:
            pass
    return _python_format_bytes(n)


def _invoke_rust(command: str, args: Dict[str, Any]) -> Any:
    """Place-holder for the future HTTP bridge to the Tauri Rust runtime.

    Today the Rust runtime is not yet wired into Python; the function raises
    NotImplementedError so callers fall through to the Python fallback.
    """
    raise NotImplementedError(
        f"Rust runtime bridge not yet active (command={command}). "
        "Falling back to Python implementation."
    )


def runtime_status() -> Dict[str, Any]:
    """Return whether the Rust fast_ops bridge is available right now."""
    return {
        "version": FAST_OPS_VERSION,
        "host": _TAURI_HOST,
        "port": _TAURI_PORT,
        "available": _runtime_available(),
    }


def reset_runtime_cache() -> None:
    """Force the next call to re-probe runtime availability. Tests only."""
    global _RUNTIME_AVAILABLE
    _RUNTIME_AVAILABLE = None