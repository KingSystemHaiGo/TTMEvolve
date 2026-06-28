"""
tests/test_memory_bayes.py - Bayesian posterior + Occam scoring tests.

These tests cover memory/bayes.py (BayesianState, BayesianScorer, occam_score).
They are intentionally written before the implementation.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.bayes import (  # noqa: E402
    BayesianScorer,
    BayesianState,
    occam_score,
)


# ---------------------------------------------------------------------------
# Posterior monotonicity
# ---------------------------------------------------------------------------

def test_bayes_posterior_is_alpha_over_sum():
    s = BayesianState(alpha=3.0, beta=1.0)
    assert abs(s.posterior - 0.75) < 1e-9


def test_bayes_posterior_starts_at_one_half_for_uninformed_prior():
    s = BayesianState()  # default alpha=beta=1
    assert abs(s.posterior - 0.5) < 1e-9


def test_bayes_posterior_monotonic_in_alpha_and_beta():
    s = BayesianState()
    p0 = s.posterior
    s.update_alpha(1.0)
    assert s.posterior > p0
    s.update_beta(1.0)
    # Net: +1 alpha, +1 beta: posterior should drop back near 0.5
    s2 = BayesianState(alpha=2.0, beta=2.0)
    assert abs(s2.posterior - 0.5) < 1e-9


def test_bayes_posterior_clamped_to_unit_interval():
    s = BayesianState(alpha=1.0, beta=1.0)
    s.update_alpha(1e9)
    assert 0.0 <= s.posterior <= 1.0
    s.update_beta(1e9)
    assert 0.0 <= s.posterior <= 1.0


# ---------------------------------------------------------------------------
# Scorer update rules (from ADR-0004 update table)
# ---------------------------------------------------------------------------

def test_scorer_positive_verified_task_lifts_alpha_by_one():
    s = BayesianState()
    BayesianScorer.update(s, "retrieved_success")
    assert s.alpha == 2.0
    assert s.occurrences == 1


def test_scorer_failed_task_pushes_beta_by_one_point_five():
    s = BayesianState()
    BayesianScorer.update(s, "retrieved_failure")
    assert abs(s.beta - 2.5) < 1e-9  # 1.0 prior + 1.5
    assert s.occurrences == 1


def test_scorer_verified_positive_shared_pushes_alpha_by_two():
    s = BayesianState()
    BayesianScorer.update(s, "verified_positive_shared")
    assert s.alpha == 3.0  # 1.0 + 2.0


def test_scorer_regression_pushes_beta_by_three():
    s = BayesianState()
    BayesianScorer.update(s, "regression")
    assert abs(s.beta - 4.0) < 1e-9  # 1.0 + 3.0


def test_scorer_misleading_pushes_beta_by_two():
    s = BayesianState()
    BayesianScorer.update(s, "misleading")
    assert abs(s.beta - 3.0) < 1e-9  # 1.0 + 2.0


def test_scorer_stale_pushes_beta_by_one():
    s = BayesianState()
    BayesianScorer.update(s, "stale")
    assert abs(s.beta - 2.0) < 1e-9  # 1.0 + 1.0


def test_scorer_conflict_pushes_both_involved_nodes():
    a = BayesianState()
    b = BayesianState()
    BayesianScorer.update(a, "conflict")
    BayesianScorer.update(b, "conflict")
    assert abs(a.beta - 3.0) < 1e-9
    assert abs(b.beta - 3.0) < 1e-9


def test_scorer_unknown_evidence_kind_raises():
    s = BayesianState()
    try:
        BayesianScorer.update(s, "unknown_kind")
    except ValueError:
        return
    raise AssertionError("scorer should reject unknown evidence kinds")


# ---------------------------------------------------------------------------
# Occam score (ADR-0004 formula)
# ---------------------------------------------------------------------------

def test_occam_score_short_wins_over_long_at_equal_posterior():
    short = occam_score(summary_tokens=10, evidence_count=0)
    long = occam_score(summary_tokens=400, evidence_count=0)
    assert short > long


def test_occam_score_evidence_bonus_caps_at_zero_point_one_five():
    cap = occam_score(summary_tokens=10, evidence_count=100)
    no_cap = occam_score(summary_tokens=10, evidence_count=0)
    # Difference should be the cap (0.15)
    assert abs((cap - no_cap) - 0.15) < 1e-9


def test_occam_score_length_penalty_uses_log1p():
    # penalty = lambda * log1p(tokens); lambda=0.08 default
    s = occam_score(summary_tokens=99, evidence_count=0, lambda_complexity=0.08)
    expected_penalty = 0.08 * math.log1p(99)
    expected = max(0.0, 1.0 - expected_penalty) + 0.0
    assert abs(s - expected) < 1e-9


def test_occam_score_floor_at_zero_for_extreme_lengths():
    s = occam_score(summary_tokens=10_000_000, evidence_count=0, lambda_complexity=1.0)
    # base component must be >= 0
    assert s >= 0.0


# ---------------------------------------------------------------------------
# Soft-delete decision (prune gate)
# ---------------------------------------------------------------------------

def test_prune_decision_requires_low_posterior_and_enough_occurrences():
    s = BayesianState(alpha=1.0, beta=1.0, occurrences=0)
    assert BayesianScorer.should_prune(s, threshold=0.15, min_occurrences=3) is False
    s.occurrences = 3
    # posterior is 0.5, above threshold
    assert BayesianScorer.should_prune(s, threshold=0.15, min_occurrences=3) is False
    # Push posterior way down
    s.alpha = 0.5
    s.beta = 50.0
    s.occurrences = 5
    assert BayesianScorer.should_prune(s, threshold=0.15, min_occurrences=3) is True


def test_prune_decision_never_fires_with_zero_occurrences():
    s = BayesianState(alpha=0.1, beta=100.0, occurrences=0)
    assert BayesianScorer.should_prune(s, threshold=0.5, min_occurrences=0) is False
