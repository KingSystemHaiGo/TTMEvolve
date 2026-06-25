"""
scripts/verify_offline.py — 校验离线包完整性

读取 vendor/manifest.json，检查所有列出的文件是否存在、大小是否匹配，
并验证 vendor/wheels/ 包含 requirements.txt 中所有包的 wheel。

用法：
    python scripts/verify_offline.py
    python scripts/verify_offline.py --deep-check    # 同时校验 sha256（慢）
"""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_wheels() -> list[str]:
    """检查 requirements.txt 中的每个包是否在 vendor/wheels/ 中有对应 wheel。"""
    errors = []
    req_file = _PROJECT_ROOT / "requirements.txt"
    wheels_dir = _PROJECT_ROOT / "vendor" / "wheels"
    if not req_file.exists():
        errors.append("requirements.txt not found")
        return errors
    if not wheels_dir.exists():
        errors.append("vendor/wheels/ not found")
        return errors

    wheels = list(wheels_dir.glob("*.whl"))
    lines = req_file.read_text(encoding="utf-8").splitlines()
    for raw in lines:
        line = raw.split("#")[0].strip()
        if not line:
            continue
        # 提取包名（去掉版本号等）
        pkg = line.split("=")[0].split("<")[0].split(">")[0].strip().lower()
        pkg_norm = pkg.replace("-", "_")
        # 有些包名和 wheel 名不同
        matched = any(
            wheel.name.lower().replace("-", "_").startswith(pkg_norm + "_")
            for wheel in wheels
        )
        if not matched:
            errors.append(f"missing wheel for package: {pkg}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify TTMEvolve offline package")
    parser.add_argument("--deep-check", action="store_true", help="also verify sha256 for all files")
    args = parser.parse_args()

    manifest_path = _PROJECT_ROOT / "vendor" / "manifest.json"
    if not manifest_path.exists():
        print("[verify] ERROR: vendor/manifest.json not found; run scripts/build_embedded.py first")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    checked = 0

    for entry in manifest.get("entries", []):
        rel = entry["path"]
        full = _PROJECT_ROOT / "vendor" / rel
        checked += 1
        if not full.exists():
            errors.append(f"missing: {rel}")
            continue
        actual_size = full.stat().st_size
        expected_size = entry.get("size")
        if expected_size is not None and actual_size != expected_size:
            errors.append(f"size mismatch: {rel} (expected {expected_size}, got {actual_size})")
            continue
        expected_sha = entry.get("sha256")
        if args.deep_check and expected_sha:
            actual_sha = _sha256(full)
            if actual_sha != expected_sha:
                errors.append(f"sha256 mismatch: {rel}")

    for model in manifest.get("models", []):
        rel = model["path"]
        full = _PROJECT_ROOT / rel
        checked += 1
        if not full.exists():
            errors.append(f"missing model: {rel}")
            continue
        actual_size = full.stat().st_size
        expected_size = model.get("size")
        if expected_size is not None and actual_size != expected_size:
            errors.append(f"size mismatch: {rel} (expected {expected_size}, got {actual_size})")

    wheel_errors = _check_wheels()
    errors.extend(wheel_errors)

    if errors:
        print(f"[verify] {checked} entries checked, {len(errors)} error(s):")
        for err in errors:
            print(f"[verify]  - {err}")
        return 1

    print(f"[verify] All checks passed ({checked} entries, {len(wheel_errors)} wheel checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
