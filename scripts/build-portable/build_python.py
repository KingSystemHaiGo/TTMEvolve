"""build_python.py — 下载并解压 Python 嵌入式运行时到 portable/python/"""

from __future__ import annotations

import json
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
PORTABLE_DIR = PROJECT_ROOT / "portable" / "python"
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
        print(f"[build_python] cached {dest.name}")
        return
    print(f"[build_python] downloading {url}")
    urllib.request.urlretrieve(url, str(dest))


def _extract_windows(zip_path: Path, target: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)


def _extract_posix(tar_path: Path, target: Path) -> None:
    suffix = "".join(tar_path.suffixes)
    if suffix.endswith(".tar.xz") or tar_path.name.endswith(".tar.xz"):
        mode = "r:xz"
    elif suffix.endswith(".tar.gz") or tar_path.name.endswith(".tar.gz"):
        mode = "r:gz"
    else:
        raise RuntimeError(f"Unknown archive: {tar_path}")
    with tarfile.open(tar_path, mode) as tf:
        tf.extractall(target)


def _enable_site(target: Path) -> None:
    """Uncomment 'import site' in pythonXY._pth so site-packages work."""
    pth_files = list(target.glob("python*._pth"))
    if not pth_files:
        print("[build_python] no ._pth file found (POSIX layout)")
        return
    for pth in pth_files:
        content = pth.read_text(encoding="utf-8")
        if "import site" in content:
            content = content.replace("#import site", "import site")
            pth.write_text(content, encoding="utf-8")
            print(f"[build_python] enabled 'import site' in {pth.name}")


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    key = _platform_key()
    entry = config["python"][key]

    target = PORTABLE_DIR
    if target.exists():
        print(f"[build_python] {target} already exists, skipping (delete to rebuild)")
        return 0

    archive = DOWNLOADS_DIR / entry["filename"]
    _download(entry["url"], archive)

    print(f"[build_python] extracting to {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if key == "windows":
        _extract_windows(archive, target)
        _enable_site(target)
    else:
        _extract_posix(archive, target)

    print("[build_python] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())