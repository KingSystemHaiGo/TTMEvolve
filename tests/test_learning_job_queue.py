from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.learning_queue import LearningJobQueue, LearningJobRequest


def _request(session_id: str) -> LearningJobRequest:
    return LearningJobRequest(
        session_id=session_id,
        task="learn",
        result={"trajectory": [{"iteration": 1}, {"iteration": 2}], "output": "ok"},
        correlation_id=session_id,
    )


def _wait_for(queue: LearningJobQueue, session_id: str, status: str) -> dict:
    deadline = time.time() + 2
    while time.time() < deadline:
        job = queue.get(session_id)
        if job.get("status") == status:
            return job
        time.sleep(0.01)
    return queue.get(session_id)


def test_learning_job_queue_runs_async_and_reports_policy():
    transitions = []

    def processor(session_id, task, result):
        time.sleep(0.05)
        return {"insight_count": 2, "shared_memory": {"counts": {"archived": 2, "promoted": 1}}}

    queue = LearningJobQueue(
        processor=processor,
        on_transition=lambda transition, session_id, job: transitions.append(transition),
        worker_idle_timeout_seconds=0.1,
    )

    queued = queue.submit(_request("learn-async"), eligible=True, async_enabled=True)
    done = _wait_for(queue, "learn-async", "done")

    assert queued["status"] in {"queued", "running"}
    assert done["status"] == "done"
    assert done["attempts"] == 1
    assert done["insight_count"] == 2
    assert done["policy"]["managed"] is True
    assert "sink" not in done
    assert transitions[:2] == ["queued", "started"]
    assert transitions[-1] == "finished"


def test_learning_job_queue_cancels_queued_job_before_start():
    release = threading.Event()
    transitions = []

    def processor(session_id, task, result):
        release.wait(timeout=1)
        return {"insight_count": 1}

    queue = LearningJobQueue(
        processor=processor,
        on_transition=lambda transition, session_id, job: transitions.append((session_id, transition)),
        worker_idle_timeout_seconds=0.1,
    )

    queue.submit(_request("first"), eligible=True, async_enabled=True)
    queue.submit(_request("second"), eligible=True, async_enabled=True)
    cancelled = queue.cancel("second")
    release.set()
    first = _wait_for(queue, "first", "done")

    assert cancelled["cancelled"] is True
    assert cancelled["status"] == "cancelled"
    assert first["status"] == "done"
    assert ("second", "cancelled") in transitions


def test_learning_job_queue_retries_failed_attempt_then_finishes():
    transitions = []
    calls = {"count": 0}

    def processor(session_id, task, result):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary reflection failure")
        return {"insight_count": 1}

    queue = LearningJobQueue(
        processor=processor,
        on_transition=lambda transition, session_id, job: transitions.append(transition),
        max_attempts=2,
        retry_delay_seconds=0,
        worker_idle_timeout_seconds=0.1,
    )

    queue.submit(_request("retry"), eligible=True, async_enabled=True)
    done = _wait_for(queue, "retry", "done")

    assert done["status"] == "done"
    assert done["attempts"] == 2
    assert calls["count"] == 2
    assert "retry_queued" in transitions
    assert transitions[-1] == "finished"
