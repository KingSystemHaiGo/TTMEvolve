"""Subprocess driver for MultiAgentRunner.

Reads ``TTMEVOLVE_MULTI_AGENT_SPEC`` (JSON), runs the agents sequentially
with a fresh Python process, and prints the JSON-encoded result list on
stdout (one per line, the last line is the payload).

The driver bypasses the ``agent`` package's ``__init__.py`` (which eagerly
imports TapMakerAgent and friends) by loading ``multi_agent`` directly
from its file path. Only the cold memory + bridge + GoalLoop modules are
touched, keeping the subprocess boot small and reliable.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_multi_agent(project_root: Path):
    module_name = "_ttmevolve_multi_agent_runtime"
    spec = importlib.util.spec_from_file_location(
        module_name,
        project_root / "agent" / "multi_agent.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load agent/multi_agent.py")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can find the module in sys.modules.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    raw = os.environ.get("TTMEVOLVE_MULTI_AGENT_SPEC")
    if not raw:
        print(json.dumps({"error": "TTMEVOLVE_MULTI_AGENT_SPEC not set"}))
        return 1
    try:
        spec = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"invalid spec json: {exc}"}))
        return 1
    project_root = Path(spec.get("project_root") or _project_root())
    storage_path = Path(spec.get("storage_path") or project_root / ".multi_agent_store")
    artifacts_root_str = spec.get("artifacts_root")
    artifacts_root = Path(artifacts_root_str) if artifacts_root_str else None
    workspace_profile = str(spec.get("workspace_profile") or "coding")
    # Also import the agent package shallowly so submodule imports work,
    # but skip the heavy __init__ chain by stubbing it.
    sys.path.insert(0, str(project_root))
    try:
        import agent as _agent_pkg  # noqa: F401
    except Exception:
        # Fall back: register a stub so submodule imports succeed without
        # loading the heavy TapMakerAgent chain.
        import types

        pkg = types.ModuleType("agent")
        pkg.__path__ = [str(project_root / "agent")]
        sys.modules["agent"] = pkg
    multi_agent = _load_multi_agent(project_root)
    agents = [
        multi_agent.AgentSpec(
            agent_id=str(item.get("agent_id") or "default"),
            task=str(item.get("task") or ""),
            session_id=str(item.get("session_id") or item.get("agent_id") or "session"),
            shared_claim=item.get("shared_claim"),
            can_read_private_other=bool(item.get("can_read_private_other", False)),
        )
        for item in (spec.get("agents") or [])
    ]
    results = multi_agent.run_agents_threaded(
        project_root=project_root,
        storage_path=storage_path,
        artifacts_root=artifacts_root,
        agents=agents,
        workspace_profile=workspace_profile,
    )
    payload = {
        "results": [
            {
                "agent_id": r.agent_id,
                "task": r.task,
                "status": r.status,
                "output": r.output,
                "indexed": r.indexed,
                "conflicts": r.conflicts,
                "error": r.error,
            }
            for r in results
        ]
    }
    print(json.dumps(payload, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
