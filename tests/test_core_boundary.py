"""
Architecture boundary tests for core compatibility modules.
"""

from __future__ import annotations

import importlib
import sys


def _fresh_import(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_core_harness_compat_import_is_lazy():
    sys.modules.pop("cli.harness", None)

    module = _fresh_import("core.harness")

    assert "cli.harness" not in sys.modules
    assert module.Harness.__name__ == "Harness"
    assert "cli.harness" in sys.modules


def test_core_project_context_compat_import_is_lazy():
    sys.modules.pop("ecosystem.project_context", None)

    module = _fresh_import("core.project_context")

    assert "ecosystem.project_context" not in sys.modules
    assert module.ProjectContext.__name__ == "ProjectContext"
    assert "ecosystem.project_context" in sys.modules
