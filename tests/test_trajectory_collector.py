from __future__ import annotations

import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from learning.trajectory_collector import TrajectoryCollector


def test_trajectory_collector_recreates_storage_dir_before_append(tmp_path: Path):
    storage = tmp_path / "storage" / "trajectories"
    collector = TrajectoryCollector(storage)
    shutil.rmtree(storage)

    collector.append("s1", [{"iteration": 0, "observation": {"ok": True}}])

    assert storage.exists()
    assert collector.read("s1")[0]["iteration"] == 0
