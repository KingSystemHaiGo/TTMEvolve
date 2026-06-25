"""build_node.py — 下载并解压 Node.js 嵌入式运行时到 portable/node/"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
PORTABLE_DIR = PROJECT_ROOT / "portable" / "node"
DOWNLOADS_DIR = PROJECT_ROOT / "portable" / "downloads"


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def _download(url: str, dest: Path) -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[build_node] cached {dest.name}")
        return
    print(f"[build_node] downloading {url}")
    urllib.request.urlretrieve(url, str(dest))


def _extract_windows(zip_path: Path, target: Path) -> None:
    # Node zip on Windows contains a top-level folder (e.g. node-v20.18.0-win-x64/);
    # strip it so the result lands directly under portable/node/.
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        prefix = ""
        for name in members:
            if name.endswith("/") and name.count("/") == 1:
                prefix = name
                break
        if prefix:
            for member in members:
                if member == prefix:
                    continue
                relative = member[len(prefix):]
                if not relative:
                    continue
                target_path = target / relative
                if member.endswith("/"):
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        else:
            zf.extractall(target)


def _extract_posix(tar_path: Path, target: Path) -> None:
    if tar_path.name.endswith(".tar.xz"):
        mode = "r:xz"
    elif tar_path.name.endswith(".tar.gz"):
        mode = "r:gz"
    else:
        raise RuntimeError(f"Unknown archive: {tar_path}")
    with tarfile.open(tar_path, mode) as tf:
        members = tf.getmembers()
        prefix = ""
        for member in members:
            if member.isdir() and member.name.count("/") == 1:
                prefix = member.name
                break
        for member in members:
            if member.name == prefix:
                continue
            relative = member.name[len(prefix):].lstrip("/")
            if not relative:
                continue
            target_path = target / relative
            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(member) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    key = _platform_key()
    entry = config["node"][key]

    target = PORTABLE_DIR
    if target.exists() and any(target.iterdir()):
        print(f"[build_node] {target} already populated, skipping")
        return 0

    archive = DOWNLOADS_DIR / entry["filename"]
    _download(entry["url"], archive)

    print(f"[build_node] extracting to {target}")
    target.mkdir(parents=True, exist_ok=True)
    if key == "windows":
        _extract_windows(archive, target)
    else:
        _extract_posix(archive, target)

    print("[build_node] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())