"""
llm/thought_record.py - structured thought record (Phase R1).

The LLM's free-text ``think()`` output is optionally parsed into
a structured record. The record carries:

  - plan_step: the current plan step id (e.g. "step-3")
  - observation_summary: short human summary of the last
    observation (e.g. "project_status returned the same dict")
  - hypothesis: the LLM's current hypothesis
  - expected_outcome: what the next action should produce
  - confidence: 0.0 - 1.0
  - decision: short statement of the chosen path

The parser is **lenient**. Free text (the existing format) parses
to ``None`` — the record is opt-in. The LLM does not have to
produce JSON; the schema is asked-for via the system prompt when
``thought_chain.strict=true`` but old responses still work.

The control loop (``core/control_loop.py``) reads the record
when present and uses ``confidence`` as a softer signal than
``observation.ok``. The evidence bundle surfaces the latest
record so the operator can see "what the agent is thinking."

The default flag is ``thought_chain.strict=false`` so this is
purely additive. No LLM provider change is required.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


THOUGHT_RECORD_VERSION = "thought-record.v1"


@dataclass
class ThoughtRecord:
    """Structured thought record parsed from LLM output."""

    schema_version: str = THOUGHT_RECORD_VERSION
    plan_step: str = ""
    observation_summary: str = ""
    hypothesis: str = ""
    expected_outcome: str = ""
    confidence: float = 0.0
    decision: str = ""
    raw_text: str = ""
    parse_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def is_empty(self) -> bool:
        return not (
            self.plan_step
            or self.observation_summary
            or self.hypothesis
            or self.expected_outcome
            or self.decision
        )


# A "looks like JSON object" sniff. We do not try to be clever;
# we just look for a leading ``{`` and a trailing ``}``.
_JSON_OBJECT_RE = re.compile(r"^\s*\{.*\}\s*$", re.DOTALL)


def parse_thought_record(
    text: Any,
    *,
    enabled: bool = True,
) -> Optional[ThoughtRecord]:
    """Lenient parser. Returns ``None`` if the input does not look
    like a structured record, or if ``enabled`` is False.

    Accepted shapes (in order of preference):

    1. ``{...}`` JSON object with the canonical fields.
    2. ``{...}`` JSON object with extra fields — extras are
       preserved in ``raw_text`` and ignored otherwise.
    3. Plain text — returns a record with ``raw_text`` set and
       nothing else. The control loop and evidence bundle both
       handle this case (no fields, no signal).
    4. ``None`` / non-string — returns ``None``.
    """
    if not enabled:
        return None
    if text is None:
        return None
    if not isinstance(text, str):
        return None
    raw = text
    if not raw.strip():
        return None
    rec = ThoughtRecord(raw_text=raw)
    if not _JSON_OBJECT_RE.match(raw):
        return rec
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        rec.parse_warnings.append("json_parse_failed")
        return rec
    if not isinstance(obj, dict):
        rec.parse_warnings.append("not_an_object")
        return rec
    # Map canonical fields. Unknown fields are ignored; missing
    # fields are kept at the default empty value.
    for src_key, dst_key in (
        ("plan_step", "plan_step"),
        ("observation_summary", "observation_summary"),
        ("hypothesis", "hypothesis"),
        ("expected_outcome", "expected_outcome"),
        ("confidence", "confidence"),
        ("decision", "decision"),
    ):
        if src_key in obj:
            value = obj[src_key]
            if dst_key == "confidence":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    rec.parse_warnings.append(f"confidence_not_float:{value!r}")
                    continue
                if not 0.0 <= value <= 1.0:
                    rec.parse_warnings.append(f"confidence_out_of_range:{value}")
                    value = max(0.0, min(1.0, value))
            elif not isinstance(value, str):
                rec.parse_warnings.append(f"{src_key}_not_string:{type(value).__name__}")
                value = str(value)
            setattr(rec, dst_key, value)
    return rec
