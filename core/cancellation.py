"""Cooperative task cancellation primitives."""

from __future__ import annotations


class TaskCancelled(Exception):
    """Raised when a running session is cooperatively cancelled."""

    def __init__(self, message: str = "Task cancelled by user"):
        super().__init__(message)
