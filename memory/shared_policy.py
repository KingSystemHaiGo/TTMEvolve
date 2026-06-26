"""
memory/shared_policy.py - multi-agent shared memory policy surface.

The policy is intentionally conservative: memory is shareable only when its
metadata says so, and private records stay visible only to their owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Set


KNOWN_VISIBILITIES = {"private", "shared", "public"}
KNOWN_PROFILES = {"coding", "docs", "maker", "browser", "general"}


@dataclass(frozen=True)
class SharedMemoryPolicy:
    agent_id: str = "default"
    read_profiles: Optional[Set[str]] = None
    write_profiles: Optional[Set[str]] = None
    include_general: bool = True
    can_read_shared: bool = True
    can_read_public: bool = True
    can_read_private_own: bool = True
    can_read_private_other: bool = False
    default_visibility: str = "private"

    @classmethod
    def from_config(
        cls,
        config: Any = None,
        *,
        agent_id: str = "default",
    ) -> "SharedMemoryPolicy":
        cfg = config if isinstance(config, dict) else {}
        profiles = cfg.get("profiles") if isinstance(cfg.get("profiles"), dict) else {}
        profile_cfg = profiles.get(agent_id) if isinstance(profiles.get(agent_id), dict) else {}
        merged = {**cfg, **profile_cfg}
        return cls(
            agent_id=str(agent_id or merged.get("agent_id") or "default"),
            read_profiles=_profile_set(merged.get("read_profiles")),
            write_profiles=_profile_set(merged.get("write_profiles")),
            include_general=bool(merged.get("include_general", True)),
            can_read_shared=bool(merged.get("can_read_shared", True)),
            can_read_public=bool(merged.get("can_read_public", True)),
            can_read_private_own=bool(merged.get("can_read_private_own", True)),
            can_read_private_other=bool(merged.get("can_read_private_other", False)),
            default_visibility=_normalize_visibility(merged.get("default_visibility"), "private"),
        )

    def can_index(self, profile: str) -> bool:
        normalized = _normalize_profile(profile)
        return self.write_profiles is None or normalized in self.write_profiles

    def can_read(self, meta: Dict[str, Any], profile: str) -> bool:
        target_profile = _normalize_profile(profile)
        entry_profile = _normalize_profile(meta.get("workspace_profile") or meta.get("profile"))
        if self.read_profiles is not None and entry_profile not in self.read_profiles:
            if not (self.include_general and entry_profile == "general"):
                return False
        if target_profile != "general" and entry_profile == "general" and not self.include_general:
            return False

        owner = str(meta.get("agent_id") or meta.get("source_agent") or "")
        visibility = _normalize_visibility(meta.get("visibility"), self.default_visibility)
        if visibility == "public":
            return self.can_read_public
        if visibility == "shared":
            return self.can_read_shared
        if owner and owner == self.agent_id:
            return self.can_read_private_own
        if not owner and self.agent_id == "default":
            return self.can_read_private_own
        return self.can_read_private_other

    def apply_index_metadata(self, item: Dict[str, Any]) -> Dict[str, Any]:
        next_item = dict(item)
        next_item["agent_id"] = str(
            next_item.get("agent_id") or next_item.get("source_agent") or self.agent_id
        )
        next_item["visibility"] = _normalize_visibility(
            next_item.get("visibility"),
            self.default_visibility,
        )
        return next_item

    def to_summary(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "read_profiles": sorted(self.read_profiles) if self.read_profiles is not None else ["*"],
            "write_profiles": sorted(self.write_profiles) if self.write_profiles is not None else ["*"],
            "include_general": self.include_general,
            "can_read_shared": self.can_read_shared,
            "can_read_public": self.can_read_public,
            "can_read_private_own": self.can_read_private_own,
            "can_read_private_other": self.can_read_private_other,
            "default_visibility": self.default_visibility,
            "boundary": (
                "private_other_allowed"
                if self.can_read_private_other
                else "owner_private_plus_explicit_shared"
            ),
        }


def _profile_set(value: Any) -> Optional[Set[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        raw: Iterable[Any] = [value]
    elif isinstance(value, Iterable):
        raw = value
    else:
        return None
    profiles = {_normalize_profile(item) for item in raw}
    return {profile for profile in profiles if profile in KNOWN_PROFILES}


def _normalize_profile(value: Any) -> str:
    profile = str(value or "general").strip().lower()
    return profile if profile in KNOWN_PROFILES else "general"


def _normalize_visibility(value: Any, default: str = "private") -> str:
    visibility = str(value or default or "private").strip().lower()
    return visibility if visibility in KNOWN_VISIBILITIES else default
