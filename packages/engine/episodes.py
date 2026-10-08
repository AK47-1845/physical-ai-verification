"""Episode statistics (P0-1): honest intervals for release verdicts.

Wilson score interval, Clopper-Pearson exact interval, rule of three,
and an episodes-needed calculator. Stdlib only: the Clopper-Pearson
beta quantiles use a continued-fraction incomplete beta (Numerical
Recipes betacf), verified against closed forms at the edges
(k=0, k=n) and scipy's beta.ppf in the interior.

Fail-closed contract: wide interval vs the claim tolerance =>
INSUFFICIENT_EVIDENCE. This module never says "safe".
"""

import math

from engine import InputError


class EpisodesError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


_Z = {0.10: 1.6448536269514729, 0.05: 1.959963984540054, 0.01: 2.5758293035489004}


def _check_counts(n, k) -> None:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise EpisodesError(f"n: positive int required, got {n!r}")
    if isinstance(k, bool) or not isinstance(k, int) or not 0 <= k <= n:
        raise EpisodesError(f"k: int in 0..n required, got {k!r} (n={n})")


def _check_alpha(alpha: float) -> float:
    if isinstance(alpha, bool) or alpha not in _Z:
        raise EpisodesError(f"alpha: one of {sorted(_Z)}, got {alpha!r}")
    return _Z[alpha]


def wilson(n: int, k: int, alpha: float = 0.05) -> list:
    """Wilson score interval for a binomial rate. Returns [lo, hi]."""
    _check_counts(n, k)
    z = _check_alpha(alpha)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return [max(0.0, center - half), min(1.0, center + half)]


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Numerical Recipes)."""
    max_iter, eps, tiny = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta Ix(a, b). a, b positive ints here."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    if x < (a + 1.0) / (a + b + 2.0):
        front = math.exp(a * math.log(x) + b * math.log1p(-x) - log_beta) / a
        return front * _betacf(a, b, x)
    front = math.exp(b * math.log1p(-x) + a * math.log(x) - log_beta) / b
    return 1.0 - front * _betacf(b, a, 1.0 - x)


def _beta_ppf(p: float, a: int, b: int) -> float:
    """Beta quantile via bisection. p in (0, 1)."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _betai(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def clopper_pearson(n: int, k: int, alpha: float = 0.05) -> list:
    """Clopper-Pearson exact interval. Returns [lo, hi]."""
    _check_counts(n, k)
    if isinstance(alpha, bool) or alpha not in _Z:
        raise EpisodesError(f"alpha: one of {sorted(_Z)}, got {alpha!r}")
    lo = 0.0 if k == 0 else _beta_ppf(alpha / 2.0, k, n - k + 1)
    hi = 1.0 if k == n else _beta_ppf(1.0 - alpha / 2.0, k + 1, n - k)
    return [lo, hi]


def rule_of_three(n: int) -> float:
    """95% upper bound on the failure rate after n episodes, zero failures."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise EpisodesError(f"n: positive int required, got {n!r}")
    return 3.0 / n


def episodes_needed(p: float, half_width: float, alpha: float = 0.05) -> int:
    """Normal-approx episodes for a target Wilson half-width at rate p."""
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0:
        raise EpisodesError(f"p: rate in 0..1 required, got {p!r}")
    if isinstance(half_width, bool) or not isinstance(half_width, (int, float)) or not 0.0 < half_width < 1.0:
        raise EpisodesError(f"half_width: in (0, 1) required, got {half_width!r}")
    z = _check_alpha(alpha)
    if p in (0.0, 1.0):
        variance = 0.25
    else:
        variance = p * (1.0 - p)
    return max(2, math.ceil(z * z * variance / (half_width * half_width)))


def verdict_for_claim(n: int, k: int, tolerance: float, alpha: float = 0.05) -> dict:
    """SUFFICIENT or INSUFFICIENT_EVIDENCE for a claim needing tolerance.

    Rule: Wilson interval width wider than tolerance => INSUFFICIENT.
    k=0 additionally reports the rule-of-three bound. Never "safe".
    """
    _check_counts(n, k)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not 0.0 < tolerance < 1.0:
        raise EpisodesError(f"tolerance: in (0, 1) required, got {tolerance!r}")
    lo, hi = wilson(n, k, alpha)
    width = hi - lo
    out = {
        "n": n,
        "k": k,
        "rate": k / n,
        "wilson": [lo, hi],
        "clopper_pearson": clopper_pearson(n, k, alpha),
        "width": width,
        "tolerance": tolerance,
        "verdict": "SUFFICIENT" if width <= tolerance else "INSUFFICIENT_EVIDENCE",
    }
    if k == 0:
        out["rule_of_three_hi"] = rule_of_three(n)
    if k == n:
        out["rule_of_three_failure_hi"] = rule_of_three(n)
    return out
