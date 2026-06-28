"""
memory/bayes.py - Bayesian posterior + Occam scoring for memory usefulness.

This module is additive. Visibility promotion/demotion is still decided by
``memory.shared_outcome.review_shared_memory_outcome()``. The posterior here
is a *ranking* signal that can recommend review, watch, or demotion, but
never directly sets ``visibility``.

Design references:
  - ADR-0004: update rules and Occam formula.
  - Beta-Bernoulli conjugate prior: posterior in [0, 1], monotone in evidence.
  - MemoryBank / forgetting curves: soft-delete only, no hard purge.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Update table (mirrors ADR-0004 Section 2.3 / Section 4.2)
# ---------------------------------------------------------------------------

# Each entry maps an evidence kind to (alpha_delta, beta_delta).
# Values are conservative defaults; the caller can override by passing
# custom deltas to ``BayesianScorer.update``.
_UPDATE_TABLE: Dict[str, Dict[str, float]] = {
    "retrieved_success":          {"alpha": 1.0, "beta": 0.0},
    "retrieved_failure":          {"alpha": 0.0, "beta": 1.5},
    "verified_positive_shared":   {"alpha": 2.0, "beta": 0.0},
    "regression":                 {"alpha": 0.0, "beta": 3.0},
    "misleading":                 {"alpha": 0.0, "beta": 2.0},
    "stale":                      {"alpha": 0.0, "beta": 1.0},
    "conflict":                   {"alpha": 0.0, "beta": 2.0},
}


# ---------------------------------------------------------------------------
# BayesianState
# ---------------------------------------------------------------------------

@dataclass
class BayesianState:
    """Beta-Bernoulli state for memory usefulness.

    posterior = alpha / (alpha + beta) ∈ [0, 1].
    """
    alpha: float = 1.0
    beta: float = 1.0
    occurrences: int = 0
    last_update: float = 0.0

    @property
    def posterior(self) -> float:
        total = self.alpha + self.beta
        if total <= 0.0:
            return 0.5
        return self.alpha / total

    @property
    def variance(self) -> float:
        a, b = self.alpha, self.beta
        total = a + b
        if total <= 0.0:
            return 0.0
        return (a * b) / ((total ** 2) * (total + 1.0))

    def update_alpha(self, delta: float) -> None:
        self.alpha = max(0.0, self.alpha + float(delta))
        self._touch()

    def update_beta(self, delta: float) -> None:
        self.beta = max(0.0, self.beta + float(delta))
        self._touch()

    def _touch(self) -> None:
        self.occurrences += 1
        self.last_update = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "occurrences": self.occurrences,
            "last_update": self.last_update,
            "posterior": self.posterior,
        }


# ---------------------------------------------------------------------------
# BayesianScorer
# ---------------------------------------------------------------------------

class BayesianScorer:
    """Apply evidence updates and prune decisions to a BayesianState."""

    @staticmethod
    def update(state: BayesianState, evidence_kind: str, *, deltas: Dict[str, float] = None) -> None:
        """Apply the evidence rule.

        Raises ``ValueError`` for unknown evidence kinds unless ``deltas``
        are provided explicitly.
        """
        rule = _UPDATE_TABLE.get(evidence_kind)
        if rule is None and not deltas:
            raise ValueError(
                f"Unknown evidence kind: {evidence_kind!r}. "
                f"Allowed: {sorted(_UPDATE_TABLE)} or pass deltas=."
            )
        if deltas:
            rule = {"alpha": float(deltas.get("alpha", 0.0)), "beta": float(deltas.get("beta", 0.0))}
        if rule["alpha"]:
            state.update_alpha(rule["alpha"])
        if rule["beta"]:
            state.update_beta(rule["beta"])

    @staticmethod
    def should_prune(
        state: BayesianState,
        *,
        threshold: float = 0.15,
        min_occurrences: int = 3,
    ) -> bool:
        """Soft-delete gate.

        A node is prune-eligible when *all* of:
          - at least one evidence event has arrived (hard floor;
            protects against a misconfigured ``min_occurrences=0``)
          - at least ``min_occurrences`` evidence events have arrived
          - posterior strictly below ``threshold``
        """
        if state.occurrences < 1:
            return False
        if state.occurrences < max(1, int(min_occurrences)):
            return False
        return state.posterior < float(threshold)


# ---------------------------------------------------------------------------
# Occam score (ADR-0004 Section 3.4)
# ---------------------------------------------------------------------------

def occam_score(
    summary_tokens: int,
    evidence_count: int,
    *,
    lambda_complexity: float = 0.08,
    evidence_cap: float = 0.15,
) -> float:
    """Bounded length penalty + capped evidence bonus.

    ``summary_tokens`` is the length of the summary in approximate tokens
    (caller computes; for memory content use ``len(content) // 4``).
    ``evidence_count`` is the number of evidence events that touched this
    memory.

    The length penalty is ``lambda_complexity * log1p(tokens)`` so it grows
    sub-linearly and never collapses a long but useful memory to zero.
    The evidence bonus is capped at ``evidence_cap`` (default 0.15) so a
    high-evidence record gets a small boost, not an unbounded one.
    """
    base = max(0.0, 1.0 - float(lambda_complexity) * math.log1p(max(int(summary_tokens), 1)))
    bonus = min(float(evidence_cap), 0.03 * max(int(evidence_count), 0))
    return base + bonus
