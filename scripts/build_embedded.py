"""
scripts/build_embedded.py — 构建 TTMEvolve 离线/内嵌运行环境

把 Python 依赖、本地模型、embedding 模型、Playwright Chromium（可选内嵌 Python/Node/Git）
全部收集到项目目录，实现断网即开即用。

用法：
    python scripts/build_embedded.py --mode deps-only    # 只下载依赖包（推荐日常）
    python scripts/build_embedded.py --mode full         # 完整内嵌运行时（Windows x64）

仅支持 Windows x64（首发）。跨平台扩展见 Phase 11。
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config

# 内嵌运行时下载链接（Windows x64 便携版）
RUNTIME_URLS = {
    "python": {
        "url": "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
        "filename": "python-3.12.10-embed-amd64.zip",
        "sha256": None,
    },
    "node": {
        "url": "https://nodejs.org/dist/v20.15.1/node-v20.15.1-win-x64.zip",
        "filename": "node-v20.15.1-win-x64.zip",
        "sha256": None,
    },
    "git": {
        "url": "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/MinGit-2.45.2-64-bit.zip",
        "filename": "MinGit-2.45.2-64-bit.zip",
        "sha256": None,
    },
}

# 默认资源
DEFAULT_MODEL_FILE = "MiniCPM5-1B-Q4_K_M.gguf"
DEFAULT_MODEL_REPO = "OpenBMB/MiniCPM5-1B-GGUF"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_URL = f"https://modelscope.cn/models/{DEFAULT_MODEL_REPO}/resolve/master/{DEFAULT_MODEL_FILE}"

# 国内镜像
PYPI_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
PYPI_TRUSTED = "pypi.tuna.tsinghua.edu.cn"


def _info(msg: str) -> None:
    print(f"[build_embedded] {msg}")


def _error(msg: str) -> None:
    print(f"[build_embedded] ERROR: {msg}", file=sys.stderr)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, expected_sha256: Optional[str] = None) -> None:
    """下载文件到 dest，可选校验 sha256。"""
    if dest.exists():
        _info(f"found cached {dest.name}")
        if expected_sha256 and _sha256(dest) != expected_sha256:
            _info("cached file checksum mismatch, re-downloading")
            dest.unlink()
        else:
            return
    _info(f"downloading {url} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest))
    if expected_sha256 and _sha256(dest) != expected_sha256:
        raise RuntimeError(f"checksum mismatch for {dest}")


def _download_with_progress(url: str, dest: Path, headers: Optional[dict] = None, timeout: int = 300) -> None:
    """带进度条下载，支持断点续传。timeout 为单连接超时秒数。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req_headers = dict(headers or {})
    start_offset = 0
    if dest.exists():
        start_offset = dest.stat().st_size
        req_headers["Range"] = f"bytes={start_offset}-"

    req = urllib.request.Request(url, headers=req_headers)
    mode = "ab" if start_offset else "wb"
    with urllib.request.urlopen(req, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length", 0)) + start_offset
        chunk_size = 1024 * 1024  # 1MB
        downloaded = start_offset
        start_time = __import__("time").time()
        with open(dest, mode) as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    percent = downloaded / total * 100
                    mb = downloaded / 1024 / 1024
                    total_mb = total / 1024 / 1024
                    print(f"\r[build_embedded] {percent:.1f}% ({mb:.1f}/{total_mb:.1f} MB)", end="", flush=True)
        elapsed = __import__("time").time() - start_time
        print(f"\n[build_embedded] saved {dest.name} in {elapsed:.1f}s")


def _extract_zip(zip_path: Path, dest: Path) -> None:
    """解压 zip 到 dest，若 dest 已存在且非空则跳过。"""
    if dest.exists() and any(dest.iterdir()):
        _info(f"already extracted: {dest}")
        return
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest)
    _info(f"extracted {zip_path.name} -> {dest}")


# ------------------------------------------------------------------
# 运行时
# ------------------------------------------------------------------
def _ensure_python(vendor_dir: Path) -> Path:
    python_dir = vendor_dir / "python"
    python_exe = python_dir / "python.exe"
    if python_exe.exists():
        return python_exe
    meta = RUNTIME_URLS["python"]
    cache = vendor_dir / "_cache" / meta["filename"]
    _download(meta["url"], cache, meta["sha256"])
    _extract_zip(cache, python_dir)
    # embeddable Python 需要解除 import 限制
    pth = python_dir / "python312._pth"
    if pth.exists():
        text = pth.read_text(encoding="utf-8")
        text = text.replace("#import site", "import site")
        pth.write_text(text, encoding="utf-8")
    return python_exe


