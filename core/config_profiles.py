"""
core/config_profiles.py — 配置 Profile

允许在 config.json 中定义多个 profile，并按 name 激活。
Profile 会覆盖基础配置中的同名键。
"""

from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, Optional

from core.config import Config


class ConfigProfiles:
    """管理 config.json 中的 profiles 块。"""

    def __init__(self, config: Config):
        self._base = deepcopy(config.data)
        self._profiles = self._base.get("profiles", {})
        self._active_name = self._base.get("active_profile", "default")

    def names(self):
        return list(self._profiles.keys())

    def active_name(self) -> str:
        return self._active_name

    def get(self, key: str, default: Any = None) -> Any:
        """按点号路径读取：先读 profile 覆盖，再读 base。"""
        keys = key.split(".")
        profile_data = self._profiles.get(self._active_name, {})

        # Try profile first
        data = profile_data
        for k in keys:
            if isinstance(data, dict) and k in data:
                data = data[k]
            else:
                break
        else:
            return data

        # Fallback to base
        data = self._base
        for k in keys:
            if isinstance(data, dict) and k in data:
                data = data[k]
            else:
                return default
        return data

    def merged(self) -> Dict[str, Any]:
        """返回 base + active profile 的合并结果。"""
        result = deepcopy(self._base)
        profile = deepcopy(self._profiles.get(self._active_name, {}))
        self._merge(result, profile)
        return result

    @staticmethod
    def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConfigProfiles._merge(base[k], v)
            else:
                base[k] = v
