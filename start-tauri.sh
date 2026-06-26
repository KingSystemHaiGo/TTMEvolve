#!/usr/bin/env bash
# =============================================================================
# TTMEvolve launcher (Linux/macOS) - prefers portable runtime
#
# v0.9.0 enhanced:
#   - cross-platform: Linux + macOS
#   - portable Python first, then .venv, then system Python
#   - GUI / CLI / headless modes
#   - source checkout GUI fallback builds frontend and runs Tauri with Cargo
#   - friendly error messages
# =============================================================================

set -e
cd "$(dirname "$0")"

PLATFORM="$(uname -s 2>/dev/null || echo Unknown)"
case "$PLATFORM" in
    Linux*)   PLATFORM_TAG="linux" ;;
    Darwin*)  PLATFORM_TAG="macos" ;;
    *)        PLATFORM_TAG="unknown" ;;
esac
echo "[start-tauri] platform: $PLATFORM_TAG"

PYTHON_EXE=""

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

MODE="gui"
if [ "${1:-}" = "--cli" ]; then
    MODE="cli"
    shift
elif [ "${1:-}" = "--headless" ]; then
    MODE="headless"
    shift
fi
echo "[start-tauri] mode: $MODE"

export TTM_PYTHON_EXE="$PYTHON_EXE"
export TTMEVOLVE_ROOT="$(pwd)"

case "$MODE" in
    gui)
        if [ -x "./src-tauri/target/release/ttmevolve" ]; then
            echo "[start-tauri] starting production build"
            exec "./src-tauri/target/release/ttmevolve" "$@"
        elif [ -x "./src-tauri/target/debug/ttmevolve" ]; then
            echo "[start-tauri] starting debug build"
            exec "./src-tauri/target/debug/ttmevolve" "$@"
        fi

        if ! command -v cargo >/dev/null 2>&1; then
            echo "[start-tauri] ERROR: no built Tauri binary found and Cargo is unavailable"
            echo "[start-tauri] install Rust/Cargo or use a packaged TTMEvolve build"
            exit 1
        fi
        if ! command -v npm >/dev/null 2>&1; then
            echo "[start-tauri] ERROR: npm not found; cannot build frontend for Tauri"
            echo "[start-tauri] please install Node.js or run scripts/build-portable/build_all.py"
            exit 1
        fi

        echo "[start-tauri] no built binary; building frontend for Tauri"
        npm --prefix frontend run build

        echo "[start-tauri] starting Tauri from source with Cargo"
        exec cargo run --manifest-path src-tauri/Cargo.toml -- "$@"
        ;;
    cli|headless)
        exec "$PYTHON_EXE" main.py --embedded "$@"
        ;;
    *)
        echo "[start-tauri] unknown mode: $MODE"
        exit 1
        ;;
esac
