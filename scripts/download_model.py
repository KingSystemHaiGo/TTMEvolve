"""
scripts/download_model.py — 下载默认本地 GGUF 模型

默认下载 MiniCPM5-1B Q4_K_M，可通过参数或 config.json 覆盖。
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config


def download(repo_id: str, filename: str, local_dir: Path) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("[bootstrap] 请先安装 huggingface-hub：pip install huggingface-hub")
        sys.exit(1)

    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"⬇️  下载 {repo_id}/{filename} 到 {local_dir}")
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
    )
    return Path(path)


def main():
    parser = argparse.ArgumentParser(description="下载 TTMEvolve 本地模型")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--repo", help="HuggingFace repo，默认读取 config.llm.local_model_repo")
    parser.add_argument("--file", help="模型文件名，默认读取 config.llm.local_model_file")
    parser.add_argument("--dir", default="./models", help="本地保存目录")
    args = parser.parse_args()

    config = Config(args.config)
    repo = args.repo or config.local_model_repo()
    filename = args.file or config.local_model_file()
    target_dir = Path(args.dir).resolve()

    downloaded = download(repo, filename, target_dir)
    print(f"✅ 模型已下载: {downloaded}")
    print(f"\n请在 config.json 中设置：")
    print(f'  "llm": {{')
    print(f'    "provider": "local",')
    print(f'    "model_path": "{downloaded}"')
    print(f"  }}")


if __name__ == "__main__":
    main()
