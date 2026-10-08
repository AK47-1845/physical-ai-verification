"""Episode statistics tests: Wilson, Clopper-Pearson, rule of three."""

import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.episodes import (  # noqa: E402
    EpisodesError,
    clopper_pearson,
    episodes_needed,
    rule_of_three,
    verdict_for_claim,
    wilson,
)


def test_rule_of_three_exact():
    assert rule_of_three(20) == pytest.approx(0.15)
    assert rule_of_three(140) == pytest.approx(3.0 / 140)


def test_wilson_perfect_record_hand_value():
    # Hand-derived: lo = 1/(1+z^2/20), hi = 1.0 exactly.
    lo, hi = wilson(20, 20)
    assert lo == pytest.approx(0.8389, abs=1e-3)
    assert hi == pytest.approx(1.0, abs=1e-9)


def test_clopper_pearson_edges_closed_form():
    # k=n: lo = (a/2)^(1/n); k=0: hi = 1-(a/2)^(1/n).
    lo, hi = clopper_pearson(20, 20)
    assert lo == pytest.approx(0.025 ** 0.05, abs=1e-6)
    assert hi == 1.0
    lo0, hi0 = clopper_pearson(20, 0)
    assert lo0 == 0.0
    assert hi0 == pytest.approx(1.0 - 0.025 ** 0.05, abs=1e-6)


def test_clopper_pearson_interior_pinned():
    # Pinned against scipy.stats.beta.ppf reference (/tmp probe 2026-10-08).
    lo, hi = clopper_pearson(20, 14)
    assert lo == pytest.approx(0.4572, abs=1e-3)
    assert hi == pytest.approx(0.8811, abs=1e-3)


def test_wilson_interior_pinned():
    lo, hi = wilson(20, 14)
    assert lo == pytest.approx(0.4811, abs=1e-3)
    assert hi == pytest.approx(0.8545, abs=1e-3)


@pytest.mark.parametrize("n,k", [(20, 0), (20, 7), (20, 14), (20, 20), (140, 100), (5, 2)])
def test_intervals_contain_sample_rate(n, k):
    for fn in (wilson, clopper_pearson):
        lo, hi = fn(n, k)
        assert 0.0 <= lo <= k / n <= hi <= 1.0


def test_cp_wider_than_wilson():
    for n, k in [(20, 7), (20, 14), (50, 30)]:
        wlo, whi = wilson(n, k)
        clo, chi = clopper_pearson(n, k)
        assert (chi - clo) >= (whi - wlo) - 1e-9


def test_intervals_shrink_with_n():
    widths = [wilson(n, n // 2)[1] - wilson(n, n // 2)[0] for n in (20, 80, 320)]
    assert widths[0] > widths[1] > widths[2]


def test_episodes_needed_scale():
    assert episodes_needed(0.7, 0.05) == 323
    small = episodes_needed(0.7, 0.10)
    tight = episodes_needed(0.7, 0.05)
    assert tight > small >= 2
    assert episodes_needed(0.5, 0.05) >= episodes_needed(0.9, 0.05)


def test_verdict_insufficient_when_wide():
    out = verdict_for_claim(20, 14, tolerance=0.05)
    assert out["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert out["width"] > 0.05
    assert "safe" not in str(out).lower()


def test_verdict_sufficient_when_narrow():
    out = verdict_for_claim(2000, 1400, tolerance=0.05)
    assert out["verdict"] == "SUFFICIENT"


def test_verdict_zero_failures_reports_rule_of_three():
    out = verdict_for_claim(20, 0, tolerance=0.05)
    assert out["rule_of_three_hi"] == pytest.approx(0.15)
    full = verdict_for_claim(20, 20, tolerance=0.05)
    assert full["rule_of_three_failure_hi"] == pytest.approx(0.15)


@pytest.mark.parametrize("bad", [(0, 0), (20, 21), (20, -1), (True, 1), (20, True), ("20", 5)])
def test_refusals(bad):
    n, k = bad
    with pytest.raises(EpisodesError):
        wilson(n, k)
    with pytest.raises(EpisodesError):
        clopper_pearson(n, k)


def test_bad_alpha_and_tolerance_refused():
    with pytest.raises(EpisodesError):
        wilson(20, 10, alpha=0.03)
    with pytest.raises(EpisodesError):
        verdict_for_claim(20, 10, tolerance=0.0)
    with pytest.raises(EpisodesError):
        episodes_needed(0.5, 0.0)
