"""
llm/context_budget.py — Token-aware context budget manager.

Centralizes token counting, trajectory slicing, and graceful prompt truncation
so that all LLM providers share the same budget logic.
"""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BudgetStats:
    """Budget statistics for a single LLM call."""

    token_count: int
    n_ctx: int
    token_usage_ratio: float       # token_count / n_ctx
    context_window_ratio: float    # (token_count + reserve + max_tokens) / n_ctx
    compression_applied: bool = False
    dropped_parts: int = 0
    truncated_chars: int = 0
    token_cache_hits: int = 0
    token_cache_misses: int = 0
    token_cache_size: int = 0
    agents_md_hits: int = 0
    cold_recall_hits: int = 0
    agents_md_ms: float = 0.0
    cold_recall_ms: float = 0.0
    context_build_ms: float = 0.0
    workspace_profile: str = "general"
    # Phase C: fragment-aware stats. Kept at default 0 for the legacy
    # ``fit_parts`` path so old callers see a stable shape.
    fragment_count: int = 0
    deferred_count: int = 0
    stubbed_count: int = 0
    graph_recall_hits: int = 0
    posterior_pruned_count: int = 0
    occam_pruned_count: int = 0
    deferred_ids: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_count": self.token_count,
            "n_ctx": self.n_ctx,
            "token_usage_ratio": self.token_usage_ratio,
            "context_window_ratio": self.context_window_ratio,
            "compression_applied": self.compression_applied,
            "dropped_parts": self.dropped_parts,
            "truncated_chars": self.truncated_chars,
            "token_cache_hits": self.token_cache_hits,
            "token_cache_misses": self.token_cache_misses,
            "token_cache_size": self.token_cache_size,
            "agents_md_hits": self.agents_md_hits,
            "cold_recall_hits": self.cold_recall_hits,
            "agents_md_ms": self.agents_md_ms,
            "cold_recall_ms": self.cold_recall_ms,
            "context_build_ms": self.context_build_ms,
            "workspace_profile": self.workspace_profile,
            "fragment_count": self.fragment_count,
            "deferred_count": self.deferred_count,
            "stubbed_count": self.stubbed_count,
            "graph_recall_hits": self.graph_recall_hits,
            "posterior_pruned_count": self.posterior_pruned_count,
            "occam_pruned_count": self.occam_pruned_count,
            "deferred_ids": list(self.deferred_ids),
        }


