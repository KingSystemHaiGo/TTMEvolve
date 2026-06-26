"""Scroll-chapter memory — Abidingenuity-inspired episodic memory for TTMEvolve.

The agent's session is split into rolling "chapters": each chapter holds a
verifiable span of the trajectory plus a structured summary that other
sessions can recall on demand.

Public surface:
- Chapter dataclass-like dict
- ScrollChapterMemory class — append-only chapter store
- recall(query, top_k) — keyword + verdict-aware recall for prompts
- render_chapter_card — UI-friendly chapter rendering
- build_scroll_context_block — fold selected chapters into agent context

Design notes (taken from Abidingenuity/memory.py):
- Chapters are append-only. Old chapters never mutate — only new ones are
  added. This keeps audit trails intact (relevant to Ima 之七's
  权威回溯 rule).
- Each chapter exposes token-bounded fields. The runtime never loads full
  raw trajectories into the prompt.
- Recall is deterministic (keyword + signal boost) so it is testable
  without an LLM.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


SCROLL_CHAPTER_VERSION = "scroll-chapter.v1"


def _chapter_id(session_id: str, index: int) -> str:
    return f"{session_id}::chapter-{index}"


def make_chapter(
    *,
    session_id: str,
    index: int,
    title: str,
    summary: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    outcome: str = "",
    tags: Optional[List[str]] = None,
    token_estimate: int = 0,
) -> Dict[str, Any]:
    """Create a chapter dict with a stable id and timestamp."""
    return {
        "version": SCROLL_CHAPTER_VERSION,
        "id": _chapter_id(session_id, index),
        "session_id": session_id,
        "index": index,
        "title": title,
        "summary": summary,
        "actions": list(actions or []),
        "outcome": outcome,
        "tags": list(tags or []),
        "created_at": time.perf_counter(),
        "token_estimate": max(0, int(token_estimate)),
    }


class ScrollChapterMemory:
    """Append-only store of chapters with keyword + signal recall."""

    def __init__(self, *, max_chapters: int = 200) -> None:
        if max_chapters <= 0:
            raise ValueError("max_chapters must be > 0")
        self._chapters: List[Dict[str, Any]] = []
        self.max_chapters = int(max_chapters)

    def append(self, chapter: Dict[str, Any]) -> None:
        if not isinstance(chapter, dict):
            raise ValueError("chapter must be a dict")
        chapter_id = chapter.get("id")
        chapter_title = chapter.get("title")
        if not isinstance(chapter_id, str) or not chapter_id:
            raise ValueError("chapter['id'] must be a non-empty string")
        if not isinstance(chapter_title, str) or not chapter_title:
            raise ValueError("chapter['title'] must be a non-empty string")
        self._chapters.append(chapter)
        if len(self._chapters) > self.max_chapters:
            # Trim oldest chapters once capacity is reached; never overwrite
            # the most recent `max_chapters // 2` chapters so context is stable.
            keep = max(self.max_chapters // 2, 1)
            self._chapters = self._chapters[-keep:]

    def list_chapters(self, *, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if session_id is None:
            return list(self._chapters)
        return [chapter for chapter in self._chapters if chapter.get("session_id") == session_id]

    def recall(
        self,
        query: str,
        *,
        top_k: int = 3,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the top_k chapters best matching the query.

        Scoring (deterministic, no LLM):
        - keyword overlap with title + summary + tags
        - small boost when outcome is "pass" or "success"
        - small boost when the most recent chapters are still in scope
        """
        tokens = _tokenize(query)
        if not tokens:
            return []
        scored: List[Dict[str, Any]] = []
        candidates = self.list_chapters(session_id=session_id)
        for index, chapter in enumerate(candidates):
            score = _score_chapter(chapter, tokens, index=index, total=len(candidates))
            if score > 0:
                scored.append({"chapter": chapter, "score": score})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return [item["chapter"] for item in scored[:top_k]]

    def render_chapter_card(self, chapter: Dict[str, Any]) -> str:
        """Render one chapter as a UI card."""
        lines = [f"# {chapter.get('title', 'Untitled')} ({chapter.get('id')})"]
        if chapter.get("summary"):
            lines.append(f"\n{chapter['summary']}")
        if chapter.get("actions"):
            lines.append("\n## 关键动作")
            for action in chapter["actions"][:5]:
                tool = action.get("tool") if isinstance(action, dict) else "?"
                outcome = action.get("outcome") if isinstance(action, dict) else ""
                lines.append(f"  - {tool} → {outcome}".rstrip())
        if chapter.get("outcome"):
            lines.append(f"\n## 结果\n{chapter['outcome']}")
        if chapter.get("tags"):
            lines.append(f"\n## 标签\n{' '.join('#' + tag for tag in chapter['tags'])}")
        return "\n".join(lines)

    def build_scroll_context_block(
        self,
        chapters: List[Dict[str, Any]],
        *,
        max_chars: int = 1200,
    ) -> str:
        """Fold the given chapters into a context block the agent can read."""
        if not chapters:
            return ""
        lines = ["\n[scroll_memory]\n"]
        for chapter in chapters:
            summary = chapter.get("summary") or ""
            outcome = chapter.get("outcome") or ""
            entry = (
                f"- {chapter.get('title', '?')} | "
                f"outcome={outcome[:60] or 'n/a'} | "
                f"{summary[:160]}"
            )
            lines.append(entry)
        block = "\n".join(lines)
        if len(block) > max_chars:
            block = block[: max_chars - 3] + "..."
        return block + "\n[/scroll_memory]\n"


