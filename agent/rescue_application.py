"""Helpers for applying expert rescue actions to ReAct state."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def append_direct_action_rescue_step(
    *,
    trajectory: List[Dict[str, Any]],
    action: Dict[str, Any],
    observation: Dict[str, Any],
    thought: Optional[str] = "",
    timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    """Append the stable trajectory entry for direct-action rescue."""
    step = {
        "iteration": len(trajectory),
        "timestamp": time.time() if timestamp is None else timestamp,
        "source": "expert",
        "thought": thought or "",
        "action": action,
        "observation": observation,
    }
    trajectory.append(step)
    return step
