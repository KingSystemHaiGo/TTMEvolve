from __future__ import annotations

import json
import sys
import time


def write(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


initialized = False

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")

    if method == "initialize":
        write({
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-maker", "version": "0.0.0"},
            },
        })
        continue

    if method == "notifications/initialized":
        initialized = True
        continue

    if method == "tools/list":
        if not initialized:
            write({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32002, "message": "not initialized"},
            })
            continue
        write({
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": [
                    {
                        "name": "maker_ping",
                        "description": "fake TapTap Maker tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                            "required": ["message"],
                        },
                    },
                    {
                        "name": "maker_slow",
                        "description": "fake slow TapTap Maker tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"delay": {"type": "number"}},
                        },
                    },
                    {
                        "name": "maker_list_tasks",
                        "description": "list remote Maker build tasks with task ids",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "maker_list_files",
                        "description": "list remote Maker files and assets with file ids",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "maker_business_fail",
                        "description": "fake tool with successful MCP transport but failed remote business result",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    }
                ]
            },
        })
        continue

    if method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")
        args = request.get("params", {}).get("arguments", {})
        if tool_name == "maker_slow":
            time.sleep(float(args.get("delay", 2)))
            write({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {
                    "content": [
                        {"type": "text", "text": "slow-done"}
                    ]
                },
            })
            continue
        if tool_name == "maker_list_tasks":
            write({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {
                    "tasks": [
                        {"task_id": "task-1", "status": "done"}
                    ]
                },
            })
            continue
        if tool_name == "maker_list_files":
            write({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {
                    "files": [
                        {"file_id": "file-1", "path": "scripts/main.lua"}
                    ]
                },
            })
            continue
        if tool_name == "maker_business_fail":
            write({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "500 图片编辑失败，请稍后重试"}
                    ],
                    "structuredContent": {
                        "success": False,
                        "error": "500 图片编辑失败，请稍后重试",
                    },
                },
            })
            continue
        write({
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "content": [
                    {"type": "text", "text": f"pong:{args.get('message', '')}"}
                ]
            },
        })
        continue

    write({
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    })
