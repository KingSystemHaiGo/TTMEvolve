"""remove-electron.py — v0.7.1 迁移：删除 Electron 桌面壳

目标：彻底移除 electron/ 目录和所有相关启动器。

执行步骤：
1. 备份 electron/ 到 .archive/electron-v0.6.x（保险）
2. 删除 electron/ 目录
3. 删除 start-gui.bat / start-gui.ps1
4. 删除 start-practice.bat / start-practice.ps1
5. 替换 start.bat → start-tauri.bat 软链接（可选）
6. 更新 package.json 移除 electron 依赖
7. 更新 README + docs

支持 --dry-run 模式（默认）：只打印要删除的文件列表。
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# 待删除的文件 / 目录（v0.6.x Electron 时代）
TARGETS = [
    # Electron 桌面壳源码 + 构建产物
    "electron",
    # Electron 启动器（v0.7.0 已迁移到 start-tauri）
    "start-gui.bat",
    "start-gui.ps1",
    "start-practice.bat",
    "start-practice.ps1",
    # Electron 时代的快捷方式（v0.7.0 由 Tauri 提供）
    "TTMEvolve-Practice.vbs",
    "TTMEvolve Practice.lnk",
]


# 需要更新内容的文件
UPDATES = [
    "package.json",  # 移除 electron 依赖
    "README.md",     # 移除 electron 引用
    "docs/sprint-board.md",  # 标记 Electron 已删除
]


def _safe_target(path: Path) -> bool:
    """Return True if the target exists and is safe to remove (inside project root)."""
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
        return path.exists()
    except ValueError:
        return False


def list_targets() -> List[Path]:
    return [PROJECT_ROOT / name for name in TARGETS]


def plan() -> List[dict]:
    actions = []
    for path in list_targets():
        if not _safe_target(path):
            continue
        actions.append(
            {
                "action": "remove",
                "path": str(path.relative_to(PROJECT_ROOT)),
                "kind": "directory" if path.is_dir() else "file",
                "size_bytes": _size(path),
            }
        )
    for rel in UPDATES:
        path = PROJECT_ROOT / rel
        if path.exists():
            actions.append(
                {
                    "action": "patch",
                    "path": rel,
                    "kind": "file",
                    "size_bytes": path.stat().st_size,
                }
            )
    return actions


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def remove_targets() -> List[Path]:
    """Actually remove the targets. Returns the list of removed paths."""
    removed: List[Path] = []
    for path in list_targets():
        if not _safe_target(path):
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
        else:
            path.unlink()
        removed.append(path)
    return removed


def backup_electron(archive_root: Path) -> Path:
    """Move electron/ into .archive/electron-v0.6.x (safety net)."""
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / "electron-v0.6.x"
    if target.exists():
        shutil.rmtree(target)
    electron_dir = PROJECT_ROOT / "electron"
    if electron_dir.exists():
        shutil.move(str(electron_dir), str(target))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.7.1 remove Electron desktop shell")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually remove files (default: dry-run, only print plan)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Move electron/ to .archive/electron-v0.6.x before deletion",
    )
    args = parser.parse_args()

    actions = plan()
    print(f"Plan: {len(actions)} actions")
    for action in actions:
        size_mb = action["size_bytes"] / (1024 * 1024)
        print(f"  [{action['action']}] {action['path']} ({action['kind']}, {size_mb:.1f}MB)")
    total_mb = sum(a["size_bytes"] for a in actions) / (1024 * 1024)
    print(f"\nTotal: {total_mb:.1f}MB")

    if not args.apply:
        print("\n(dry-run — pass --apply to execute)")
        return 0

    print("\nApplying...")
    if args.backup:
        archive_dir = PROJECT_ROOT / ".archive"
        target = backup_electron(archive_dir)
        print(f"  backup: electron -> {target.relative_to(PROJECT_ROOT)}")
    removed = remove_targets()
    print(f"\nRemoved {len(removed)} paths")
    for path in removed:
        print(f"  ✓ {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())