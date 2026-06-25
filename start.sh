#!/usr/bin/env bash
set -e

export PYTHONIOENCODING=utf-8
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "[TTMEvolve] 工作目录: $PROJECT_ROOT"

# Detect Python: prefer vendor/python, fallback to system python3/python
VENDOR_PYTHON="$PROJECT_ROOT/vendor/python/bin/python3"
PYTHON=""
if [ -f "$VENDOR_PYTHON" ]; then
    PYTHON="$VENDOR_PYTHON"
    export TTM_PYTHON_EXE="$VENDOR_PYTHON"
    echo "[TTMEvolve] 使用内嵌 Python: $VENDOR_PYTHON"
fi
if [ -z "$PYTHON" ]; then
    if command -v python3 &> /dev/null; then
        PYTHON="python3"
    elif command -v python &> /dev/null; then
        PYTHON="python"
    else
        echo "[TTMEvolve] 错误: 未找到 python3/python"
        exit 1
    fi
fi

$PYTHON --version

# Detect Node: prefer vendor/node
VENDOR_NODE="$PROJECT_ROOT/vendor/node/bin/node"
if [ -f "$VENDOR_NODE" ]; then
    export PATH="$(dirname "$VENDOR_NODE"):$PATH"
    export TTM_NODE_EXE="$VENDOR_NODE"
    echo "[TTMEvolve] 使用内嵌 Node: $VENDOR_NODE"
fi

# Detect Git: prefer vendor/git
VENDOR_GIT="$PROJECT_ROOT/vendor/git/bin/git"
if [ -f "$VENDOR_GIT" ]; then
    export PATH="$(dirname "$VENDOR_GIT"):$PATH"
    export TTM_GIT_EXE="$VENDOR_GIT"
    echo "[TTMEvolve] 使用内嵌 Git: $VENDOR_GIT"
fi

# Load embedded environment variables
ENV_FILE="$PROJECT_ROOT/.env.embedded"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
    echo "[TTMEvolve] 已加载 .env.embedded"
fi

if [ ! -f config.json ]; then
    echo "[TTMEvolve] config.json 不存在，正在从 config.example.json 复制..."
    cp config.example.json config.json
    echo "[TTMEvolve] 已创建 config.json，请按需修改后重新启动。"
    exit 1
fi

if [ ! -d .venv ]; then
    echo "[TTMEvolve] 正在创建虚拟环境..."
    "$PYTHON" -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

VENV_PYTHON=".venv/bin/python"

echo "[TTMEvolve] 正在检查/安装环境..."
if ! "$VENV_PYTHON" scripts/bootstrap.py; then
    echo "[TTMEvolve] 环境初始化失败。"
    echo "可能原因：网络连接问题，无法从 PyPI 下载依赖。"
    echo "你可以尝试："
    echo "  - 检查网络后重新运行 ./start.sh"
    echo "  - 手动安装依赖：$VENV_PYTHON -m pip install -r requirements.txt"
    echo "[TTMEvolve] 正在以 Mock 模式启动..."
    "$VENV_PYTHON" main.py --provider mock "$@"
    exit $?
fi

echo "[TTMEvolve] 启动自进化 TapMaker Agent..."
"$VENV_PYTHON" main.py "$@"
