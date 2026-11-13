"""Unit tests: python -m pytest tests  (or simply: python tests/test_core.py)."""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from altinfo import eventbeta as eb, gap, satellite, scoring, earnings, monitors, dashboard  # noqa: E402
from altinfo.coverage import COPPER_MINES, find  # noqa: E402
from altinfo.sources import kalshi  # noqa: E402

SNAP = json.load(open(os.path.join(ROOT, "data", "snapshot_2026-11-09.json")))


def test_brent_scenarios_give_62pct():
    sc = [gap.Scenario(**s) for s in SNAP["brent"]["prototype"]["scenarios"]]
    p = gap.scenario_prob_above(sc, 96)
    assert abs(p - 0.6167) < 1e-3


def test_ladder_and_gap():
    lad = SNAP["brent"]["real"]["kalshi_brent_above"]
    m = gap.ladder_prob_above([float(k) for k in lad], list(lad.values()), 96)
    assert abs(m - 0.52) < 0.01
    g = gap.priced_in_gap(0.62, m)
    assert g["label"] == "UNDER-PRICED" and abs(g["gap_pts"] - 10) < 1
    assert gap.priced_in_gap(0.90, 0.92)["label"] == "PRICED IN"


def test_ladder_is_monotone():
    assert gap.ladder_prob_above([90, 95, 100], [0.5, 0.6, 0.2], 95) <= 0.5


def test_buildout_index_matches_preview():
    p = pd.read_csv(os.path.join(ROOT, "data", "prototype", "campuses.csv"))
    h = satellite.buildout_history(p)
    assert np.allclose(h["index"].values, [0.38, 0.45, 0.53, 0.60], atol=0.006)
    assert np.allclose(h["gw_fit_out"].values, [1.6, 2.3, 3.2, 4.2], atol=0.05)


def test_tank_fill():
    assert satellite.tank_fill(5, 20) == 0.75
    assert satellite.tank_fill(25, 20) == 0.0


def test_brier_and_track_record():
    assert scoring.brier([1.0, 0.0], [1, 0]) == 0
    calls = pd.DataFrame({"event": ["a", "b"], "ours": [0.62, 0.9], "market": [0.52, 0.92], "outcome": [1, np.nan]})
    _, s = scoring.track_record(calls)
    assert s["resolved"] == 1 and s["skill_vs_market"] > 0


