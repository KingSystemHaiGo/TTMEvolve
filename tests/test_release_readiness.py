from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts import release_readiness


def _write_zip(path: Path, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in entries.items():
            zf.writestr(name, text)


def _write_manifest(zip_path: Path, *, file_count: int) -> None:
    manifest = {
        "package": zip_path.name,
        "sha256": release_readiness._sha256(zip_path),
        "size_bytes": zip_path.stat().st_size,
        "file_count": file_count,
        "forbidden_entries": [],
    }
    zip_path.with_suffix(zip_path.suffix + ".manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_release_readiness_source_package_passes_with_clean_manifest(tmp_path):
    zip_path = tmp_path / "release-artifacts" / "TTMEvolve-source.zip"
    _write_zip(zip_path, {"main.py": "print('ok')", "README.md": "# ok"})
    _write_manifest(zip_path, file_count=2)

    result = release_readiness.audit_source_package(zip_path)

    assert result["status"] == "ready"
    assert result["forbidden_count"] == 0
    assert result["probe_hits"] == {}
    assert result["manifest_mismatches"] == []


def test_release_readiness_source_package_blocks_private_entries(tmp_path):
    zip_path = tmp_path / "release-artifacts" / "TTMEvolve-source.zip"
    _write_zip(zip_path, {"main.py": "ok", "config.json": "secret"})
    _write_manifest(zip_path, file_count=2)

    result = release_readiness.audit_source_package(zip_path)

    assert result["status"] == "blocked"
    assert result["forbidden_count"] == 1
    assert "config.json" in result["probe_hits"]


def test_release_readiness_reports_unproven_release_claims(tmp_path):
    root = tmp_path
    for rel in [
        "TTMEvolve.vbs",
        "TTMEvolve-Practice.vbs",
        "start-tauri.bat",
        "src-tauri/target/release/ttmevolve.exe",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")
    (root / ".gitignore").write_text("release-artifacts/\n", encoding="utf-8")

    zip_path = root / "release-artifacts" / "TTMEvolve-source.zip"
    _write_zip(zip_path, {"main.py": "ok"})
    _write_manifest(zip_path, file_count=1)

    report = release_readiness.build_release_readiness_report(
        project_root=root,
        package_path=zip_path,
    )

    assert report["status"] == "blocked"
    assert report["mode"] == "full-offline"
    assert "offline_runtime_bundle" in report["required_checks"]
    assert report["checks"]["source_package"]["status"] == "ready"
    assert report["checks"]["launch_surface"]["status"] == "ready"
    assert report["checks"]["offline_runtime_bundle"]["status"] == "blocked"
    assert report["closure_gate"]["can_claim_full_publishable_release"] is False


def test_release_readiness_source_checkpoint_mode_allows_scoped_claim(tmp_path, monkeypatch):
    root = tmp_path
    for rel in [
        "TTMEvolve.vbs",
        "TTMEvolve-Practice.vbs",
        "start-tauri.bat",
        "src-tauri/target/release/ttmevolve.exe",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")
    (root / ".gitignore").write_text("release-artifacts/\n", encoding="utf-8")
    monkeypatch.setattr(
        release_readiness,
        "audit_git_artifacts_ignored",
        lambda project_root: release_readiness._check(
            True,
            "ready",
            "release-artifacts is git-ignored",
            path=str(project_root / "release-artifacts"),
        ),
    )

    zip_path = root / "release-artifacts" / "TTMEvolve-source.zip"
    _write_zip(zip_path, {"main.py": "ok"})
    _write_manifest(zip_path, file_count=1)

    report = release_readiness.build_release_readiness_report(
        project_root=root,
        package_path=zip_path,
        mode=release_readiness.SOURCE_CHECKPOINT_MODE,
    )

    assert report["status"] == "ready"
    assert report["mode"] == "source-checkpoint"
    assert report["required_checks"] == [
        "source_package",
        "launch_surface",
        "release_artifacts_ignored",
    ]
    assert "offline_runtime_bundle" in report["informational_checks"]
    assert report["out_of_scope"]["offline_runtime_bundle"] == "blocked"
    assert report["closure_gate"]["can_claim_source_checkpoint_ready"] is True
    assert report["closure_gate"]["can_claim_full_publishable_release"] is False


def test_release_readiness_rejects_unknown_mode(tmp_path):
    zip_path = tmp_path / "release-artifacts" / "TTMEvolve-source.zip"
    _write_zip(zip_path, {"main.py": "ok"})
    _write_manifest(zip_path, file_count=1)

    try:
        release_readiness.build_release_readiness_report(
            project_root=tmp_path,
            package_path=zip_path,
            mode="optimistic",
        )
    except ValueError as exc:
        assert "unsupported release readiness mode" in str(exc)
    else:
        raise AssertionError("unknown release readiness mode should fail")


def test_release_readiness_offline_runtime_blocks_missing_python(tmp_path):
    portable = tmp_path / "portable"
    (portable / "cache").mkdir(parents=True)
    (portable / "cache" / "state.txt").write_text("cache", encoding="utf-8")

    result = release_readiness.audit_offline_runtime_bundle(tmp_path)

    assert result["status"] == "blocked"
    assert any("portable Python missing" in item for item in result["failures"])
