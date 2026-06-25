"""
scripts/package_release.py — 一键打包离线发布包

将项目代码与预置的离线依赖（vendor/、models/）打包成 zip，
可直接分发给未安装 Python/Node/Git 的 Windows 用户。

用法：
    python scripts/package_release.py
    python scripts/package_release.py --output TTMEvolve-offline.zip
"""

from __future__ import annotations
import argparse
import json
import os
import zipfile
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# 默认排除的目录/文件
DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "storage",
    "test_project",
    "__pycache__",
    ".tmp",
    "dist",
    "build",
    "vendor/_cache",
}

DEFAULT_EXCLUDE_PATTERNS = {
    "*.pyc",
    "*.log",
    ".env",
    ".env.local",
    "config.json",
}


def _load_version() -> str:
    """尝试从 core/version_manager.py 或 package.json 读取版本。"""
    try:
        version_file = _PROJECT_ROOT / "core" / "version_manager.py"
        if version_file.exists():
            text = version_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "VERSION" in line and "=" in line:
                    return line.split("=")[-1].strip().strip('"\'')
    except Exception:
        pass
    try:
        pkg = json.loads((_PROJECT_ROOT / "electron" / "package.json").read_text(encoding="utf-8"))
        return pkg.get("version", "0.4.0")
    except Exception:
        return "0.4.0"


def _should_include(rel_path: str, is_dir: bool) -> bool:
    """判断相对路径是否应该被打包。"""
    parts = Path(rel_path).parts
    # 排除特定目录
    for part in parts:
        if part in DEFAULT_EXCLUDES:
            return False
    # 排除匹配文件
    if not is_dir:
        for pattern in DEFAULT_EXCLUDE_PATTERNS:
            if Path(rel_path).match(pattern):
                return False
    return True


def package_release(output: Optional[Path] = None) -> Path:
    version = _load_version()
    if output is None:
        output = _PROJECT_ROOT / f"TTMEvolve-offline-v{version}.zip"

    print(f"[package] Building release: {output}")
    print(f"[package] Project root: {_PROJECT_ROOT}")

    included = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(_PROJECT_ROOT):
            root_path = Path(root)
            rel_root = root_path.relative_to(_PROJECT_ROOT)

            # 过滤目录
            dirs[:] = [
                d for d in dirs
                if _should_include(str(rel_root / d), True)
            ]

            for file in files:
                file_path = root_path / file
                rel_path = file_path.relative_to(_PROJECT_ROOT)
                if not _should_include(str(rel_path), False):
                    continue
                arcname = str(rel_path).replace("\\", "/")
                zf.write(file_path, arcname)
                included += 1
                if included % 1000 == 0:
                    print(f"[package] ... {included} files added")

    size_mb = output.stat().st_size / 1024 / 1024
    print(f"[package] Done: {included} files, {size_mb:.1f} MB -> {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Package TTMEvolve offline release")
    parser.add_argument("--output", type=Path, help="output zip path")
    args = parser.parse_args()

    package_release(args.output)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