def _ensure_node(vendor_dir: Path) -> Path:
    node_dir = vendor_dir / "node"
    node_exe = node_dir / "node.exe"
    if node_exe.exists():
        return node_exe
    meta = RUNTIME_URLS["node"]
    cache = vendor_dir / "_cache" / meta["filename"]
    _download(meta["url"], cache, meta["sha256"])
    temp_extract = vendor_dir / "_cache" / "node_extract"
    _extract_zip(cache, temp_extract)
    extracted = next(temp_extract.iterdir())
    if extracted.is_dir():
        shutil.move(str(extracted), str(node_dir))
    return node_dir / "node.exe"


def _ensure_git(vendor_dir: Path) -> Path:
    git_dir = vendor_dir / "git"
    git_exe = git_dir / "cmd" / "git.exe"
    if git_exe.exists():
        return git_exe
    meta = RUNTIME_URLS["git"]
    cache = vendor_dir / "_cache" / meta["filename"]
    _download(meta["url"], cache, meta["sha256"])
    _extract_zip(cache, git_dir)
    return git_exe


# ------------------------------------------------------------------
# 依赖包
# ------------------------------------------------------------------
def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _python_abi() -> str:
    major = sys.version_info.major
    minor = sys.version_info.minor
    return f"cp{major}{minor}"


def _platform_tag() -> str:
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    if sysname == "windows":
        return "win_amd64"
    if sysname == "darwin":
        return "macosx_10_9_x86_64" if machine == "x86_64" else "macosx_11_0_arm64"
    if sysname == "linux":
        return "manylinux2014_x86_64" if machine == "x86_64" else "manylinux2014_aarch64"
    return "any"


