"""
agent/config.py — 向后兼容 re-export

Config 已下沉到 `core.config`，请优先从那里导入。
"""

from __future__ import annotations
from core.config import Config  # noqa: F401

__all__ = ["Config"]