def _is_cjk(ch: str) -> bool:
    """Cover the CJK Unified Ideographs blocks + extensions + compatibility."""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF          # CJK Unified Ideographs
        or 0x3400 <= code <= 0x4DBF       # CJK Extension A
        or 0x20000 <= code <= 0x2A6DF     # CJK Extension B
        or 0x2A700 <= code <= 0x2B73F     # CJK Extension C
        or 0x2B740 <= code <= 0x2B81F     # CJK Extension D
        or 0xF900 <= code <= 0xFAFF       # CJK Compatibility Ideographs
        or 0x2F800 <= code <= 0x2FA1F     # CJK Compatibility Supplement
    )


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    # Each CJK ideograph becomes its own 1-char token; ASCII runs become
    # whole-word tokens. This is more inclusive than the old "一".."鿿"
    # range and covers the common Extension A/B blocks.
    out: List[str] = []
    buffer: List[str] = []
    for ch in text.lower():
        if _is_cjk(ch):
            if buffer:
                out.append("".join(buffer))
                buffer = []
            out.append(ch)
        elif ch.isalnum():
            buffer.append(ch)
        else:
            if buffer:
                out.append("".join(buffer))
                buffer = []
    if buffer:
        out.append("".join(buffer))
    return out


def _score_chapter(
    chapter: Dict[str, Any],
    query_tokens: List[str],
    *,
    index: int,
    total: int,
) -> float:
    haystacks = [chapter.get("title", ""), chapter.get("summary", "")]
    haystacks.extend(chapter.get("tags") or [])
    chapter_tokens = set()
    for haystack in haystacks:
        chapter_tokens.update(_tokenize(str(haystack)))
    if not chapter_tokens:
        return 0.0
    overlap = sum(1 for token in query_tokens if token in chapter_tokens)
    if overlap == 0:
        return 0.0
    score = float(overlap)
    outcome = str(chapter.get("outcome") or "").lower()
    if any(token in outcome for token in ("pass", "success", "done")):
        score += 0.5
    if any(token in outcome for token in ("fail", "error", "broken")):
        score -= 0.2
    # Recency boost: more recent chapters get a tiny nudge so the agent
    # prefers the latest experience over an ancient one.
    recency = (index + 1) / max(total, 1)
    score += recency * 0.1
    return score


def fingerprint_chapter(chapter: Dict[str, Any]) -> str:
    """Stable fingerprint for de-duplication.

    Includes actions and tags so chapters that differ only in those fields
    get distinct fingerprints.
    """
    import json as _json
    payload = _json.dumps(
        {
            "id": chapter.get("id"),
            "title": chapter.get("title"),
            "summary": chapter.get("summary"),
            "actions": chapter.get("actions") or [],
            "tags": chapter.get("tags") or [],
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]