def _installed_llama_cpp_version() -> Optional[str]:
    """返回当前环境中 llama-cpp-python 的版本，若未安装则返回 None。"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "llama-cpp-python"],
            capture_output=True, text=True, check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _download_llama_cpp_wheel(version: str, wheels_dir: Path) -> bool:
    """下载 llama-cpp-python 预编译 wheel，优先官方 CPU 索引，其次 GitHub releases。"""
    # 方案 1: 使用官方 CPU extra index
    _info(f"downloading llama-cpp-python=={version} from official CPU index...")
    try:
        subprocess.check_call(
            [
                sys.executable, "-m", "pip", "download",
                f"llama-cpp-python=={version}",
                "-d", str(wheels_dir),
                "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cpu",
                "--only-binary=:all:",
            ],
            cwd=str(_PROJECT_ROOT),
        )
        return True
    except subprocess.CalledProcessError as e:
        _error(f"official CPU index failed: {e}")

    # 方案 2: 直接下载官方 py3-none wheel
    candidates = [
        (
            f"llama_cpp_python-{version}-py3-none-win_amd64.whl",
            f"https://github.com/abetlen/llama-cpp-python/releases/download/v{version}/llama_cpp_python-{version}-py3-none-win_amd64.whl",
        ),
        (
            f"llama_cpp_python-{version}-cp{_python_abi().replace('cp', '')}-cp{_python_abi().replace('cp', '')}-win_amd64.whl",
            f"https://github.com/JamePeng/llama-cpp-python/releases/download/v{version}/llama_cpp_python-{version}-cp{_python_abi().replace('cp', '')}-cp{_python_abi().replace('cp', '')}-win_amd64.whl",
        ),
    ]

    for filename, url in candidates:
        dest = wheels_dir / filename
        if dest.exists():
            _info(f"llama-cpp-python wheel already cached: {dest}")
            return True
        _info(f"downloading prebuilt llama-cpp-python wheel: {url}")
        try:
            urllib.request.urlretrieve(url, str(dest))
            _info(f"saved {dest}")
            return True
        except Exception as e:
            _error(f"failed to download {filename}: {e}")
            if dest.exists():
                dest.unlink()

    return False


def _ensure_wheels(vendor_dir: Path, python_exe: Path) -> Path:
    """下载 requirements.txt 中所有依赖的 wheel 到 vendor/wheels/。"""
    wheels_dir = vendor_dir / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)
    req_file = _PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        _error(f"{req_file} not found")
        return wheels_dir

    marker = wheels_dir / ".ready"
    if marker.exists():
        _info("wheels already prepared")
        return wheels_dir

    py_ver = _python_version()
    abi = _python_abi()
    plat = _platform_tag()
    _info(f"downloading wheels from {PYPI_INDEX}")
    _info(f"target: Python {py_ver}, {abi}, {plat}")

    cmd = [
        str(python_exe), "-m", "pip", "download",
        "-r", str(req_file),
        "-d", str(wheels_dir),
        "--index-url", PYPI_INDEX,
        "--trusted-host", PYPI_TRUSTED,
        "--only-binary=:all:",
        f"--python-version={py_ver}",
        f"--abi={abi}",
        f"--platform={plat}",
        "--no-deps",
    ]
    try:
        subprocess.check_call(cmd, cwd=str(_PROJECT_ROOT))
    except subprocess.CalledProcessError as e:
        _error(f"binary wheel download failed: {e}")
        # 兜底：单独处理 llama-cpp-python
        version = _installed_llama_cpp_version() or "0.3.30"
        if not _download_llama_cpp_wheel(version, wheels_dir):
            raise RuntimeError("failed to download llama-cpp-python wheel")

        # 其余包再次尝试（排除 llama-cpp-python）
        _info("retrying remaining packages without llama-cpp-python...")
        filtered_req = wheels_dir / ".requirements.filtered.txt"
        lines = req_file.read_text(encoding="utf-8").splitlines()
        filtered = [ln for ln in lines if "llama-cpp-python" not in ln]
        if not filtered:
            _info("only llama-cpp-python was required")
        else:
            filtered_req.write_text("\n".join(filtered) + "\n", encoding="utf-8")
            cmd[5] = str(filtered_req)
            subprocess.check_call(cmd, cwd=str(_PROJECT_ROOT))

    marker.write_text("ready", encoding="utf-8")
    count = len(list(wheels_dir.glob("*.whl")))
    _info(f"downloaded {count} wheels to {wheels_dir}")
    return wheels_dir


# ------------------------------------------------------------------
# 模型
# ------------------------------------------------------------------
def _ensure_model() -> Path:
    """确保 GGUF 模型存在于 models/ 目录。"""
    models_dir = _PROJECT_ROOT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / DEFAULT_MODEL_FILE
    if model_path.exists():
        _info(f"model already exists: {model_path}")
        return model_path

    # 优先从已有位置复制
    source_candidates = [
        _PROJECT_ROOT / "vendor" / "models" / DEFAULT_MODEL_FILE,
    ]
    for source in source_candidates:
        if source.exists():
            _info(f"copying model from {source}")
            shutil.copy2(source, model_path)
            return model_path

    _info(f"downloading {DEFAULT_MODEL_FILE} from ModelScope ...")
    try:
        _download_with_progress(MODEL_URL, model_path, headers={"User-Agent": "TTMEvolve-build/1.0"})
        return model_path
    except Exception as e:
        _error(f"failed to download model: {e}")
        if model_path.exists():
            model_path.unlink()
        raise


# ------------------------------------------------------------------
# Embedding 模型
# ------------------------------------------------------------------
def _ensure_embeddings(vendor_dir: Path) -> Path:
    emb_dir = vendor_dir / "embeddings"
    emb_dir.mkdir(parents=True, exist_ok=True)
    local_name = Path(DEFAULT_EMBEDDING_MODEL).name
    local_path = emb_dir / local_name
    marker = local_path / ".ready"
    if local_path.exists() and any(local_path.iterdir()) and marker.exists():
        _info(f"embedding model already exists: {local_path}")
        return local_path

    _info(f"downloading embedding model {DEFAULT_EMBEDDING_MODEL} ...")

    # 方案 1: 使用 HF-Mirror 加速 HuggingFace
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            DEFAULT_EMBEDDING_MODEL,
            local_dir=str(local_path),
            local_dir_use_symlinks=False,
        )
        marker.write_text("ready", encoding="utf-8")
        _info(f"embedding model saved to {local_path}")
        return local_path
    except Exception as e:
        _error(f"hf-mirror download failed: {e}")

    # 方案 2: 使用 ModelScope
    _info("trying ModelScope mirror...")
    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
        ms_snapshot_download(
            DEFAULT_EMBEDDING_MODEL,
            local_dir=str(local_path),
        )
        marker.write_text("ready", encoding="utf-8")
        _info(f"embedding model saved to {local_path}")
        return local_path
    except Exception as e:
        _error(f"modelscope download failed: {e}")
        raise


# ------------------------------------------------------------------
# Playwright Chromium
# ------------------------------------------------------------------
def _ensure_playwright_browsers(vendor_dir: Path, python_exe: Path) -> Path:
    browser_dir = vendor_dir / "playwright"
    marker = browser_dir / ".ready"
    if marker.exists():
        _info("playwright browsers already prepared")
        return browser_dir

    _info("installing Playwright Chromium browser...")

    # 尝试读取 playwright 的 browsers.json 获取精确版本
    browsers_json = (
        Path(python_exe).parent.parent
        / "Lib"
        / "site-packages"
        / "playwright"
        / "driver"
        / "package"
        / "browsers.json"
    )
    browser_version = "148.0.7778.96"
    revision = "1223"
    if browsers_json.exists():
        try:
            data = json.loads(browsers_json.read_text(encoding="utf-8"))
            for b in data.get("browsers", []):
                if b.get("name") == "chromium":
                    browser_version = b.get("browserVersion", browser_version)
                    revision = b.get("revision", revision)
                    break
        except Exception:
            pass

    chrome_dir = browser_dir / f"chromium-{revision}" / "chrome-win64"
    chrome_exe = chrome_dir / "chrome.exe"
    headless_dir = browser_dir / f"chromium_headless_shell-{revision}" / "chrome-headless-shell-win64"
    headless_exe = headless_dir / "chrome-headless-shell.exe"

    if not chrome_exe.exists() or not headless_exe.exists():
        archives = [
            (f"chrome-win64-{revision}.zip", f"chromium-{revision}", chrome_exe),
            (f"chrome-headless-shell-win64-{revision}.zip", f"chromium_headless_shell-{revision}", headless_exe),
        ]
        for filename, extract_parent, exe_path in archives:
            if exe_path.exists():
                continue
            zip_dest = browser_dir / filename
            urls = [
                f"https://cdn.playwright.dev/builds/cft/{browser_version}/win64/{filename.replace(f'-{revision}', '')}",
                f"https://playwright.azureedge.net/builds/cft/{browser_version}/win64/{filename.replace(f'-{revision}', '')}",
                f"https://npmmirror.com/mirrors/playwright/builds/cft/{browser_version}/win64/{filename.replace(f'-{revision}', '')}",
                f"https://registry.npmmirror.com/-/binary/playwright/builds/cft/{browser_version}/win64/{filename.replace(f'-{revision}', '')}",
            ]
            downloaded = False
            last_err = None
            for url in urls:
                _info(f"trying {filename} mirror: {url}")
                try:
                    _download_with_progress(url, zip_dest, timeout=300)
                    downloaded = True
                    break
                except Exception as e:
                    last_err = e
                    _error(f"failed: {e}")
                    if zip_dest.exists():
                        zip_dest.unlink()

            if not downloaded:
                _error(f"all mirrors failed for {filename}: {last_err}")
                # fallback: 调用 playwright 命令安装
                env = os.environ.copy()
                env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
                env.setdefault("PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT", "300000")
                subprocess.run(
                    [str(python_exe), "-m", "playwright", "install", "chromium"],
                    env=env,
                    check=True,
                )
                break
            else:
                _extract_zip(zip_dest, browser_dir / extract_parent)
                zip_dest.unlink(missing_ok=True)

    marker.write_text("ready", encoding="utf-8")
    _info(f"playwright chromium saved to {browser_dir}")
    return browser_dir


# ------------------------------------------------------------------
# 配置与清单
# ------------------------------------------------------------------
def _write_embedded_config(model_path: Path) -> None:
    example_path = _PROJECT_ROOT / "config.example.json"
    if example_path.exists():
        example = json.loads(example_path.read_text(encoding="utf-8"))
    else:
        example = {}

    example.setdefault("llm", {})
    example["llm"]["provider"] = "local"
    example["llm"]["model_path"] = f"./models/{model_path.name}"
    example.setdefault("memory", {})
    example["memory"].setdefault("vector_index", {})
    example["memory"]["vector_index"]["model"] = DEFAULT_EMBEDDING_MODEL

    out = _PROJECT_ROOT / "config.embedded.json"
    out.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
    _info(f"wrote {out}")


def _write_env_file() -> None:
    """生成 .env.embedded，记录离线资源路径。"""
    lines = [
        "# Auto-generated by scripts/build_embedded.py",
        f"SENTENCE_TRANSFORMERS_HOME={_PROJECT_ROOT / 'vendor' / 'embeddings'}",
        f"PLAYWRIGHT_BROWSERS_PATH={_PROJECT_ROOT / 'vendor' / 'playwright'}",
    ]
    python_exe = _PROJECT_ROOT / "vendor" / "python" / "python.exe"
    node_exe = _PROJECT_ROOT / "vendor" / "node" / "node.exe"
    git_exe = _PROJECT_ROOT / "vendor" / "git" / "cmd" / "git.exe"
    if python_exe.exists():
        lines.append(f"TTM_PYTHON_EXE={python_exe}")
    if node_exe.exists():
        lines.append(f"TTM_NODE_EXE={node_exe}")
    if git_exe.exists():
        lines.append(f"TTM_GIT_EXE={git_exe}")

    (_PROJECT_ROOT / ".env.embedded").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _info("wrote .env.embedded")


def _write_manifest(vendor_dir: Path, model_path: Path) -> None:
    """生成 vendor/manifest.json，记录离线包内容，用于校验。"""
    entries = []
    manifest_time = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")

    def add_dir(rel_root: Path, rel_prefix: str = "") -> None:
        if not rel_root.exists():
            return
        for path in rel_root.rglob("*"):
            if path.is_file() and path.name != ".ready":
                rel = path.relative_to(vendor_dir)
                entries.append({
                    "path": str(rel).replace("\\", "/"),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path) if path.stat().st_size < 50 * 1024 * 1024 else None,
                })

    add_dir(vendor_dir / "wheels")
    add_dir(vendor_dir / "embeddings")
    add_dir(vendor_dir / "playwright")
    if (vendor_dir / "python" / "python.exe").exists():
        add_dir(vendor_dir / "python")
    if (vendor_dir / "node" / "node.exe").exists():
        add_dir(vendor_dir / "node")
    if (vendor_dir / "git" / "cmd" / "git.exe").exists():
        add_dir(vendor_dir / "git")

    manifest = {
        "version": "1.0.0",
        "generated_at": manifest_time,
        "platform": _platform_tag(),
        "python_version": _python_version(),
        "mode": "full" if (vendor_dir / "python" / "python.exe").exists() else "deps-only",
        "entries": entries,
        "models": [
            {
                "path": f"models/{model_path.name}",
                "size": model_path.stat().st_size,
                "sha256": None,
            }
        ],
    }
    manifest_path = vendor_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _info(f"wrote {manifest_path}")


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Build offline/embedded runtime for TTMEvolve")
    parser.add_argument(
        "--mode",
        choices=["full", "deps-only"],
        default="deps-only",
        help="full=download Python/Node/Git runtimes + deps; deps-only=download deps only",
    )
    parser.add_argument("--skip-python", action="store_true", help="skip downloading embedded Python (full mode only)")
    parser.add_argument("--skip-node", action="store_true", help="skip downloading Node (full mode only)")
    parser.add_argument("--skip-git", action="store_true", help="skip downloading Git (full mode only)")
    parser.add_argument("--skip-wheels", action="store_true", help="skip downloading wheels")
    parser.add_argument("--skip-model", action="store_true", help="skip copying/downloading model")
    parser.add_argument("--skip-embeddings", action="store_true", help="skip downloading embedding model")
    parser.add_argument("--skip-playwright", action="store_true", help="skip installing Playwright Chromium")
    args = parser.parse_args()

    if args.mode == "full" and platform.system() != "Windows":
        _error("embedded build currently only supports Windows x64")
        return 1

    vendor_dir = _PROJECT_ROOT / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    # 决定使用哪个 Python
    python_exe = Path(sys.executable)
    if args.mode == "full":
        if not args.skip_python:
            python_exe = _ensure_python(vendor_dir)
        else:
            embedded = vendor_dir / "python" / "python.exe"
            if embedded.exists():
                python_exe = embedded

        if not args.skip_node:
            _ensure_node(vendor_dir)
        if not args.skip_git:
            _ensure_git(vendor_dir)

    if not args.skip_wheels:
        _ensure_wheels(vendor_dir, python_exe)

    model_path = _PROJECT_ROOT / "models" / DEFAULT_MODEL_FILE
    if not args.skip_model:
        model_path = _ensure_model()

    if not args.skip_embeddings:
        _ensure_embeddings(vendor_dir)

    if not args.skip_playwright:
        try:
            _ensure_playwright_browsers(vendor_dir, python_exe)
        except Exception as e:
            _error(f"Playwright browser install failed: {e}")

    _write_embedded_config(model_path)
    _write_env_file()
    _write_manifest(vendor_dir, model_path)

    _info("build complete")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
