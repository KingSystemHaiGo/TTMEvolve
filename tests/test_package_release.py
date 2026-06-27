from __future__ import annotations

import json
import zipfile

import scripts.package_release as package_release


def test_package_release_excludes_private_runtime_and_build_state(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "config.example.json").write_text("{}\n", encoding="utf-8")
    (root / "config.json").write_text('{"api_key":"secret"}\n', encoding="utf-8")
    (root / ".env.embedded").write_text("SECRET=1\n", encoding="utf-8")
    (root / ".mcp.json").write_text("{}\n", encoding="utf-8")
    (root / "TTMEvolve.vbs").write_text("' launcher\n", encoding="utf-8")
    (root / "scripts" / "build-portable").mkdir(parents=True)
    (root / "scripts" / "build-portable" / "config.json").write_text("{}\n", encoding="utf-8")

    for rel in [
        "storage/session.db",
        "portable/home/token",
        "vendor/wheels/pkg.whl",
        "models/model.gguf",
        "workspace/private-game/main.lua",
        "src-tauri/target/release/ttmevolve.exe",
        "frontend/dist/assets/app.js",
        "logs/start.log",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private\n", encoding="utf-8")

    monkeypatch.setattr(package_release, "_PROJECT_ROOT", root)
    output = root / "release-artifacts" / "TTMEvolve-source-test.zip"

    package_release.package_release(output)

    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())

    assert "main.py" in names
    assert "config.example.json" in names
    assert "TTMEvolve.vbs" in names
    assert "scripts/build-portable/config.json" in names
    assert "config.json" not in names
    assert ".env.embedded" not in names
    assert ".mcp.json" not in names
    assert not any(name.startswith("storage/") for name in names)
    assert not any(name.startswith("portable/") for name in names)
    assert not any(name.startswith("vendor/") for name in names)
    assert not any(name.startswith("models/") for name in names)
    assert not any(name.startswith("workspace/") for name in names)
    assert not any(name.startswith("src-tauri/target/") for name in names)
    assert not any(name.startswith("release-artifacts/") for name in names)

    manifest = json.loads(output.with_suffix(".zip.manifest.json").read_text(encoding="utf-8"))
    assert manifest["forbidden_entries"] == []
    assert manifest["file_count"] == len(names)


def test_validate_archive_entries_flags_release_blockers():
    forbidden = package_release.validate_archive_entries([
        "main.py",
        "config.json",
        "portable/home/auth.json",
        "src-tauri/target/release/app.exe",
        "project/.maker-mcp/config.json",
    ])

    assert "config.json" in forbidden
    assert "portable/home/auth.json" in forbidden
    assert "src-tauri/target/release/app.exe" in forbidden
    assert "project/.maker-mcp/config.json" in forbidden
