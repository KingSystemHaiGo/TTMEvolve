"""
core/resource_registry.py — 自进化资源注册表

所有可进化对象统一抽象为 Resource：
- prompt
- agent_code
- tool / skill
- mcp_server
- memory_index
- config_profile

每个资源记录：id、type、version、content_hash、source、rollback_target、enabled。
"""

from __future__ import annotations
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


RESOURCE_TYPES = {
    "prompt",
    "agent_code",
    "tool",
    "skill",
    "mcp_server",
    "memory_index",
    "config_profile",
}


@dataclass
class Resource:
    id: str
    type: str
    version: str
    content: str
    content_hash: str
    source: str = "unknown"
    rollback_target: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Resource":
        return cls(**data)


class ResourceRegistry:
    """资源注册表：版本化、可回滚。"""

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.storage_path / "resources.jsonl"
        self._resources: Dict[str, List[Resource]] = {}
        self._load()

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def register(
        self,
        resource_id: str,
        resource_type: str,
        content: str,
        source: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> Resource:
        if resource_type not in RESOURCE_TYPES:
            raise ValueError(f"未知资源类型：{resource_type}")

        versions = self._resources.get(resource_id, [])
        new_version = f"v{len(versions) + 1}"
        rollback_target = versions[-1].version if versions else None

        resource = Resource(
            id=resource_id,
            type=resource_type,
            version=new_version,
            content=content,
            content_hash=self.compute_hash(content),
            source=source,
            rollback_target=rollback_target,
            enabled=enabled,
            metadata=metadata or {},
        )
        versions.append(resource)
        self._resources[resource_id] = versions
        self._save(resource)
        return resource

    def get(self, resource_id: str, version: Optional[str] = None) -> Optional[Resource]:
        versions = self._resources.get(resource_id, [])
        if not versions:
            return None
        if version is None:
            # 返回最新启用版本
            for r in reversed(versions):
                if r.enabled:
                    return r
            return versions[-1]
        for r in versions:
            if r.version == version:
                return r
        return None

    def list_resources(self, resource_type: Optional[str] = None) -> List[str]:
        if resource_type is None:
            return list(self._resources.keys())
        return [
            rid
            for rid, versions in self._resources.items()
            if versions and versions[-1].type == resource_type
        ]

    def rollback(self, resource_id: str, version: Optional[str] = None) -> Optional[Resource]:
        """回滚到指定版本；不指定则回滚到上一个版本。"""
        versions = self._resources.get(resource_id, [])
        if not versions:
            return None
        target = version
        if target is None:
            target = versions[-1].rollback_target
        if not target:
            return None
        target_res = self.get(resource_id, target)
        if not target_res:
            return None
        # 创建一个新版本，内容复制目标版本
        return self.register(
            resource_id=resource_id,
            resource_type=target_res.type,
            content=target_res.content,
            source=f"rollback_from_{versions[-1].version}_to_{target}",
            metadata={**target_res.metadata, "rollback_source": target},
        )

    def disable(self, resource_id: str, version: Optional[str] = None) -> bool:
        resource = self.get(resource_id, version)
        if not resource:
            return False
        resource.enabled = False
        self._save(resource)
        return True

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        for line in self._index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                resource = Resource.from_dict(json.loads(line))
                self._resources.setdefault(resource.id, []).append(resource)
            except Exception:
                continue

    def _save(self, resource: Resource) -> None:
        with self._index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(resource.to_dict(), ensure_ascii=False) + "\n")
