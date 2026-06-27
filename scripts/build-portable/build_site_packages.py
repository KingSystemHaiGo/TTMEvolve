"""build_site_packages.py — 用 portable Python 安装精简 site-packages

v0.7.0 转向云端 LLM 后，不再安装 llama-cpp-python / torch / sentence-transformers 等
本地模型依赖。精简后的依赖列表见 build-portable/config.json。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
DOWNLOADS_DIR = PROJECT_ROOT / "portable" / "downloads"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def _python_exe() -> Path:
    if sys.platform.startswith("win"):
        return PROJECT_ROOT / "portable" / "python" / "python.exe"
    return PROJECT_ROOT / "portable" / "python" / "bin" / "python3"


def _site_target() -> Path:
    if sys.platform.startswith("win"):
        return PROJECT_ROOT / "portable" / "python" / "Lib" / "site-packages"
    # POSIX python-build-standalone uses lib/python3.X/site-packages
    py_dir = next((PROJECT_ROOT / "portable" / "python" / "lib").glob("python*"), None)
    if py_dir is None:
        raise RuntimeError("POSIX python lib dir not found")
    return py_dir / "site-packages"


def _download_get_pip() -> Path:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOWNLOADS_DIR / "get-pip.py"
    if target.exists():
        print(f"[build_site_packages] cached {target.name}")
        return target
    print(f"[build_site_packages] downloading {GET_PIP_URL}")
    urllib.request.urlretrieve(GET_PIP_URL, str(target))
    return target


def _ensure_pip(py: Path) -> int:
    probe = subprocess.run(
        [str(py), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        print(f"[build_site_packages] pip OK ({probe.stdout.strip()})")
        return 0

    get_pip = _download_get_pip()
    print("[build_site_packages] bootstrapping pip")
    result = subprocess.run(
        [str(py), str(get_pip), "--no-warn-script-location"],
        check=False,
    )
    if result.returncode != 0:
        print(f"[build_site_packages] pip bootstrap failed: {result.returncode}")
    return result.returncode


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    py = _python_exe()
    if not py.exists():
        print(f"[build_site_packages] portable Python missing: {py}")
        print("[build_site_packages] run build_python.py first")
        return 1

    pip_result = _ensure_pip(py)
    if pip_result != 0:
        return pip_result

    target = _site_target()
    target.mkdir(parents=True, exist_ok=True)

    requirements = config["site_packages"]["requirements"]
    print(f"[build_site_packages] installing {len(requirements)} required packages to {target}")
    cmd = [
        str(py),
        "-m",
        "pip",
        "install",
        "--target",
        str(target),
        "--upgrade",
        "--no-cache-dir",
        "--disable-pip-version-check",
        *requirements,
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"[build_site_packages] pip install failed: {result.returncode}")
        return result.returncode

    optional = config["site_packages"]["optional"]
    if optional:
        print(f"[build_site_packages] installing {len(optional)} optional packages")
        subprocess.run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "--target",
                str(target),
                "--upgrade",
                "--no-cache-dir",
                "--disable-pip-version-check",
                *optional,
            ],
            check=False,
        )

    # Smoke test: import the key packages.
    print("[build_site_packages] running import smoke test")
    smoke_env = os.environ.copy()
    smoke_env["PYTHONPATH"] = str(target)
    smoke = subprocess.run(
        [str(py), "-c", "import fastapi, uvicorn, pydantic, httpx, requests; print('ok')"],
        env=smoke_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if smoke.returncode != 0:
        print(f"[build_site_packages] smoke test failed: {smoke.stderr}")
        return smoke.returncode

    print("[build_site_packages] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
