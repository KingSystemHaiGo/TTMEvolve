"""
scripts/bootstrap.py — 自动安装依赖并确认模型就绪

入口统一为 start.bat。策略：
1. 如果 vendor/wheels/ 和 models/ 已预置，直接本地安装/加载（即开即用）。
2. 如果没有预置且网络可用，自动调用 prepare_offline_env.py 下载。
3. 如果都不满足，fallback 到 Mock 模式。

PyPI 默认使用清华 tuna 镜像；模型默认使用 ModelScope 镜像。
"""

from __future__ import annotations
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from core.portable_env import apply_portable_env


apply_portable_env(_PROJECT_ROOT)


VENDOR_WHEELS_DIR = _PROJECT_ROOT / "vendor" / "wheels"
MODELS_DIR = _PROJECT_ROOT / "models"
DEFAULT_MODEL = "MiniCPM5-1B-Q4_K_M.gguf"

PYPI_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
PYPI_TRUSTED = "pypi.tuna.tsinghua.edu.cn"


def _python() -> str:
    return sys.executable


def _subprocess_env() -> dict[str, str]:
    apply_portable_env(_PROJECT_ROOT)
    return os.environ.copy()


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _is_online(timeout: float = 5.0) -> bool:
    try:
        urllib.request.urlopen(PYPI_INDEX, timeout=timeout)
        return True
    except Exception:
        return False


def _vendor_exists() -> bool:
    return VENDOR_WHEELS_DIR.exists() and any(VENDOR_WHEELS_DIR.glob("*.whl"))


def _model_exists() -> bool:
    return (MODELS_DIR / DEFAULT_MODEL).exists()


def _embeddings_exists() -> bool:
    """检测 vendor/embeddings 中是否已有离线 embedding 模型。"""
    emb_dir = VENDOR_WHEELS_DIR.parent / "embeddings"
    if not emb_dir.exists():
        return False
    # 默认模型目录
    candidate = emb_dir / "paraphrase-multilingual-MiniLM-L12-v2"
    return candidate.exists() and any(candidate.iterdir())


def _playwright_exists() -> bool:
    """检测 vendor/playwright 中是否已有离线 Chromium。"""
    browser_dir = VENDOR_WHEELS_DIR.parent / "playwright"
    return (browser_dir / ".ready").exists()


def _embedded_python_exists() -> bool:
    return (_PROJECT_ROOT / "vendor" / "python" / "python.exe").exists()


def _embedded_node_exists() -> bool:
    return (_PROJECT_ROOT / "vendor" / "node" / "node.exe").exists()


def _embedded_git_exists() -> bool:
    return (_PROJECT_ROOT / "vendor" / "git" / "cmd" / "git.exe").exists()


