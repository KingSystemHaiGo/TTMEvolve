"""
agent/mcp_client.py - lightweight stdio client for the TapTap Maker MCP server.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class MakerMCPClient:
    """Connects to a Maker MCP server and forwards tool calls."""

    def __init__(
        self,
        command: str,
        args: List[str],
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        request_timeout_seconds: float = 30.0,
    ):
        self.command = command
        self.args = args
        self.cwd = Path(cwd)
        self.extra_env = env or {}
        self.request_timeout_seconds = float(request_timeout_seconds or 30.0)
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._tools: List[Dict[str, Any]] = []
        self._server_info: Dict[str, Any] = {}

    def start(self) -> None:
        env = os.environ.copy()
        env.update(self.extra_env)
        self._process = subprocess.Popen(
            [self.command] + self.args,
            cwd=self.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        time.sleep(0.2)
        self._initialize()
        self._tools = self._list_tools()

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def _send(
        self,
        msg: Dict[str, Any],
        read_response: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("MCP server not running")
        if not self._process.stdin or not self._process.stdout:
            raise RuntimeError("MCP server stdio is unavailable")

        data = json.dumps(msg) + "\n"
        with self._lock:
            self._process.stdin.write(data)
            self._process.stdin.flush()
            if not read_response:
                return None
            expected_id = msg.get("id")
            while True:
                try:
                    line = self._read_stdout_line(timeout_seconds=timeout_seconds)
                except TimeoutError:
                    self.stop()
                    raise
                if not line:
                    return None
                response = json.loads(line)
                if expected_id is None or response.get("id") == expected_id:
                    return response

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            },
            read_response=False,
        )

    def _initialize(self) -> None:
        """Run the MCP initialization handshake before listing tools."""
        self._request_id += 1
        response = self._send({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "TTMEvolve",
                    "version": "0.4.0",
                },
            },
        })
        if not response:
            raise RuntimeError("MCP server returned empty initialize response")
        if "error" in response:
            raise RuntimeError(f"MCP initialize failed: {response['error']}")
        self._server_info = response.get("result", {})
        self._notify("notifications/initialized")

    def _list_tools(self) -> List[Dict[str, Any]]:
        self._request_id += 1
        response = self._send({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/list",
            "params": {},
        })
        if not response:
            return []
        if "error" in response:
            raise RuntimeError(f"MCP tools/list failed: {response['error']}")
        result = response.get("result", {})
        return result.get("tools", [])

    def list_tools(self) -> List[Dict[str, Any]]:
        return self._tools

    def call(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        self._request_id += 1
        response = self._send({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params,
            },
        }, timeout_seconds=timeout_seconds)
        if not response:
            return {"ok": False, "error": "MCP server returned empty response"}
        if "error" in response:
            return {"ok": False, "error": response["error"]}
        result = response.get("result", {})
        business_error = _tool_business_error(result)
        if business_error:
            return {
                "ok": False,
                "error": business_error,
                "error_type": "remote_business_failure",
                "failure_type": "remote_business_failure",
                "result": result,
                "result_is_error": bool(isinstance(result, dict) and result.get("isError")),
                "structured_success": _structured_success(result),
            }
        return {"ok": True, "result": result}

    def __call__(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        return self.call(tool_name, kwargs)

    def _read_stdout_line(self, timeout_seconds: Optional[float] = None) -> str:
        if not self._process or not self._process.stdout:
            raise RuntimeError("MCP server stdio is unavailable")
        timeout = self._resolve_timeout(timeout_seconds)
        lines: "queue.Queue[str]" = queue.Queue(maxsize=1)

        def read_line() -> None:
            try:
                lines.put(self._process.stdout.readline())
            except Exception:
                lines.put("")

        thread = threading.Thread(target=read_line, daemon=True)
        thread.start()
        try:
            return lines.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"MCP request timed out after {timeout:.1f}s")

    def _resolve_timeout(self, timeout_seconds: Optional[float]) -> float:
        try:
            timeout = float(timeout_seconds) if timeout_seconds is not None else self.request_timeout_seconds
        except (TypeError, ValueError):
            timeout = self.request_timeout_seconds
        return max(0.1, timeout)


def _tool_business_error(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    structured = result.get("structuredContent")
    if result.get("isError"):
        return _extract_tool_error(result) or "MCP tool returned an error result"
    if isinstance(structured, dict) and structured.get("success") is False:
        return _extract_tool_error(result) or "MCP tool returned success=false"
    return ""


def _structured_success(result: Any) -> Optional[bool]:
    if not isinstance(result, dict):
        return None
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("success"), bool):
        return structured.get("success")
    return None


def _extract_tool_error(result: Dict[str, Any]) -> str:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("error", "message", "reason", "detail"):
            value = structured.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        errors = structured.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(item) for item in errors[:3])

    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""
