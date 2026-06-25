from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent


def _load_feedback(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "failure_type": "invalid_artifact", "path": str(path), "error": str(e)}


def summarize(feedback_dir: Path) -> Dict[str, Any]:
    files = sorted(feedback_dir.glob("llm-runtime-interview-*.json"))
    items: List[Dict[str, Any]] = [_load_feedback(path) | {"path": str(path)} for path in files]
    failures = Counter(
        "ok" if item.get("ok") else item.get("failure_type", "invalid_feedback_shape")
        for item in items
    )
    latest = items[-1] if items else None
    successful_feedback = [item for item in items if item.get("ok") and item.get("feedback")]
    latest_feedback = successful_feedback[-1]["feedback"] if successful_feedback else None
    latest_event_meta = None
    if latest and isinstance(latest.get("event"), dict):
        latest_event_meta = latest["event"].get("meta")
    return {
        "feedback_dir": str(feedback_dir),
        "total_runs": len(items),
        "counts": dict(failures),
        "latest_run": latest,
        "latest_event_meta": latest_event_meta,
        "latest_successful_feedback": latest_feedback,
    }


def main() -> int:
    feedback_dir = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "docs/llm-feedback")
    payload = summarize(feedback_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