def _install_from_wheels() -> bool:
    if not _vendor_exists():
        return False
    print("[bootstrap] Installing from vendor/wheels...")
    wheels = list(VENDOR_WHEELS_DIR.glob("*.whl"))
    try:
        subprocess.check_call(
            [_python(), "-m", "pip", "install", "--no-index", "--find-links", str(VENDOR_WHEELS_DIR)] + [str(w) for w in wheels],
            cwd=str(_PROJECT_ROOT),
            env=_subprocess_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        return _ensure_chromium()
    except subprocess.CalledProcessError as e:
        print(f"[bootstrap] Local wheel install failed: {e}")
        return False


def _ensure_chromium() -> bool:
    """确保 Playwright Chromium 可用。优先使用 vendor/playwright 离线包。"""
    if not _has("playwright"):
        return True

    # 优先使用离线浏览器包
    vendor_browser = _PROJECT_ROOT / "vendor" / "playwright"
    env = os.environ.copy()
    if vendor_browser.exists():
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(vendor_browser)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(vendor_browser)

    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        executable = pw.chromium.executable_path
        pw.stop()
        if executable and Path(executable).exists():
            print(f"[bootstrap] Chromium binary ready: {executable}")
            return True
    except Exception:
        pass

    # 离线模式下不再尝试在线下载
    offline = os.getenv("TTM_EVOLVE_OFFLINE", "").lower() in ("1", "true", "yes")
    if offline:
        print("[bootstrap] Offline mode: Chromium binary not available locally")
        print("[bootstrap] Browser preview will be unavailable")
        return True

    print("[bootstrap] Installing Playwright Chromium binary...")
    try:
        subprocess.check_call(
            [_python(), "-m", "playwright", "install", "chromium"],
            cwd=str(_PROJECT_ROOT),
            env={**_subprocess_env(), **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        print("[bootstrap] Chromium binary ready")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[bootstrap] Failed to install Chromium binary: {e}")
        print("[bootstrap] Browser preview will be unavailable; run 'python -m playwright install chromium' manually")
        return True


def _install_from_pypi(packages: list[str]) -> bool:
    if not packages:
        return True
    print(f"[bootstrap] Installing from PyPI mirror: {', '.join(packages)}")
    try:
        subprocess.check_call(
            [_python(), "-m", "pip", "install", "--upgrade", "--prefer-binary",
             "--index-url", PYPI_INDEX, "--trusted-host", PYPI_TRUSTED, *packages],
            cwd=str(_PROJECT_ROOT),
            env=_subprocess_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[bootstrap] PyPI install failed: {e}")
        return False


def _prepare_offline_env() -> bool:
    """调用 prepare_offline_env.py 下载 wheel 和模型。"""
    script = _PROJECT_ROOT / "scripts" / "prepare_offline_env.py"
    print("[bootstrap] Vendor not found, preparing offline environment...")
    print("[bootstrap] This will download wheels and model, please wait.")
    try:
        subprocess.check_call([_python(), str(script)], cwd=str(_PROJECT_ROOT), env=_subprocess_env())
        return _vendor_exists() and _model_exists()
    except subprocess.CalledProcessError:
        return False


def install_requirements(provider: str, offline: bool) -> bool:
    if provider == "mock":
        return True

    # 优先本地 vendor
    if _vendor_exists():
        return _install_from_wheels()

    if offline:
        print("[bootstrap] Offline mode but vendor/wheels not found")
        return _provider_deps_ok(provider)

    # 尝试在线安装
    import_map = {
        "llama-cpp-python": "llama_cpp",
        "huggingface-hub": "huggingface_hub",
        "anthropic": "anthropic",
        "requests": "requests",
        "openai": "openai",
        "sentence-transformers": "sentence_transformers",
        "faiss-cpu": "faiss",
        "numpy": "numpy",
        "pywebview": "webview",
        "playwright": "playwright",
    }
    packages = []
    if provider in ("openai", "deepseek", "api"):
        packages += ["requests", "openai"]
    if provider in ("claude", "anthropic"):
        packages += ["requests", "anthropic"]
    if provider in ("local", "gguf"):
        packages += ["llama-cpp-python", "huggingface-hub"]
    if provider != "mock":
        packages += ["sentence-transformers", "faiss-cpu", "numpy"]

    # 桌面 GUI 核心依赖
    packages += ["pywebview"]

    # 浏览器自动化（Phase 7）
    packages += ["playwright"]

    missing = [p for p in packages if not _has(import_map.get(p, p))]
    if not missing:
        return _ensure_chromium()

    if _is_online():
        if not _install_from_pypi(missing):
            return False
        return _ensure_chromium()

    print("[bootstrap] No network and no vendor/wheels")
    return False


def _provider_deps_ok(provider: str) -> bool:
    ok = True
    if provider in ("local", "gguf"):
        ok = ok and _has("llama_cpp") and _has("huggingface_hub")
    if provider in ("openai", "deepseek", "api"):
        ok = ok and _has("requests") and _has("openai")
    if provider in ("claude", "anthropic"):
        ok = ok and _has("requests") and _has("anthropic")
    return ok


def ensure_model(provider: str) -> bool:
    if provider not in ("local", "gguf"):
        return True

    if _model_exists():
        print(f"[bootstrap] Local model ready: {MODELS_DIR / DEFAULT_MODEL}")
        return True

    print("[bootstrap] Local model not found")
    return False


def ensure_embeddings() -> bool:
    """embedding 模型是可选的，有则加速，无则 keyword fallback。"""
    if _embeddings_exists():
        print("[bootstrap] Embedding model ready")
        return True
    if _has("sentence_transformers"):
        print("[bootstrap] sentence-transformers installed, embedding model will download on first use")
        return True
    print("[bootstrap] Embedding model not preloaded; vector memory will fallback to keyword search")
    return True


def ensure_playwright() -> bool:
    """Playwright Chromium 是可选的。离线包存在时优先使用。"""
    if _playwright_exists():
        print("[bootstrap] Offline Chromium browser ready")
        return True
    if _has("playwright"):
        print("[bootstrap] Playwright installed, Chromium will download on first use if not offline")
        return True
    print("[bootstrap] Playwright not installed; browser tools unavailable")
    return True


def main() -> int:
    print("[bootstrap] Checking TTMEvolve environment...")

    offline = "--offline" in sys.argv or os.getenv("TTM_EVOLVE_OFFLINE", "").lower() in ("1", "true", "yes")
    force_mock = "--mock" in sys.argv
    provider = os.getenv("TTM_EVOLVE_PROVIDER", "")

    if not provider and not force_mock:
        try:
            config = Config(str(_PROJECT_ROOT / "config.json"))
            provider = config.llm_provider()
        except Exception:
            provider = "local"

    if force_mock:
        provider = "mock"

    if provider == "mock":
        print("[bootstrap] Mock mode ready")
        return 0

    # 如果没有 vendor 和模型，且不在离线模式，自动准备
    if not offline and not (_vendor_exists() and _model_exists()):
        if _is_online():
            if not _prepare_offline_env():
                print("[bootstrap] Failed to prepare offline environment")
        else:
            print("[bootstrap] No network; cannot prepare environment")

    deps_ok = install_requirements(provider, offline)
    model_ok = ensure_model(provider)
    emb_ok = ensure_embeddings()
    pw_ok = ensure_playwright()

    if deps_ok and model_ok and emb_ok and pw_ok:
        print("[bootstrap] Environment ready")
        return 0

    if not deps_ok:
        print("[bootstrap] Dependencies not ready")
    if not model_ok:
        print("[bootstrap] Model not ready")

    print("[bootstrap] Will fallback to Mock mode")
    return 2


if __name__ == "__main__":
    sys.exit(main())
