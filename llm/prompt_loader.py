"""
llm/prompt_loader.py - progressive prompt, context, and memory loader.

Phase C. Lives at the orchestration layer (``MemoryManager`` /
``ReActLoop``) so LLM provider classes stay thin.

Design references:
  - ADR-0007 (Progressive Prompt, Context, And Memory Loader)
  - The plan's Phase C exit gate: ``loader.enabled=false`` must keep
    existing prompt assembly byte-equivalent; ``loader.enabled=true``
    must show deferred/stubbed stats and keep task + plan + policy
    fragments at priority 10 even under a tight budget.

This module is intentionally deterministic. It never calls an LLM in
the hot path; the stub extractor is a one-pass summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from llm.context_budget import BudgetStats, ContextBudgetManager


FRAGMENT_ROLES = frozenset({
    "policy", "task", "plan", "project_rules", "tools",
    "memory", "trajectory", "advice",
})


@dataclass
class PromptFragment:
    id: str
    role: str
    content: str
    priority: int
    full_ref: str = ""
    stub: bool = False
    source: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def token_estimate(self, budget: ContextBudgetManager) -> int:
        if self.meta.get("_token_estimate") is not None:
            return int(self.meta["_token_estimate"])
        return budget.estimate_tokens(self.content)


@dataclass
class LoadedContext:
    text: str
    fragments: List[PromptFragment]
    deferred: List[str]
    budget_stats: BudgetStats
    graph_evidence: List[Dict[str, Any]] = field(default_factory=list)


# ADR-0007 priority table
PRIORITY_BY_ROLE: Dict[str, int] = {
    "policy": 10,
    "task": 10,
    "plan": 10,
    "project_rules": 8,
    "tools": 7,
    "memory": 6,
    "advice": 5,
    "trajectory": 3,
}


class PromptLoader:
    """Build, fit, and serialize fragment-based prompts.

    The loader is stateless apart from its dependencies. Callers
    construct one per call site (one per ``MemoryManager`` instance) and
    reuse it.
    """

    # Stub length is intentionally tiny: a one-line summary.
    _STUB_MAX_CHARS = 120

    def __init__(self, budget_manager: ContextBudgetManager):
        self.budget_manager = budget_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        system: str,
        task: str,
        workspace_profile: str,
        tools_description: str,
        trajectory_str: str,
        project_rules: str = "",
        cold_memory_hits: str = "",
        plan_step: str = "",
        advice: str = "",
        max_tokens: int = 512,
    ) -> LoadedContext:
        """Build and fit fragments. Returns the assembled context plus
        per-call stats. ``deferred`` lists fragment full_refs that the
        caller may want to expand later.
        """
        fragments = self.build_default_fragments(
            task=task,
            profile=workspace_profile,
            tools_description=tools_description,
            trajectory_str=trajectory_str,
            agents_context=project_rules,
            cold_context=cold_memory_hits,
            plan_step=plan_step,
            advice=advice,
        )
        text, stats = self.budget_manager.fit_fragments(
            system=system,
            fragments=fragments,
            max_tokens=max_tokens,
        )
        return LoadedContext(
            text=text,
            fragments=fragments,
            deferred=list(stats.deferred_ids),
            budget_stats=stats,
        )

    def build_default_fragments(
        self,
        *,
        task: str,
        profile: str,
        tools_description: str,
        trajectory_str: str,
        agents_context: str = "",
        cold_context: str = "",
        plan_step: str = "",
        advice: str = "",
    ) -> List[PromptFragment]:
        """Return a list of fragments honoring the ADR-0007 priority
        table. Each fragment carries a ``full_ref`` (where applicable)
        so the budget manager can stub and the caller can later expand.
        """
        out: List[PromptFragment] = []

        if profile:
            out.append(PromptFragment(
                id="policy-profile",
                role="policy",
                content=f"【Workspace Profile】{profile}",
                priority=PRIORITY_BY_ROLE["policy"],
                full_ref="policy-profile",
            ))

        if task:
            out.append(PromptFragment(
                id="task",
                role="task",
                content=task,
                priority=PRIORITY_BY_ROLE["task"],
                full_ref="task",
            ))

        if plan_step:
            out.append(PromptFragment(
                id="plan-step",
                role="plan",
                content=plan_step,
                priority=PRIORITY_BY_ROLE["plan"],
                full_ref="plan-step",
            ))

        if agents_context:
            out.append(PromptFragment(
                id="project-rules",
                role="project_rules",
                content=agents_context,
                priority=PRIORITY_BY_ROLE["project_rules"],
                full_ref="project-rules",
            ))

        if tools_description:
            out.append(PromptFragment(
                id="tools",
                role="tools",
                content=tools_description,
                priority=PRIORITY_BY_ROLE["tools"],
                full_ref="tools",
            ))

        if cold_context:
            out.append(PromptFragment(
                id="memory",
                role="memory",
                content=cold_context,
                priority=PRIORITY_BY_ROLE["memory"],
                full_ref="memory",
                meta={"source": "graph_recall"} if "graph" in cold_context.lower() else {"source": "flat_cold"},
            ))

        if advice:
            out.append(PromptFragment(
                id="advice",
                role="advice",
                content=advice,
                priority=PRIORITY_BY_ROLE["advice"],
                full_ref="advice",
            ))

        if trajectory_str:
            out.append(PromptFragment(
                id="trajectory",
                role="trajectory",
                content=trajectory_str,
                priority=PRIORITY_BY_ROLE["trajectory"],
                full_ref="trajectory",
            ))

        return out

    def expand_fragment(self, fragment_id: str) -> Optional[str]:
        """Return the full content for a deferred fragment id, or None.

        The default implementation has no source-of-truth; the loader
        relies on the caller to keep fragment ids in sync with whatever
        backing store they came from. This is the entry point the
        caller can override to plug in a real expansion.
        """
        return None

    def prune_low_confidence(
        self,
        fragments: List[PromptFragment],
        *,
        posterior_floor: float = 0.15,
        occam_floor: float = 0.0,
    ) -> List[PromptFragment]:
        """Drop memory fragments whose Bayesian posterior is below
        ``posterior_floor`` or whose Occam score is below ``occam_floor``.

        This is a pre-fit filter; the budget manager still enforces the
        token cap. Counters are exposed via ``BudgetStats`` so the
        caller can observe what was removed.
        """
        kept: List[PromptFragment] = []
        for f in fragments:
            if f.role != "memory":
                kept.append(f)
                continue
            posterior = f.meta.get("posterior")
            occam = f.meta.get("occam_score")
            if isinstance(posterior, (int, float)) and posterior < posterior_floor:
                continue
            if isinstance(occam, (int, float)) and occam < occam_floor:
                continue
            kept.append(f)
        return kept

    # ------------------------------------------------------------------
    # Internal: deterministic stub extractor
    # ------------------------------------------------------------------

    @staticmethod
    def _stub_text(content: str) -> str:
        """One-line deterministic summary used when the full fragment
        does not fit. The first non-empty line is kept and trimmed.
        """
        if not content:
            return ""
        first_line = next(
            (line.strip() for line in content.splitlines() if line.strip()),
            "",
        )
        if len(first_line) <= PromptLoader._STUB_MAX_CHARS:
            return first_line
        return first_line[: PromptLoader._STUB_MAX_CHARS - 1] + "…"