def test_next_day_moves():
    px = pd.Series([100, 110, 99], index=pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28"]))
    m = earnings.next_day_moves(px, {"Q2 FY27": "2026-08-26"})
    assert abs(m.move.iloc[0] - 0.10) < 1e-12


def test_kalshi_candle_formats():
    live = {"price": {"close_dollars": "0.7700"}, "yes_bid": {"close_dollars": "0.7600"}, "yes_ask": {"close_dollars": "0.7700"}}
    hist = {"price": {"close": "0.0100"}, "yes_bid": {"close": "0.0000"}, "yes_ask": {"close": "1.0000"}}
    assert abs(kalshi.candle_price(live) - 0.765) < 1e-9
    assert kalshi.candle_price(hist) == 0.01  # wide spread after settlement: use last trade


def test_event_beta_recovers_true_beta():
    rng = np.random.default_rng(0)
    d = pd.bdate_range("2026-01-01", periods=300)
    p = pd.Series(np.clip(0.5 + np.cumsum(rng.normal(0, 0.02, 300)), 0.02, 0.98), index=d)
    shock = eb.event_changes(p.to_frame("x"))["x"]
    r = 0.3 * shock / 10 + rng.normal(0, 0.5, 300)  # +0.3% per 10 points
    b = eb.event_betas(r.to_frame("A"), shock.to_frame("x"), scale={"x": 10})
    assert abs(b.beta.iloc[0] - 0.3) < 0.1


def test_fed_expected_move():
    rows = []
    for day, p in [("2026-12-01", {"H0": .8, "H25": .2}), ("2026-12-02", {"H0": .6, "H25": .4})]:
        for o, v in p.items():
            rows.append({"date": day, "meeting": "26DEC", "outcome": o, "price": v})
        for o in ["C25", "C26", "H26"]:
            rows.append({"date": day, "meeting": "26DEC", "outcome": o, "price": 0.0})
    f = eb.fed_expected_move(pd.DataFrame(rows), {"26DEC": "2026-12-09"})
    assert abs(f.E.iloc[-1] - 10) < 1e-9 and abs(f.dE.iloc[-1] - 5) < 1e-9


def test_haversine_and_disasters():
    assert abs(monitors.km_between(51.5074, -0.1278, 48.8566, 2.3522) - 344) < 5  # London to Paris
    quakes = pd.DataFrame([{"time": pd.Timestamp("2026-11-01"), "mag": 6.1, "place": "near Grasberg", "lat": -4.10, "lon": 137.20}])
    near = monitors.disasters_near(COPPER_MINES, quakes, radius_km=30)
    assert list(near.site) == ["Grasberg"]


def test_copper_monitor_needs_both_legs():
    d = pd.date_range("2026-01-01", periods=60)
    act = pd.Series(100.0, index=d); act.iloc[-1] = 60
    m = monitors.Monitor("copper", COPPER_MINES, monitors.copper_rule)
    q = pd.DataFrame([{"time": d[-1], "mag": 6.0, "place": "x", "lat": -4.06, "lon": 137.12}])
    a = m.run(quakes=q, activity={"Grasberg": act}, asof=d[-1])
    assert a.level.tolist() == ["ALERT"]
    far = q.assign(lat=10.0)
    assert m.run(quakes=far, activity={"Grasberg": act}, asof=d[-1]).level.tolist() == ["WATCH"]


def test_gap_ranking_and_coverage():
    calls = pd.DataFrame({"asset": ["A", "B"], "event": ["x", "y"], "date": ["2026-11-17"] * 2, "ours": [0.9, 0.62],
                          "market": [0.92, 0.26], "market_week_ago": [0.9, 0.6], "confidence": ["m", "m"]})
    r = dashboard.gap_ranking(calls)
    assert r.asset.iloc[0] == "B" and r.label.tolist() == ["UNDER-PRICED", "PRICED IN"]
    assert find("nvda") == "NVDA" and find("brent") == "BRENT" and find("HG=F") == "COPPER"


def test_coverage_agriculture_and_portfolio_sites():
    from altinfo.coverage import COVERAGE, sites_for_holdings
    assert find("corn") == "CORN" and find("soybean") == "SOYBEANS" and find("KC=F") == "COFFEE"
    assert all(k in COVERAGE for k in ["CORN", "WHEAT", "SOYBEANS", "COFFEE", "SUGAR"])
    s = sites_for_holdings(["FCX"])
    assert {x["site"] for x in s} >= {"Grasberg", "Cerro Verde"}
    assert len(sites_for_holdings(["copper"])) == len(COVERAGE["COPPER"]["sites"])


def test_calendar_merges_same_event():
    cal = dashboard.upcoming("2026-11-10", days=14)
    cp = cal[cal.event == "USDA Crop Progress"]
    assert len(cp) == len(set(cp.date)) and "Corn" in cp.names.iloc[0] and "Wheat" in cp.names.iloc[0]
    assert pd.Timestamp("2026-11-30") not in set(cal.date)
    assert pd.Timestamp("2026-11-30") in set(dashboard.upcoming("2026-11-10", 14, live_calls=["BRENT"]).date)


def test_valuation_helpers():
    from altinfo import valuation
    p = pd.Series(np.arange(100, 200, dtype=float), index=pd.bdate_range("2026-01-01", periods=100))
    r = valuation.runup(p)
    assert abs(r["1 week"] - (199 / 194 - 1)) < 1e-9
    curve = pd.DataFrame([{"date": "2026-11-09", "root": "BZ", "month": f"2026-{m:02d}" if m <= 12 else f"2027-{m - 12:02d}",
                           "contract": "x", "close": 100 - i} for i, m in enumerate(range(12, 18))])
    s = valuation.curve_spread(curve, "BZ", 1, 6)
    assert s["spread"].iloc[0] == 5
    eps = pd.DataFrame({"ticker": "N", "period_end": ["2024-01-31", "2025-01-31"], "eps": [1.0, 2.0]})
    mon = pd.DataFrame({"ticker": "N", "date": ["2024-06-01", "2025-06-01"], "close": [50.0, 80.0]})
    pe = valuation.pe_history(mon, eps, "N")
    assert list(pe.round(1)) == [50.0, 40.0]


def test_weather_anomaly():
    from altinfo.sources import weather
    d = pd.date_range("2015-01-01", "2026-11-04")
    df = pd.DataFrame({"date": d, "precip": 2.0, "tmean": 10.0})
    df.loc[df.date > "2026-10-05", "precip"] = 1.0
    a = weather.anomaly(df)
    assert abs(a["rain_pct_normal"] - 0.5) < 1e-9 and abs(a["temp_anomaly_c"]) < 1e-9


def test_fires_alerts_gainers_and_tiers():
    from altinfo import tiers
    fires = pd.DataFrame({"time": pd.to_datetime(["2026-11-09"]), "lat": [-4.1], "lon": [137.2], "frp": [10.0]})
    sites = COPPER_MINES + COPPER_MINES[:1]  # Grasberg twice is checked once
    al = monitors.site_alerts(sites, None, fires)
    assert al.site.tolist() == ["Grasberg"]
    gain, lose = monitors.gainers_losers({"FCX": 0.35})
    assert "FCX" in lose and "FCX" not in gain and "SCCO" in gain and "PRY.MI" in lose
    page = {"profile": 1, "price": 2, "gap": 3, "indices": 4, "sites": 5, "attention": 6}
    free = tiers.ticker_page_for(page, "free")
    assert "gap" not in free and "indices" not in free and "sites" not in free and free["tier"] == "Free"
    assert tiers.report_available("free", "2026-11-17", "2026-11-18") and not tiers.report_available("free", "2026-11-17", "2026-11-10")


def test_svg_charts():
    from altinfo import signals
    assert signals.svg_line(pd.date_range("2026-01-01", periods=3), [1, 2, 3]).startswith("<svg")
    assert "60%" in signals.svg_bars(["a", "b"], [50, 60], "{:.0f}%")
    assert "leaflet" in signals.map_html([dict(m, role="Mine") for m in COPPER_MINES[:2]])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
