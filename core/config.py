"""
agent/config.py — 配置加载

支持 profile 覆盖：config.json 中定义 profiles 块，
通过 active_profile 指定当前生效的 profile。
"""

from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional
import json


class Config:
    """TTMEvolve 配置。"""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or "config.json")
        self.base_dir = self.path.resolve().parent
        self.data: Dict[str, Any] = self._load()
        self._profiles = self.data.get("profiles", {})
        self._active_profile = self.data.get("active_profile", "default")

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8-sig"))

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clone(self) -> "Config":
        """Return an in-memory copy that can be safely mutated per session."""
        cloned = Config.__new__(Config)
        cloned.path = self.path
        cloned.base_dir = self.base_dir
        cloned.data = deepcopy(self.data)
        cloned._profiles = cloned.data.get("profiles", {})
        cloned._active_profile = cloned.data.get("active_profile", self._active_profile)
        return cloned

    def active_profile(self) -> str:
        return self._active_profile

    def get(self, key: str, default: Any = None) -> Any:
        """按点号路径读取：先读 active profile 覆盖，再读 base。"""
        keys = key.split(".")

        # Try active profile first
        data = self._profiles.get(self._active_profile, {})
        for k in keys:
            if isinstance(data, dict) and k in data:
                data = data[k]
            else:
                break
        else:
            return data

        # Fallback to base config
        data = self.data
        for k in keys:
            if isinstance(data, dict) and k in data:
                data = data[k]
            else:
                return default
        return data

    def merged(self) -> Dict[str, Any]:
        """返回 base + active profile 的合并结果。"""
        result = deepcopy(self.data)
        profile = deepcopy(self._profiles.get(self._active_profile, {}))
        self._merge(result, profile)
        return result

    @staticmethod
    def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                Config._merge(base[k], v)
            else:
                base[k] = v

    def maker_mcp_config(self) -> Dict[str, Any]:
        cfg = deepcopy(self.get("maker_mcp", {}))
        if isinstance(cfg, dict) and cfg.get("cwd"):
            cfg["cwd"] = str(self._resolve_path(cfg["cwd"]))
        return cfg

    def project_root(self) -> Path:
        return self._resolve_path(self.get("project_root", "."))

    def storage_root(self) -> Path:
        return self._resolve_path(self.get("storage_root", "./storage"))

    def portable_root(self) -> Path:
        return self._resolve_path(self.get("runtime.portable_root", "./portable"))

    def llm_config(self) -> Dict[str, Any]:
        return self.get("llm", {})

    def llm_provider(self) -> str:
        return self.get("llm.provider", "local")

    def local_model_path(self) -> Path:
        return self._resolve_path(self.get("llm.model_path", "./models/MiniCPM5-1B-Q4_K_M.gguf"))

    def local_model_repo(self) -> str:
        return self.get("llm.local_model_repo", "openbmb/MiniCPM5-1B-GGUF")

    def local_model_file(self) -> str:
        return self.get("llm.local_model_file", "MiniCPM5-1B-Q4_K_M.gguf")

    def sandbox_mode(self) -> str:
        return self.get("sandbox.mode", "workspace-write")

    def approval_policy(self) -> str:
        return self.get("approval.policy", "on-request")

    def mcp_servers(self) -> Dict[str, Any]:
        return self.get("mcp_servers", {})

    def expert_config(self) -> Dict[str, Any]:
        return self.get("expert", {})

    def rescue_config(self) -> Dict[str, Any]:
        return self.get("rescue", {})

    def learning_config(self) -> Dict[str, Any]:
        return self.get("learning", {})

    def compression_config(self) -> Dict[str, Any]:
        return self.get("llm.compression", {})

    def hot_memory_max_turns(self) -> int:
        return self.get("llm.hot_memory_max_turns", 6)

    def warm_memory_budget_tokens(self) -> int:
        return self.get("llm.warm_memory_budget_tokens", 1500)

    def kv_cache_max_entries(self) -> int:
        return self.get("llm.kv_cache_max_entries", 8)

    def vector_index_config(self) -> Dict[str, Any]:
        return self.get("memory.vector_index", {})

    def agents_md_config(self) -> Dict[str, Any]:
        return self.get("agents_md", {})

    def runtime_tool_timeout_seconds(self) -> float:
        return float(self.get("runtime.tool_timeout_seconds", 45))

    def runtime_shell_timeout_seconds(self) -> float:
        return float(self.get("runtime.shell_timeout_seconds", self.runtime_tool_timeout_seconds()))

    def maker_mcp_request_timeout_seconds(self) -> float:
        return float(self.get("maker_mcp.request_timeout_seconds", 30))

    def _resolve_path(self, value: Any) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path.resolve()
        return (self.base_dir / path).resolve()
