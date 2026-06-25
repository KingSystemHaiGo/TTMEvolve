"""Subagent spawning for parallel/sequential sub-tasks.

The host ReAct loop delegates a bounded sub-task to a fresh LLM call, collects
the final answer, and returns it as a normal tool observation. This is a
deliberately small implementation: it does NOT recursively call ReActLoop
(avoiding infinite recursion); instead, it acts as a "delegated generation"
helper, suitable for `codex-parallel` style subtasks like summarising a file
or drafting boilerplate.

The interface is async-friendly: callers can run multiple subagent calls in
parallel using a thread pool.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
from typing import Any, Callable, Dict, List, Optional


SUBAGENT_RESULT_VERSION = "subagent-result.v1"


def make_subagent_invocation(
    *,
    task: str,
    context: str = "",
    max_tokens: int = 800,
) -> Dict[str, Any]:
    """Build the prompt and metadata for a subagent invocation."""
    fingerprint = hashlib.sha256(f"{task}|{context}".encode("utf-8")).hexdigest()[:16]
    prompt = (
        "You are a focused subagent. Complete the following task and return only the "
        "final answer in plain text. Do not include tool calls or extra commentary.\n\n"
        f"TASK:\n{task.strip()}\n\n"
        f"CONTEXT:\n{context.strip() or '(no extra context)'}\n"
    )
    return {
        "version": SUBAGENT_RESULT_VERSION,
        "invocation_id": f"sa-{fingerprint}",
        "task": task,
        "context": context,
        "max_tokens": max_tokens,
        "prompt": prompt,
        "started_at": time.perf_counter(),
    }


def collect_subagent_result(
    invocation: Dict[str, Any],
    *,
    llm_generate: Callable[[str, int], Any],
) -> Dict[str, Any]:
    """Run a single subagent invocation synchronously."""
    try:
        response = llm_generate(invocation["prompt"], invocation.get("max_tokens", 800))
        text = getattr(response, "text", None) or str(response)
    except Exception as e:
        return _result(invocation, ok=False, text="", error=str(e))
    return _result(invocation, ok=True, text=text)


def run_subagents_parallel(
    invocations: List[Dict[str, Any]],
    *,
    llm_generate: Callable[[str, int], Any],
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """Run multiple subagent invocations in parallel.

    Order is preserved: results[i] corresponds to invocations[i].
    """
    if not invocations:
        return []
    worker_count = max(1, min(max_workers, len(invocations)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [
            pool.submit(collect_subagent_result, inv, llm_generate=llm_generate)
            for inv in invocations
        ]
        return [future.result() for future in futures]


def _result(invocation: Dict[str, Any], *, ok: bool, text: str, error: str = "") -> Dict[str, Any]:
    elapsed_ms = round((time.perf_counter() - invocation.get("started_at", time.perf_counter())) * 1000, 1)
    payload = {
        "version": SUBAGENT_RESULT_VERSION,
        "invocation_id": invocation.get("invocation_id"),
        "task": invocation.get("task"),
        "ok": ok,
        "text": text,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }
    return payload


def register_subagent_tool(tools: Any, llm_generate: Callable[[str, int], Any]) -> None:
    """Register the spawn_subagent tool on a ToolRegistry.

    The handler returns a single subagent result; for parallel fan-out, the
    ReAct loop calls `run_subagents_parallel` directly.
    """

    def handler(task: str = "", context: str = "", max_tokens: int = 800, **_: Any) -> Dict[str, Any]:
        invocation = make_subagent_invocation(task=task or "", context=context or "", max_tokens=max_tokens)
        result = collect_subagent_result(invocation, llm_generate=llm_generate)
        return {
            "ok": result.get("ok", False),
            "tool": "spawn_subagent",
            "invocation_id": result.get("invocation_id"),
            "task": result.get("task"),
            "text": result.get("text", ""),
            "elapsed_ms": result.get("elapsed_ms"),
            "error": result.get("error", ""),
            "idempotency_key": f"subagent:{result.get('invocation_id')}",
        }

    tools.register(
        name="spawn_subagent",
        description=(
            "Delegate a focused sub-task to a fresh LLM call. Use when the host loop needs "
            "a quick standalone answer (summarise this file, draft boilerplate, classify "
            "an item) without recursive reasoning. For batch fan-out, call "
            "spawn_subagent_batch instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Self-contained sub-task description."},
                "context": {"type": "string", "description": "Optional supporting context."},
                "max_tokens": {"type": "integer", "description": "Max tokens for the response."},
            },
            "required": ["task"],
        },
        handler=handler,
        source="builtin",
    )


def register_subagent_batch_tool(
    tools: Any,
    llm_generate: Callable[[str, int], Any],
) -> None:
    """Register spawn_subagent_batch for parallel fan-out."""

    def handler(tasks: Optional[List[Dict[str, Any]]] = None, **_: Any) -> Dict[str, Any]:
        items = tasks or []
        invocations = [
            make_subagent_invocation(
                task=str(item.get("task") or ""),
                context=str(item.get("context") or ""),
                max_tokens=int(item.get("max_tokens") or 800),
            )
            for item in items
            if isinstance(item, dict)
        ]
        results = run_subagents_parallel(invocations, llm_generate=llm_generate)
        return {
            "ok": all(result.get("ok") for result in results),
            "tool": "spawn_subagent_batch",
            "count": len(results),
            "results": results,
            "idempotency_key": f"subagent-batch:{hashlib.sha256(json.dumps([r['invocation_id'] for r in results], sort_keys=True).encode()).hexdigest()[:16]}",
        }

    tools.register(
        name="spawn_subagent_batch",
        description=(
            "Run multiple sub-tasks in parallel and collect their results. Each task is "
            "self-contained; the host loop does NOT recursively reason between them. "
            "Use this for fan-out work like summarising several files at once."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string"},
                            "context": {"type": "string"},
                            "max_tokens": {"type": "integer"},
                        },
                        "required": ["task"],
                    },
                }
            },
            "required": ["tasks"],
        },
        handler=handler,
        source="builtin",
    )