"""
Backward-compatible access to the CLI harness.

`Harness` and `AgentSession` live in `cli.harness`.  This module keeps the old
`core.harness` import path without making normal `core` imports pull in the CLI
layer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["AgentSession", "Harness"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module("cli.harness")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *__all__])
