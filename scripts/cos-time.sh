#!/usr/bin/env bash
# =============================================================================
# costime.sh — COS 时间戳铁律工具
#
# v3.13 铁律：所有文档时间戳必须精确到分钟（YYYY-MM-DD HH:MM）
#
# 用法：
#   ./scripts/cos-time.sh update <file>   — 更新单个文件 "## Last updated:" 行
#   ./scripts/cos-time.sh stamp <file>   — 在文件末尾追加时间戳
#   ./scripts/cos-time.sh verify         — 验证所有 docs/*.md 时间戳合规
#   ./scripts/cos-time.sh all           — 批量更新 docs/ 下所有文件
# =============================================================================

set -e

TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
DOCS_DIR="${DOCS_DIR:-docs}"

# ----- helpers -----

_last_updated_line() {
    grep -n "^## Last updated:" "$1" 2>/dev/null || true
}

# ----- commands -----

cmd_update() {
    local file="$1"
    [[ -f "$file" ]] || { echo "❌ not found: $file"; exit 1; }
    if grep -q "^## Last updated:" "$file"; then
        # In-place update on the "## Last updated:" line.
        sed -i.bak -E "s|^## Last updated: .*|## Last updated: $TIMESTAMP|" "$file"
        rm -f "$file.bak"
        echo "✓ updated: $file"
    else
        echo "" >> "$file"
        echo "## Last updated: $TIMESTAMP" >> "$file"
        echo "✓ appended: $file"
    fi
}

cmd_stamp() {
    local file="$1"
    [[ -f "$file" ]] || { echo "❌ not found: $file"; exit 1; }
    echo "" >> "$file"
    echo "## Last updated: $TIMESTAMP" >> "$file"
    echo "✓ stamped: $file"
}

cmd_verify() {
    local failed=0
    local checked=0
    while IFS= read -r -d '' file; do
        checked=$((checked + 1))
        if ! _last_updated_line "$file" | grep -qE "^## Last updated: [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$"; then
            echo "❌ missing or malformed: $file"
            failed=$((failed + 1))
        fi
    done < <(find "$DOCS_DIR" -type f -name "*.md" -print0 2>/dev/null)
    echo ""
    echo "checked: $checked | failed: $failed"
    [[ $failed -eq 0 ]]
}

cmd_all() {
    local updated=0
    while IFS= read -r -d '' file; do
        cmd_update "$file"
        updated=$((updated + 1))
    done < <(find "$DOCS_DIR" -type f -name "*.md" -print0 2>/dev/null)
    echo ""
    echo "updated: $updated files"
}

# ----- dispatch -----

case "${1:-}" in
    update)
        [[ -n "${2:-}" ]] || { echo "usage: $0 update <file>"; exit 1; }
        cmd_update "$2"
        ;;
    stamp)
        [[ -n "${2:-}" ]] || { echo "usage: $0 stamp <file>"; exit 1; }
        cmd_stamp "$2"
        ;;
    verify)
        cmd_verify
        ;;
    all)
        cmd_all
        ;;
    *)
        cat <<EOF
costime.sh — COS timestamp tool

usage:
  $0 update <file>   — update single file timestamp
  $0 stamp <file>    — append timestamp to file
  $0 verify          — verify all docs/*.md timestamps
  $0 all             — update all docs/*.md timestamps
EOF
        exit 1
        ;;
esac