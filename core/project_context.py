"""
Backward-compatible access to ecosystem project context.

`ProjectContext` lives in `ecosystem.project_context`.  This module keeps the
old `core.project_context` import path without making normal `core` imports pull
in the ecosystem layer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["ProjectContext"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module("ecosystem.project_context")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *__all__])
