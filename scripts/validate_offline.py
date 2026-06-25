"""
scripts/validate_offline.py — 验证离线环境可用性

在断网环境下运行，确认：
1. requirements.txt 中的关键包都能 import
2. GGUF 模型能被 llama_cpp 加载
3. embedding 模型能从 vendor/embeddings/ 加载
4. FAISS 可用
5. Playwright 能从 vendor/playwright/ 启动 Chromium

用法：
    python scripts/validate_offline.py
"""

from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _info(msg: str) -> None:
    print(f"[validate] {msg}")


def _error(msg: str) -> None:
    print(f"[validate] ERROR: {msg}", file=sys.stderr)


def check_imports() -> list[str]:
    """验证 requirements.txt 中的包都能 import。"""
    errors = []
    import_map = {
        "anthropic": "anthropic",
        "requests": "requests",
        "llama-cpp-python": "llama_cpp",
        "huggingface-hub": "huggingface_hub",
        "sentence-transformers": "sentence_transformers",
        "faiss-cpu": "faiss",
        "numpy": "numpy",
        "playwright": "playwright",
        "pywebview": "webview",
    }

    req_file = _PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        errors.append("requirements.txt not found")
        return errors

    lines = req_file.read_text(encoding="utf-8").splitlines()
    for raw in lines:
        line = raw.split("#")[0].strip()
        if not line:
            continue
        pkg = line.split("=")[0].split("<")[0].split(">")[0].strip()
        module = import_map.get(pkg, pkg)
        try:
            __import__(module)
            _info(f"import ok: {module}")
        except Exception as e:
            errors.append(f"import failed: {module} ({e})")
    return errors


def check_model() -> list[str]:
    errors = []
    model_path = _PROJECT_ROOT / "models" / "MiniCPM5-1B-Q4_K_M.gguf"
    if not model_path.exists():
        errors.append(f"model not found: {model_path}")
        return errors

    _info("loading GGUF model in subprocess (may take a few seconds)...")
    script = """
import sys
from pathlib import Path
from llama_cpp import Llama
model_path = Path(r'%s')
try:
    llm = Llama(
        model_path=str(model_path),
        n_ctx=512,
        n_batch=128,
        n_threads=1,
        use_mmap=True,
        use_mlock=False,
        verbose=False,
    )
    print('MODEL_OK')
except Exception as e:
    print(f'MODEL_FAIL: {e}', file=sys.stderr)
    sys.exit(1)
""" % str(model_path).replace("\\", "/")
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and "MODEL_OK" in result.stdout:
            _info(f"model load ok: {model_path}")
        else:
            err = (result.stderr or result.stdout or "unknown error").strip()
            errors.append(f"model load failed: {err}")
    except subprocess.TimeoutExpired:
        errors.append("model load timed out")
    except Exception as e:
        errors.append(f"model load subprocess failed: {e}")
    return errors


def check_embeddings() -> list[str]:
    errors = []
    vendor_emb = _PROJECT_ROOT / "vendor" / "embeddings"
    if not vendor_emb.exists():
        errors.append("vendor/embeddings/ not found")
        return errors

    _info("loading embedding model in subprocess...")
    script = """
import os, sys
from pathlib import Path
from sentence_transformers import SentenceTransformer
vendor_emb = Path(r'%s')
os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(vendor_emb)
model_dir = vendor_emb / 'paraphrase-multilingual-MiniLM-L12-v2'
try:
    model = SentenceTransformer(str(model_dir), local_files_only=True)
    emb = model.encode(['hello'], convert_to_numpy=True, normalize_embeddings=True)
    print(f'EMB_OK {emb.shape[-1]}')
except Exception as e:
    print(f'EMB_FAIL: {e}', file=sys.stderr)
    sys.exit(1)
""" % str(vendor_emb).replace("\\", "/")
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and "EMB_OK" in result.stdout:
            dim = result.stdout.strip().split()[-1]
            _info(f"embedding model ok, dim={dim}")
        else:
            err = (result.stderr or result.stdout or "unknown error").strip()
            errors.append(f"embedding model load failed: {err}")
    except subprocess.TimeoutExpired:
        errors.append("embedding model load timed out")
    except Exception as e:
        errors.append(f"embedding model subprocess failed: {e}")
    return errors


def check_faiss() -> list[str]:
    errors = []
    try:
        import faiss
        import numpy as np
        index = faiss.IndexFlatIP(8)
        vec = np.random.rand(1, 8).astype("float32")
        index.add(vec)
        _info("faiss ok")
    except Exception as e:
        errors.append(f"faiss check failed: {e}")
    return errors


def check_playwright() -> list[str]:
    errors = []
    browser_dir = _PROJECT_ROOT / "vendor" / "playwright"
    if not browser_dir.exists():
        errors.append("vendor/playwright/ not found")
        return errors

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
    try:
        from playwright.sync_api import sync_playwright
        _info("starting Chromium from vendor/playwright...")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("about:blank")
        browser.close()
        pw.stop()
        _info("chromium ok")
    except Exception as e:
        errors.append(f"chromium start failed: {e}")
    return errors


def main() -> int:
    _info("Validating TTMEvolve offline environment...")
    errors = []
    errors.extend(check_imports())
    errors.extend(check_faiss())
    errors.extend(check_model())
    errors.extend(check_embeddings())
    errors.extend(check_playwright())

    if errors:
        print(f"\n[validate] {len(errors)} error(s) found:")
        for err in errors:
            print(f"[validate]  - {err}")
        return 1

    _info("All validation checks passed")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
