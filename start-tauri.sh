#!/usr/bin/env bash
# =============================================================================
# TTMEvolve 启动脚本 (Linux/macOS) — 优先内嵌环境
#
# v0.9.0 增强：
#   - 跨平台：Linux + macOS
#   - 优先 portable 内嵌环境
#   - 自动检测系统 Python
#   - 启动器 / CLI 模式选择
#   - 友好的错误信息
# =============================================================================

set -e
cd "$(dirname "$0")"

# 平台检测
PLATFORM="$(uname -s 2>/dev/null || echo Unknown)"
case "$PLATFORM" in
    Linux*)   PLATFORM_TAG="linux" ;;
    Darwin*)  PLATFORM_TAG="macos" ;;
    *)        PLATFORM_TAG="unknown" ;;
esac
echo "[start-tauri] platform: $PLATFORM_TAG"

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
    echo "[start-tauri] please install Python 3.10+ or run scripts/build-portable/build_all.py"
    exit 1
fi

# 2. 内嵌 Node
if [ -x "./portable/node/bin/node" ]; then
    NODE_EXE="$(pwd)/portable/node/bin/node"
    echo "[start-tauri] using embedded node: $NODE_EXE"
elif command -v node >/dev/null 2>&1; then
    NODE_EXE="$(command -v node)"
    echo "[start-tauri] using system node: $NODE_EXE"
fi

export PYTHON_EXE NODE_EXE

# 3. 模式选择
MODE="gui"
if [ "${1:-}" = "--cli" ]; then
    MODE="cli"
    shift
elif [ "${1:-}" = "--headless" ]; then
    MODE="headless"
    shift
fi
echo "[start-tauri] mode: $MODE"

# 4. 启动应用
case "$MODE" in
    gui)
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
        ;;
    cli|headless)
        exec "$PYTHON_EXE" main.py --embedded "$@"
        ;;
    *)
        echo "[start-tauri] unknown mode: $MODE"
        exit 1
        ;;
esac