"""Create the illustrative satellite inputs used by the prototype (data/prototype).

Real inputs would come from imagery analysis. Here we generate a campus panel and tank shadow
readings that are internally consistent with the figures printed in the two sample previews:
Build-out Index 38%, 45%, 53%, 60% and 1.6, 2.3, 3.2, 4.2 GW in fit-out over four quarters
(42 campuses, 18.6 GW); tank fills by hub now and four weeks ago.
Run: python scripts/make_prototype_data.py
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "prototype")
os.makedirs(OUT, exist_ok=True)

STAGES = ["site_prep", "shell", "roof_mech", "power_cooling", "energized"]
W = np.array([0.15, 0.40, 0.60, 0.85, 1.00])
QUARTERS = ["Q4 FY26", "Q1 FY27", "Q2 FY27", "Q3 FY27"]
TARGET_IDX = np.array([0.38, 0.45, 0.53, 0.60])
TARGET_GW = np.array([1.6, 2.3, 3.2, 4.2])


def score(gw, st):
    idx = (W[st] * gw[:, None]).sum(0) / gw.sum()
    fit = (gw[:, None] * (st >= 3)).sum(0)
    return np.abs(idx - TARGET_IDX).max() * 100 + np.abs(fit - TARGET_GW).max() * 10, idx, fit


rng = np.random.default_rng(7)
gw = rng.gamma(2.0, 1.0, 42)
gw = np.round(gw / gw.sum() * 18.6, 2)
gw[-1] += round(18.6 - gw.sum(), 2)
st = np.zeros((42, 4), int)
st[:, 0] = rng.choice(5, 42, p=[0.30, 0.35, 0.27, 0.05, 0.03])
for q in range(1, 4):
    st[:, q] = np.minimum(4, st[:, q - 1] + rng.binomial(1, 0.35, 42))
best, _, _ = score(gw, st)
cur, best_st = best, st.copy()
T = 2.0
for it in range(800000):  # simulated annealing: move one campus one stage, keep stages monotone in time
    i, q = rng.integers(42), rng.integers(4)
    cand = st.copy()
    if rng.random() < 0.5:
        cand[i, q:] = np.clip(cand[i, q:] + 1, 0, 4)
    else:
        cand[i, :q + 1] = np.clip(cand[i, :q + 1] - 1, 0, 4)
    s, _, _ = score(gw, cand)
    if s <= cur or rng.random() < np.exp((cur - s) / T):
        cur, st = s, cand
        if s < best:
            best, best_st = s, cand.copy()
    T = max(0.005, T * 0.99999)
    if best < 0.3:
        break
st = best_st
_, idx, fit = score(gw, st)
rows = [{"campus": f"C{i + 1:02d}", "gw": gw[i], "quarter": QUARTERS[q], "stage": STAGES[st[i, q]]}
        for i in range(42) for q in range(4)]
pd.DataFrame(rows).to_csv(os.path.join(OUT, "campuses.csv"), index=False)
print("Build-out index:", np.round(idx * 100, 1), " GW in fit-out:", np.round(fit, 2))

# Tanks: fill = 1 - inner/outer shadow. Two to four tanks per hub with different capacities.
FILL = {"Cushing, US": (0.34, 0.36), "US Gulf Coast": (0.53, 0.51), "Rotterdam (ARA)": (0.48, 0.47),
        "Fujairah, UAE": (0.41, 0.33), "China east coast": (0.63, 0.57), "Japan and Korea": (0.51, 0.49)}
rows = []
for hub, (before, now) in FILL.items():
    n = rng.integers(2, 5)
    cap = rng.uniform(0.3, 1.2, n)
    for date, f in (("4 weeks ago", before), ("now", now)):
        fills = np.clip(f + rng.normal(0, 0.04, n), 0.05, 0.95)
        fills += f - (fills * cap).sum() / cap.sum()  # keep the capacity weighted mean on target
        outer = rng.uniform(18, 26, n)
        for k in range(n):
            rows.append({"hub": hub, "tank": f"{hub[:3].upper()}{k + 1}", "date": date, "capacity": round(cap[k], 3),
                         "outer": round(outer[k], 2), "inner": round(outer[k] * (1 - fills[k]), 3)})
pd.DataFrame(rows).to_csv(os.path.join(OUT, "tanks.csv"), index=False)
print("tanks.csv written")

# Memory cargo: weekly tonnes of memory chips flown from Korea and Taiwan to US server assembly sites, read from
# cargo counts at the airports (illustrative). Rising volumes with flat spot prices point to easing memory costs.
rng_m = np.random.default_rng(11)
weeks = pd.date_range(end="2026-11-06", periods=26, freq="W-FRI")
trend = np.linspace(100, 131, len(weeks))
cargo = trend * (1 + rng_m.normal(0, 0.035, len(weeks)))
pd.DataFrame({"week": weeks.strftime("%Y-%m-%d"), "memory_cargo_index": np.round(cargo, 1)}).to_csv(
    os.path.join(OUT, "memory_cargo.csv"), index=False)
print("memory_cargo.csv written")
