"""The priced-in gap: our probability versus the market's.

Three building blocks:
  ladder_prob_above   market probability that a price ends above any level, from a Kalshi
                      ladder of "above X" contracts (monotone interpolation)
  scenario_prob_above our probability from weighted scenarios with price ranges
  priced_in_gap       gap in points and the verdict printed on the preview
"""
from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt

import numpy as np


# ------------------------------------------------------------------ market side
def ladder_prob_above(strikes, probs, level):
    """P(price > level) implied by contracts "above strike" with prices `probs` (0 to 1).

    Prices are made monotone (non increasing in the strike) and interpolated linearly;
    outside the ladder the nearest contract is used.
    """
    k = np.asarray(strikes, float)
    p = np.asarray(probs, float)
    o = np.argsort(k)
    k, p = k[o], np.minimum.accumulate(np.clip(p[o], 0, 1))
    return float(np.interp(level, k, p))


def touch_ladder(levels, probs, spot):
    """Split a "touches level before date" ladder into downside and upside legs."""
    lv, pr = np.asarray(levels, float), np.asarray(probs, float)
    down = {float(l): float(q) for l, q in zip(lv, pr) if l < spot}
    up = {float(l): float(q) for l, q in zip(lv, pr) if l > spot}
    return down, up


# ------------------------------------------------------------------ our side
@dataclass
class Scenario:
    name: str
    weight: float
    low: float | None = None   # None = open ended below
    high: float | None = None  # None = open ended above
    tail: float = 10.0         # width assumed for an open ended range

    def prob_above(self, level):
        lo = self.low if self.low is not None else self.high - self.tail
        hi = self.high if self.high is not None else self.low + self.tail
        if level <= lo:
            return 1.0
        if level >= hi:
            return 0.0
        return (hi - level) / (hi - lo)  # uniform within the range


def scenario_prob_above(scenarios, level):
    """Weighted probability that the price ends above `level`. Weights are normalised."""
    w = np.array([s.weight for s in scenarios], float)
    w = w / w.sum()
    return float(sum(wi * s.prob_above(level) for wi, s in zip(w, scenarios)))


def norm_cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def prob_beat(estimate, consensus, sigma):
    """P(actual > consensus) if the actual is normal around our estimate with st. dev. sigma."""
    return norm_cdf((estimate - consensus) / sigma)


def nowcast(x, y, x_new):
    """Least squares line through (x, y), evaluated at x_new. Returns (prediction, slope, intercept)."""
    b, a = np.polyfit(np.asarray(x, float), np.asarray(y, float), 1)
    return float(a + b * x_new), float(b), float(a)


# ------------------------------------------------------------------ verdict
def priced_in_gap(ours, market, threshold=0.03):
    """Gap in probability points and the label used in the preview header."""
    g = ours - market
    if abs(g) < threshold:
        label = "PRICED IN"
    elif g > 0:
        label = "UNDER-PRICED"
    else:
        label = "OVER-PRICED"
    return {"ours": ours, "market": market, "gap_pts": 100 * g, "label": label}