class ContextBudgetManager:
    """Enforce a token budget on prompts.

    Supports an optional tokenizer callable. If absent, falls back to a rough
    character estimate suitable for API providers where a local tokenizer is
    unavailable.
    """

    def __init__(
        self,
        n_ctx: int,
        reserve_tokens: int,
        tokenizer: Optional[Callable[[str], int]] = None,
    ):
        if n_ctx <= 0:
            raise ValueError("n_ctx must be positive")
        self.n_ctx = n_ctx
        self.reserve_tokens = max(0, reserve_tokens)
        self.tokenizer = tokenizer
        # Fallback heuristic tuned for mixed CJK/English text.
        self._fallback_ratio = 4
        self._token_cache: Dict[str, int] = {}
        self._token_cache_hits = 0
        self._token_cache_misses = 0

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def estimate_tokens(self, text: str) -> int:
        """Return token count estimate for ``text``."""
        if not text:
            return 0
        key = self._cache_key(text)
        cached = self._token_cache.get(key)
        if cached is not None:
            self._token_cache_hits += 1
            return cached
        self._token_cache_misses += 1
        result = self._estimate_tokens_uncached(text)
        # Only cache texts that are likely reused (system prompts, tools, etc.)
        if len(text) >= 100:
            self._token_cache[key] = result
        return result

    def cache_stats(self) -> Dict[str, int]:
        return {
            "token_cache_hits": self._token_cache_hits,
            "token_cache_misses": self._token_cache_misses,
            "token_cache_size": len(self._token_cache),
        }

    def _estimate_tokens_uncached(self, text: str) -> int:
        if self.tokenizer is not None:
            try:
                return self.tokenizer(text)
            except Exception:
                pass
        return max(1, len(text) // self._fallback_ratio)

    def _stats(
        self,
        token_count: int,
        max_tokens: int,
        *,
        compression_applied: bool = False,
        dropped_parts: int = 0,
        truncated_chars: int = 0,
    ) -> BudgetStats:
        used_with_reserve = token_count + self.reserve_tokens + max_tokens
        return BudgetStats(
            token_count=token_count,
            n_ctx=self.n_ctx,
            token_usage_ratio=round(token_count / self.n_ctx, 4),
            context_window_ratio=round(min(used_with_reserve / self.n_ctx, 1.0), 4),
            compression_applied=compression_applied,
            dropped_parts=dropped_parts,
            truncated_chars=truncated_chars,
            **self.cache_stats(),
        )

    def fit(
        self,
        system: str,
        user: str,
        max_tokens: int,
    ) -> Tuple[str, BudgetStats]:
        """Return ``user`` trimmed so that system + user + max_tokens fits budget.

        Trimming removes text from the *top* (oldest part) while preserving the
        bottom (most recent) content.
        """
        budget = self.n_ctx - self.reserve_tokens - max_tokens
        if budget <= 0:
            return "", self._stats(0, max_tokens)

        system_tokens = self.estimate_tokens(system)
        current_user = user
        while True:
            total = system_tokens + self.estimate_tokens(current_user)
            if total <= budget:
                break
            # Truncate from the top, preserving the tail.
            over = total - budget
            if self.tokenizer is not None:
                # With a real tokenizer drop roughly the excess token count.
                chars_to_drop = max(1, over)
            else:
                chars_to_drop = max(1, over * self._fallback_ratio)
            if len(current_user) <= chars_to_drop:
                current_user = ""
                break
            current_user = current_user[int(chars_to_drop):].lstrip()
            if not current_user:
                break
        return current_user, self._stats(
            system_tokens + self.estimate_tokens(current_user),
            max_tokens,
        )

    def fit_parts(
        self,
        system: str,
        parts: List[Tuple[str, int]],
        max_tokens: int,
    ) -> Tuple[str, BudgetStats]:
        """Fit multiple user text parts under budget, dropping lowest priority first.

        ``parts`` is a list of ``(text, priority)`` where higher priority means
        more important.  Parts are expected in descending priority order.
        The returned stats include ``system`` tokens as well.
        """
        budget = self.n_ctx - self.reserve_tokens - max_tokens
        if budget <= 0:
            return "", self._stats(0, max_tokens)

        system_tokens = self.estimate_tokens(system)
        budget -= system_tokens
        if budget <= 0:
            return "", self._stats(system_tokens, max_tokens)

        # Work on mutable copies grouped by priority.
        grouped: Dict[int, List[str]] = {}
        for text, priority in parts:
            grouped.setdefault(priority, []).append(text)

        priorities = sorted(grouped.keys(), reverse=True)
        active: List[str] = []
        for p in priorities:
            active.extend(grouped[p])

        dropped_parts = 0
        truncated_chars = 0
        budget_total = budget + system_tokens

        def active_tokens() -> int:
            return system_tokens + sum(self.estimate_tokens(t) for t in active)

        highest_priority = priorities[0] if priorities else 0
        while active_tokens() > budget_total and priorities and priorities[-1] < highest_priority:
            lowest = priorities[-1]
            if not grouped[lowest]:
                priorities.pop()
                continue
            # Drop oldest item in the lowest priority group.
            text = grouped[lowest].pop(0)
            if text in active:
                active.remove(text)
                dropped_parts += 1
            if not grouped[lowest]:
                priorities.pop()

        # If still over budget (e.g. single huge high-priority part), truncate.
        result = "\n\n".join(active)
        while system_tokens + self.estimate_tokens(result) > budget_total and len(result) > 0:
            over = system_tokens + self.estimate_tokens(result) - budget_total
            if self.tokenizer is not None:
                chars_to_drop = max(1, over)
            else:
                chars_to_drop = max(1, over * self._fallback_ratio)
            if len(result) <= chars_to_drop:
                truncated_chars += len(result)
                result = ""
                break
            truncated_chars += int(chars_to_drop)
            result = result[int(chars_to_drop):].lstrip()

        compression_applied = dropped_parts > 0 or truncated_chars > 0
        if compression_applied and result:
            marker = f"[context_compressed dropped_parts={dropped_parts} truncated_chars={truncated_chars}]"
            marked = f"{marker}\n\n{result}"
            if system_tokens + self.estimate_tokens(marked) <= budget_total:
                result = marked

        return result, self._stats(
            system_tokens + self.estimate_tokens(result),
            max_tokens,
            compression_applied=compression_applied,
            dropped_parts=dropped_parts,
            truncated_chars=truncated_chars,
        )

    # ------------------------------------------------------------------
    # Phase C: fragment-based fitting
    # ------------------------------------------------------------------

    def fit_fragments(
        self,
        system: str,
        fragments: List["PromptFragment"],
        max_tokens: int,
    ) -> Tuple[str, BudgetStats]:
        """Fit fragment-based prompts under a token budget.

        Mirrors ``fit_parts`` but operates on ``PromptFragment`` objects
        so callers can preserve ``full_ref`` for later expansion. When
        a fragment does not fit, the loader first attempts a stub; if
        the stub still does not fit, the fragment's ``full_ref`` is
        added to the deferred list and the fragment is dropped.

        The returned ``BudgetStats`` carries the Phase C fields
        (``fragment_count``, ``deferred_count``, ``stubbed_count``,
        ``graph_recall_hits``, ``posterior_pruned_count``,
        ``occam_pruned_count``, ``deferred_ids``).
        """
        # Local import keeps ``llm.context_budget`` independent of
        # ``llm.prompt_loader`` at module load time.
        from llm.prompt_loader import PromptFragment, PromptLoader

        budget = self.n_ctx - self.reserve_tokens - max_tokens
        if budget <= 0:
            return "", self._stats(0, max_tokens)
        system_tokens = self.estimate_tokens(system)
        budget -= system_tokens
        if budget <= 0:
            return "", self._stats(system_tokens, max_tokens)

        # Group fragments by priority (descending). Within the same
        # priority, the order in the input list is preserved.
        priority_order = sorted({f.priority for f in fragments}, reverse=True)
        active: List[PromptFragment] = list(fragments)
        deferred: List[str] = []
        stubbed: List[str] = []
        dropped = 0
        truncated_chars = 0

        def total_active_tokens() -> int:
            return system_tokens + sum(
                self.estimate_tokens(f.content) for f in active
            )

        # Walk priority groups from lowest up. Each time the budget is
        # violated, drop the *first* fragment at the lowest priority,
        # stub it if possible, else drop entirely and record the
        # ``full_ref`` in the deferred list.
        while total_active_tokens() > budget and priority_order:
            lowest = priority_order[-1]
            for f in list(active):
                if f.priority == lowest:
                    active.remove(f)
                    if f.full_ref:
                        # Stub first
                        stub = PromptLoader._stub_text(f.content)
                        if stub and stub != f.content:
                            stub_frag = PromptFragment(
                                id=f.id + "-stub",
                                role=f.role,
                                content=stub,
                                priority=f.priority,
                                full_ref=f.full_ref,
                                stub=True,
                                source=f.source,
                                meta=dict(f.meta),
                            )
                            new_total = total_active_tokens() + self.estimate_tokens(stub)
                            if new_total <= budget:
                                active.append(stub_frag)
                                stubbed.append(f.full_ref)
                                break
                        # Stub didn't fit; defer the full ref
                        deferred.append(f.full_ref)
                    dropped += 1
                    break
            if not any(f.priority == lowest for f in active):
                priority_order.pop()

        # If still over budget (e.g. a single huge priority-10 fragment),
        # truncate the joined result from the top.
        # Sort active fragments by priority descending so the output
        # places task + plan + policy before trajectory (priority 1-3).
        active_sorted = sorted(active, key=lambda f: f.priority, reverse=True)
        result_parts = [f.content for f in active_sorted]
        result = "\n\n".join(result_parts)
        while system_tokens + self.estimate_tokens(result) > budget and len(result) > 0:
            over = system_tokens + self.estimate_tokens(result) - budget
            chars_to_drop = max(1, over * self._fallback_ratio) if self.tokenizer is None else max(1, over)
            if len(result) <= chars_to_drop:
                truncated_chars += len(result)
                result = ""
                break
            truncated_chars += int(chars_to_drop)
            result = result[int(chars_to_drop):].lstrip()

        compression_applied = (dropped + stubbed.__len__() + truncated_chars) > 0
        if compression_applied and result:
            marker = (
                f"[context_compressed dropped={dropped} "
                f"stubbed={len(stubbed)} deferred={len(deferred)} "
                f"truncated_chars={truncated_chars}]"
            )
            marked = f"{marker}\n\n{result}"
            if system_tokens + self.estimate_tokens(marked) <= budget:
                result = marked

        # Counters
        graph_recall_hits = sum(
            1 for f in fragments
            if f.meta.get("source") == "graph_recall"
        )
        stats = self._stats(
            system_tokens + self.estimate_tokens(result),
            max_tokens,
            compression_applied=compression_applied,
            dropped_parts=dropped,
            truncated_chars=truncated_chars,
        )
        # Phase C extra fields via replace (BudgetStats is frozen)
        from dataclasses import replace
        stats = replace(
            stats,
            fragment_count=len(fragments),
            deferred_count=len(deferred),
            stubbed_count=len(stubbed),
            graph_recall_hits=graph_recall_hits,
            deferred_ids=list(deferred),
        )
        return result, stats

    def slice_trajectory(
        self,
        trajectory: List[Dict[str, Any]],
        max_steps: int = 6,
        max_chars_per_step: int = 200,
        preserve_important: bool = True,
        max_important_steps: int = 2,
    ) -> str:
        """Render the most recent ``max_steps`` steps as a compact string."""
        if not trajectory:
            return ""

        steps = trajectory[-max_steps:] if len(trajectory) > max_steps else list(trajectory)
        if preserve_important and len(trajectory) > max_steps and max_important_steps > 0:
            important: List[Dict[str, Any]] = []
            for step in trajectory[:-max_steps]:
                if _is_important_step(step):
                    important.append(step)
            steps = important[-max_important_steps:] + steps
        omitted = len(trajectory) - len(steps)
        lines: List[str] = []
        if omitted > 0:
            lines.append(f"[omitted {omitted} earlier low-importance steps]")

        for step in steps:
            iteration = step.get("iteration", "?")
            thought = str(step.get("thought", ""))[:max_chars_per_step]
            action = _pretty_short(step.get("action", {}), max_chars_per_step)
            observation = _pretty_short(step.get("observation", {}), max_chars_per_step)
            lines.append(
                f"Step {iteration}:\n"
                f"  思考：{thought}\n"
                f"  动作：{action}\n"
                f"  观察：{observation}"
            )
        return "\n\n".join(lines)


def _pretty_short(obj: Any, max_chars: int) -> str:
    text = str(obj)
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _is_important_step(step: Dict[str, Any]) -> bool:
    observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
    validation = step.get("plan_validation") if isinstance(step.get("plan_validation"), dict) else {}
    if observation.get("ok") is False:
        return True
    if observation.get("committed") is not None or observation.get("idempotency_key"):
        return True
    if validation.get("verdict") in {"warn", "fail"}:
        return True
    return False
