"""
core/version_manager.py — 版本管理与回滚

每次 Agent 修改代码/配置前，核心运转层先打快照。
修改后如果健康指标下降，自动回滚到上一个已知良好的版本。
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import json
import shutil
import subprocess


@dataclass
class VersionSnapshot:
    version_id: str
    created_at: str
    description: str
    source_paths: List[str]
    snapshot_dir: Path
    health_score: float = 1.0

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "created_at": self.created_at,
            "description": self.description,
            "source_paths": self.source_paths,
            "snapshot_dir": str(self.snapshot_dir),
            "health_score": self.health_score,
        }


class VersionManager:
    """
    管理代码/配置版本。
    - 使用 git tag 标记稳定版本（如果项目在 git 中）。
    - 同时维护本地快照目录，用于非 git 文件或快速回滚。
    """

    def __init__(self, project_root: Path, storage_path: Path):
        self.project_root = Path(project_root)
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_path = storage_path / "versions.json"
        self._versions: List[VersionSnapshot] = []
        self._load()

    def snapshot(self, description: str, paths: List[str]) -> VersionSnapshot:
        now = datetime.now(timezone.utc)
        vid = f"evo-{now.strftime('%Y%m%d-%H%M%S')}"
        snap_dir = self.storage_path / vid
        snap_dir.mkdir(parents=True, exist_ok=True)

        for rel in paths:
            src = self.project_root / rel
            if not src.exists():
                continue
            dst = snap_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        snap = VersionSnapshot(
            version_id=vid,
            created_at=now.isoformat(),
            description=description,
            source_paths=paths,
            snapshot_dir=snap_dir,
        )
        self._versions.append(snap)
        self._save()

        # 同时打 git 标签
        self._git_tag(vid, description)
        return snap

    def rollback(self, version_id: Optional[str] = None) -> Optional[VersionSnapshot]:
        target = None
        if version_id:
            target = next((v for v in self._versions if v.version_id == version_id), None)
        if not target:
            # 回滚到最近一个 health_score 最高的版本
            candidates = [v for v in self._versions if v.health_score >= 0.8]
            if candidates:
                target = max(candidates, key=lambda v: v.health_score)
        if not target:
            return None

        for rel in target.source_paths:
            src = target.snapshot_dir / rel
            dst = self.project_root / rel
            if not src.exists():
                continue
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        self._git_tag(f"rollback-{target.version_id}", f"Rollback to {target.version_id}")
        return target

    def list_versions(self) -> List[VersionSnapshot]:
        return list(reversed(self._versions))

    def update_health(self, version_id: str, health_score: float) -> None:
        for v in self._versions:
            if v.version_id == version_id:
                v.health_score = health_score
        self._save()

    def _git_tag(self, tag: str, message: str) -> None:
        if not (self.project_root / ".git").exists():
            return
        try:
            subprocess.run(
                ["git", "tag", "-a", tag, "-m", message],
                cwd=self.project_root,
                check=True,
                capture_output=True,
            )
        except Exception:
            pass

    def _save(self) -> None:
        data = [v.to_dict() for v in self._versions]
        self._index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            for d in data:
                self._versions.append(VersionSnapshot(
                    version_id=d["version_id"],
                    created_at=d["created_at"],
                    description=d["description"],
                    source_paths=d["source_paths"],
                    snapshot_dir=Path(d["snapshot_dir"]),
                    health_score=d.get("health_score", 1.0),
                ))
        except Exception:
            pass
