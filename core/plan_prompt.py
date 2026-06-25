"""Prompt helpers that ask the LLM to produce a structured plan (Plan First).

The output is consumed by `core.plan_format.normalize_plan` so the runtime
never has to deal with malformed LLM output.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


PLAN_GENERATION_PROMPT = """You are TTMEvolve's planner. Before taking any action, design a step-by-step plan.

TASK:
{task}

CONTEXT:
{context}

RUNTIME_HINTS:
{runtime_hints}

AVAILABLE TOOLS (use these exact tool names):
{tool_list}

Respond with JSON only, no prose. Use this schema:

{{
  "summary": "<one-line plan summary>",
  "assumptions": ["<assumption 1>", "..."],
  "steps": [
    {{
      "id": "step-1",
      "tool": "<tool name from the list above>",
      "params": {{ ... }},
      "intent": "<why this step matters>",
      "expected_evidence": ["<how to know it succeeded>", "..."],
      "depends_on": ["<other step ids>", "..."],
      "notes": "<optional caveats>"
    }}
  ]
}}

Rules:
- Keep plans small: 2-7 steps unless the task is genuinely long.
- Always include expected_evidence for every step.
- Use depends_on to express ordering when needed.
- If the task cannot be planned in advance, return an empty steps list with a summary that explains why.
- Only use tools from the AVAILABLE TOOLS list. If you need a tool that is not listed, write a note in `assumptions` instead.
"""


def build_plan_prompt(
    task: str,
    context: str = "",
    runtime_hints: Optional[Dict[str, Any]] = None,
    tool_list: Optional[List[str]] = None,
) -> str:
    hints = runtime_hints or {}
    hint_lines = [f"- {key}: {value}" for key, value in hints.items()]
    tools = tool_list or []
    if tools:
        rendered_tools = "\n".join(f"- {name}" for name in tools)
    else:
        rendered_tools = "- (no tools registered yet)"
    return PLAN_GENERATION_PROMPT.format(
        task=task.strip(),
        context=(context or "(no extra context)").strip(),
        runtime_hints="\n".join(hint_lines) or "- (no runtime hints)",
        tool_list=rendered_tools,
    )


def extract_plan_from_llm_text(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of an LLM response.

    Returns None if no JSON object can be parsed. The caller is responsible
    for passing the result through `core.plan_format.normalize_plan`.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for end in range(start, len(text)):
        char = text[end]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:end + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None