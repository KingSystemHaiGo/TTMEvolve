"""Managed background learning job queue.

The queue owns scheduling, cancellation state, retry policy, and compact job
snapshots. The agent still owns the actual learning pipeline and public layer
events through callbacks.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


LearningProcessor = Callable[[str, str, Dict[str, Any]], Dict[str, Any]]
TransitionCallback = Callable[[str, str, Dict[str, Any]], None]


@dataclass(frozen=True)
class LearningJobRequest:
    session_id: str
    task: str
    result: Dict[str, Any]
    correlation_id: str
    sink: Optional[Callable[[Dict[str, Any]], None]] = None


class LearningJobQueue:
    """Small managed worker queue for reflection/learning jobs."""

    def __init__(
        self,
        *,
        processor: LearningProcessor,
        on_transition: Optional[TransitionCallback] = None,
        max_attempts: int = 1,
        retry_delay_seconds: float = 0.0,
        worker_idle_timeout_seconds: float = 5.0,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.processor = processor
        self.on_transition = on_transition
        self.max_attempts = max(1, int(max_attempts or 1))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds or 0.0))
        self.worker_idle_timeout_seconds = max(0.05, float(worker_idle_timeout_seconds or 5.0))
        self.time_fn = time_fn
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._requests: Dict[str, LearningJobRequest] = {}
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._lock = threading.RLock()
        self._worker: Optional[threading.Thread] = None

    def submit(
        self,
        request: LearningJobRequest,
        *,
        eligible: bool,
        async_enabled: bool,
    ) -> Dict[str, Any]:
        now = self.time_fn()
        job = {
            "session_id": request.session_id,
            "status": "queued" if eligible else "skipped",
            "eligible": bool(eligible),
            "async": bool(async_enabled and eligible),
            "queued_at": now,
            "correlation_id": request.correlation_id,
            "sink": request.sink,
            "started_at": None,
            "finished_at": None,
            "elapsed_ms": 0,
            "error": "",
            "attempts": 0,
            "max_attempts": self.max_attempts,
            "retryable": False,
            "cancel_requested": False,
            "cancelled_at": None,
            "last_transition": "queued" if eligible else "skipped",
            "policy": self.policy(async_enabled=bool(async_enabled and eligible)),
        }
        with self._lock:
            self._jobs[request.session_id] = dict(job)
            self._requests[request.session_id] = request
            if eligible and async_enabled:
                self._queue.put(request.session_id)
                self._ensure_worker_locked()
        self._notify("queued" if eligible else "skipped", dict(job))

        if eligible and not async_enabled:
            self._run_job(request.session_id)
        return self.get(request.session_id)

    def get(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return {"session_id": session_id, "status": "missing"}
            return self._public_job(job)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._public_job(job) for job in self._jobs.values()]

    def cancel(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            job = dict(self._jobs.get(session_id) or {})
            if not job:
                return {"session_id": session_id, "status": "missing", "cancelled": False}
            status = str(job.get("status") or "")
            if status in {"done", "skipped", "error", "cancelled", "canceled"}:
                return {**self._public_job(job), "cancelled": False, "reason": "job_not_active"}
            now = self.time_fn()
            job["cancel_requested"] = True
            job["cancelled_at"] = now
            if status == "queued":
                job.update({
                    "status": "cancelled",
                    "finished_at": now,
                    "last_transition": "cancelled",
                    "retryable": self._can_retry(job),
                })
                self._jobs[session_id] = job
                notify = "cancelled"
            else:
                job["last_transition"] = "cancel_requested"
                self._jobs[session_id] = job
                notify = "cancel_requested"
        self._notify(notify, job)
        return {**self.get(session_id), "cancelled": True}

    def retry(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            job = dict(self._jobs.get(session_id) or {})
            request = self._requests.get(session_id)
            if not job or request is None:
                return {"session_id": session_id, "status": "missing", "retried": False}
            if str(job.get("status")) not in {"error", "cancelled", "canceled"}:
                return {
                    **self._public_job(job),
                    "retried": False,
                    "reason": "job_not_retryable_in_current_status",
                }
            if not self._can_retry(job):
                return {**self._public_job(job), "retried": False, "reason": "max_attempts_reached"}
            now = self.time_fn()
            job.update({
                "status": "queued",
                "queued_at": now,
                "finished_at": None,
                "elapsed_ms": 0,
                "error": "",
                "cancel_requested": False,
                "cancelled_at": None,
                "retryable": False,
                "last_transition": "retry_queued",
            })
            self._jobs[session_id] = job
            self._queue.put(session_id)
            self._ensure_worker_locked()
        self._notify("retry_queued", job)
        return {**self.get(session_id), "retried": True}

    def summary(self) -> Dict[str, Any]:
        jobs = self.list_jobs()
        status_counts: Dict[str, int] = {}
        for job in jobs:
            status = str(job.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "version": "learning-job-queue.v1",
            "status": "ready",
            "job_count": len(jobs),
            "status_counts": status_counts,
            "queued_count": status_counts.get("queued", 0),
            "running_count": status_counts.get("running", 0),
            "active_count": status_counts.get("queued", 0) + status_counts.get("running", 0),
            "policy": self.policy(async_enabled=True),
        }

    def policy(self, *, async_enabled: bool) -> Dict[str, Any]:
        return {
            "managed": True,
            "mode": "async_worker_queue" if async_enabled else "inline",
            "max_attempts": self.max_attempts,
            "retry_delay_seconds": self.retry_delay_seconds,
            "worker_idle_timeout_seconds": self.worker_idle_timeout_seconds,
            "cancellation": "cooperative_status_gate",
            "truthfulness_rule": (
                "queued jobs can be cancelled before start; running jobs only observe "
                "cancellation at learning step boundaries"
            ),
        }

    def _ensure_worker_locked(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="ttmevolve-learning-worker",
            daemon=True,
        )
        self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            try:
                session_id = self._queue.get(timeout=self.worker_idle_timeout_seconds)
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._worker = None
                        return
                continue
            try:
                self._run_job(session_id)
            finally:
                self._queue.task_done()

    def _run_job(self, session_id: str) -> None:
        request: Optional[LearningJobRequest]
        with self._lock:
            job = dict(self._jobs.get(session_id) or {})
            request = self._requests.get(session_id)
            if not job or request is None or job.get("status") != "queued":
                return
            if job.get("cancel_requested"):
                self._cancel_locked(session_id, job)
                transition_job = dict(self._jobs[session_id])
                transition = "cancelled"
            else:
                now = self.time_fn()
                attempts = int(job.get("attempts") or 0) + 1
                job.update({
                    "status": "running",
                    "attempts": attempts,
                    "started_at": now,
                    "finished_at": None,
                    "last_transition": "started",
                    "retryable": False,
                })
                self._jobs[session_id] = job
                transition_job = dict(job)
                transition = "started"
        self._notify(transition, transition_job)
        if transition == "cancelled" or request is None:
            return

        started_at = float(transition_job.get("started_at") or self.time_fn())
        try:
            summary = self.processor(session_id, request.task, request.result)
            if isinstance(summary, dict) and summary.get("error"):
                raise RuntimeError(str(summary.get("error")))
            finished_at = self.time_fn()
            elapsed_ms = (finished_at - started_at) * 1000
            with self._lock:
                job = dict(self._jobs.get(session_id) or transition_job)
                if job.get("cancel_requested"):
                    self._cancel_locked(session_id, job, finished_at=finished_at, elapsed_ms=elapsed_ms)
                    final_job = dict(self._jobs[session_id])
                    final_transition = "cancelled"
                else:
                    job.update({
                        "status": "done",
                        "finished_at": finished_at,
                        "elapsed_ms": elapsed_ms,
                        "error": "",
                        "summary": summary if isinstance(summary, dict) else {},
                        "shared_memory": (summary or {}).get("shared_memory", {}) if isinstance(summary, dict) else {},
                        "insight_count": (summary or {}).get("insight_count", 0) if isinstance(summary, dict) else 0,
                        "retryable": False,
                        "last_transition": "finished",
                    })
                    self._jobs[session_id] = job
                    final_job = dict(job)
                    final_transition = "finished"
            self._notify(final_transition, final_job)
        except Exception as exc:
            self._handle_failure(session_id, started_at, exc)

    def _handle_failure(self, session_id: str, started_at: float, exc: Exception) -> None:
        finished_at = self.time_fn()
        elapsed_ms = (finished_at - started_at) * 1000
        retry_job: Optional[Dict[str, Any]] = None
        failed_job: Optional[Dict[str, Any]] = None
        with self._lock:
            job = dict(self._jobs.get(session_id) or {"session_id": session_id})
            job.update({
                "finished_at": finished_at,
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
            })
            if job.get("cancel_requested"):
                self._cancel_locked(session_id, job, finished_at=finished_at, elapsed_ms=elapsed_ms)
                failed_job = dict(self._jobs[session_id])
                failed_transition = "cancelled"
            elif self._can_retry(job):
                job.update({
                    "status": "queued",
                    "queued_at": finished_at + self.retry_delay_seconds,
                    "last_transition": "retry_queued",
                    "retryable": True,
                })
                self._jobs[session_id] = job
                retry_job = dict(job)
                failed_transition = ""
            else:
                job.update({
                    "status": "error",
                    "last_transition": "failed",
                    "retryable": False,
                })
                self._jobs[session_id] = job
                failed_job = dict(job)
                failed_transition = "failed"

        if retry_job is not None:
            self._notify("retry_queued", retry_job)
            if self.retry_delay_seconds:
                time.sleep(self.retry_delay_seconds)
            with self._lock:
                self._queue.put(session_id)
                self._ensure_worker_locked()
            return
        if failed_job is not None:
            self._notify(failed_transition, failed_job)

    def _cancel_locked(
        self,
        session_id: str,
        job: Dict[str, Any],
        *,
        finished_at: Optional[float] = None,
        elapsed_ms: Optional[float] = None,
    ) -> None:
        now = self.time_fn() if finished_at is None else finished_at
        job.update({
            "status": "cancelled",
            "finished_at": now,
            "elapsed_ms": elapsed_ms if elapsed_ms is not None else job.get("elapsed_ms", 0),
            "cancel_requested": True,
            "cancelled_at": job.get("cancelled_at") or now,
            "last_transition": "cancelled",
            "retryable": self._can_retry(job),
        })
        self._jobs[session_id] = job

    def _can_retry(self, job: Dict[str, Any]) -> bool:
        return int(job.get("attempts") or 0) < int(job.get("max_attempts") or self.max_attempts)

    def _notify(self, transition: str, job: Dict[str, Any]) -> None:
        if callable(self.on_transition):
            try:
                self.on_transition(transition, str(job.get("session_id") or ""), dict(job))
            except Exception:
                pass

    def _public_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        public = dict(job)
        public.pop("sink", None)
        return public
