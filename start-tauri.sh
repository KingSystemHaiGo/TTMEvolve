#!/usr/bin/env bash
# =============================================================================
# TTMEvolve 启动脚本 (Linux/macOS) — 优先内嵌环境
# =============================================================================

set -e
cd "$(dirname "$0")"

PYTHON_EXE=""
NODE_EXE=""

# 1. 内嵌 Python (portable)
if [ -x "./portable/python/bin/python3" ]; then
    PYTHON_EXE="$(pwd)/portable/python/bin/python3"
    echo "[start-tauri] using embedded python: $PYTHON_EXE"
elif [ -x "./portable/python/bin/python" ]; then
    PYTHON_EXE="$(pwd)/portable/python/bin/python"
    echo "[start-tauri] using embedded python: $PYTHON_EXE"
elif [ -x "./.venv/bin/python3" ]; then
    PYTHON_EXE="$(pwd)/.venv/bin/python3"
    echo "[start-tauri] using venv python: $PYTHON_EXE"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python3)"
    echo "[start-tauri] using system python: $PYTHON_EXE"
else
    echo "[start-tauri] ERROR: no python found"
    exit 1
fi

# 2. 内嵌 Node
if [ -x "./portable/node/bin/node" ]; then
    NODE_EXE="$(pwd)/portable/node/bin/node"
fi

export PYTHON_EXE NODE_EXE

# 启动应用
if [ -x "./src-tauri/target/release/ttmevolve" ]; then
    echo "[start-tauri] starting production build"
    exec "./src-tauri/target/release/ttmevolve"
elif [ -x "./src-tauri/target/debug/ttmevolve" ]; then
    echo "[start-tauri] starting debug build"
    exec "./src-tauri/target/debug/ttmevolve"
else
    echo "[start-tauri] no built binary; falling back to python main.py"
    exec "$PYTHON_EXE" main.py --embedded "$@"
fi