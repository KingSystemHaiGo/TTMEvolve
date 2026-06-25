"""
core/project_context.py — 向后兼容 re-export

ProjectContext 已移动到 `ecosystem.project_context`，请优先从那里导入。
"""

from __future__ import annotations
from ecosystem.project_context import ProjectContext  # noqa: F401

__all__ = ["ProjectContext"]
