"""Analysis engine: one ticker in, one structured analysis out.

    analyze("NVDA")  ->  dict with the seven parts the platform always shows

      evidence       what the observable data say (physical layer; each item marked real, reported or prototype)
      expectations   what the market expects (prediction markets, analysts, futures)
      priced_in      how much of it already sits in the price (run-up, valuation, past reactions)
      gap            our probability minus the market's, with the method behind our number
      confidence     0 to 100 with the reasons
      risks          what could make the reading wrong
      conclusion     a few sentences a non technical reader can follow

The engine only orchestrates. Data arrive through fetch.Fetcher, are made comparable by normalize, and the maths is the
code already in gap.py, valuation.py, earnings.py, satellite.py, monitors.py and signals.py.
"""
import json
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import config, earnings, gap as gapmod, normalize, resolver, satellite, signals, store, valuation
from .errors import NoData
from .fetch import Fetcher
from .monitors import site_alerts

STAGES = ["Recognising the asset", "Collecting the data", "Making sources comparable", "Running the analysis", "Done"]

# Calls registered in the event reports: the method is richer than the automatic ones, so they take priority.
REPORT_CALLS = {
    "NVDA": {"kind": "earnings_beat", "date": "2026-11-17", "question": "NVIDIA beats EPS consensus on 17 Nov",
             "method": "Base rate: NVIDIA beat consensus in each of its last 8 reports (Laplace's rule: 9 in 10)",
             "basis": "evidence", "report": "notebooks/01_nvda_preview.html"},
    "BRENT": {"kind": "price_above", "level": 96.0, "series": "KXBRENTMON", "date": "2026-11-30",
              "question": "Brent closes November above $96",
              "method": "Three scenarios for the US Iran talks, weighted by tanker flows and storage",
              "basis": "evidence", "report": "notebooks/02_brent_preview.html"},
}
ASSET_RISKS = {
    "NVDA": ["Construction stages read from imagery can lag the real fit-out of a data centre.",
             "Memory and packaging costs could squeeze margins even if revenue beats."],
    "BRENT": ["A US Iran deal signed quickly would bring tankers back faster than our scenarios assume.",
              "Tankers sailing with transponders off are missed by ship tracking."],
}


def _f(x, digits=4):
    """JSON safe number."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x or math.isinf(x) else round(x, digits)


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def model_prob(kind, spot, level, sigma_daily, days):
    """What the price itself implies: probability of finishing above a level, or of touching it, for a random walk with
    the volatility of the last 60 days. A neutral yardstick, not a forecast."""
    s = sigma_daily * math.sqrt(max(days, 1))
    if s <= 0 or spot <= 0 or level <= 0:
        return None
    above = 1 - _phi((math.log(level / spot) + 0.5 * s * s) / s)
    if kind == "price_above":
        return above
    if kind == "touch_high":
        return 1.0 if level <= spot else min(1.0, 2 * above)
    if kind == "touch_low":
        return 1.0 if level >= spot else min(1.0, 2 * (1 - above))
    return None


def _label(g_pts):
    return "PRICED IN" if abs(g_pts) < config.PRICED_IN_THRESHOLD * 100 else ("UNDER-PRICED" if g_pts > 0 else "OVER-PRICED")


def _gap(question, ours, market, method, basis, venue, closes, volume=None):
    g = (ours - market) * 100
    return {"question": question, "ours": _f(ours), "market": _f(market), "gap_pts": _f(g, 1), "label": _label(g),
            "method": method, "basis": basis, "venue": venue, "closes": closes, "volume": _f(volume, 0)}


# ====================================================================== collect
def _collect(a, f):
    """Everything the analysis needs, downloaded in parallel through the fetcher."""
    with ThreadPoolExecutor(8) as ex:
        jobs = {"px": ex.submit(f.prices, a["price_ticker"]), "linked": ex.submit(f.prices_many, a["linked"], True),
                "quakes": ex.submit(f.quakes) if a["sites"] else None,
                "fires": ex.submit(f.fires, a["sites"]) if a["sites"] else None,
                "poly": ex.submit(f.poly_all, resolver.search_terms(a)["poly"], a["pattern"]),
                "eia": ex.submit(f.eia) if a["group"] == "Energy" and a["in_registry"] else None,
                "fund": ex.submit(f.fundamentals, [a["key"]] + a["linked"]) if a["kind"] == "company" else None,
                "earn": ex.submit(f.earnings_history, a["price_ticker"]) if a["kind"] == "company" else None,
                "curve": ex.submit(f.curve, a["curve"]) if a["curve"] else None}
        series = list(a["kalshi_series"])
        # every Kalshi series whose title mentions the asset, not only the ones in the registry
        found = f.kalshi_find(resolver.search_terms(a)["kalshi"])
        series += [t for t, title in zip(found.get("ticker", []), found.get("title", []))
                   if (resolver.relevant(str(title), a) or resolver.relevant(str(t), a)) and t not in series]
        # intraday series (15 minute, hourly) settle within the day: noise for a pre event view
        cat = set(found.get("ticker", [])) | set(series)
        series = [t for t in series if not t.endswith("15M") and not (t.endswith("H") and (t[:-1] + "D") in cat)][:30]
        km = list(ex.map(f.kalshi_markets, series))
        regions = {s["site"]: (s["lat"], s["lon"]) for s in a["sites"] if s["role"] == "Growing region"}
        wx = f.weather(regions) if regions else None
        out = {k: (j.result() if j is not None else None) for k, j in jobs.items()}
    out["kalshi"] = pd.concat([m for m in km if len(m)], ignore_index=True) if any(len(m) for m in km) else pd.DataFrame()
    out["weather"], out["regions"] = wx, list(regions)
    return out


# ====================================================================== sections
def _price(px):
    if len(px) < 30:
        return None
    r = valuation.runup(px)
    hi = px.iloc[-252:].max()
    return {"last": _f(px.iloc[-1], 2), "as_of": px.index[-1].strftime("%Y-%m-%d"),
            "change_1w": _f(r.get("1 week")), "change_1m": _f(r.get("1 month")), "change_3m": _f(r.get("3 months")),
            "from_1y_high": _f(px.iloc[-1] / hi - 1), "series": normalize.series(px.iloc[-126:], 2)}


def _evidence(a, d, today):
    """Observable data. direction: +1 supports a higher price or a better result, -1 the opposite, 0 neutral."""
    items, charts, wx_rows = [], [], []
    snap = json.load(open(config.SNAPSHOT))

    def add(label, value, direction, status, note=""):
        items.append({"label": label, "value": value, "direction": direction, "status": status, "note": note})

    if a["in_registry"]:
        sig = signals.collect(a["key"], config.ROOT, today)
        charts = [{"title": c["title"], "note": c["note"], "status": "prototype" if c["prototype"] else "reported", **c["spec"]}
                  for c in sig["charts"] if c["spec"] and not c["title"].startswith(("Price", "Rain", "Kalshi", "Polymarket"))]
    if a["key"] == "NVDA":
        h = satellite.buildout_history(pd.read_csv(config.PROTO / "campuses.csv"))
        add("Data Center Build-out Index", f"{h['index'].iloc[-1]:.0%}", 1, "prototype",
            f"up from {h['index'].iloc[-2]:.0%} a quarter ago: customers' AI data centres are closer to receiving chips")
        add("Capacity in fit-out", f"{h['gw_fit_out'].iloc[-1]:.1f} GW", 1, "prototype",
            f"was {h['gw_fit_out'].iloc[-2]:.1f} GW: more sites at the stage where chips are installed")
        mc = pd.read_csv(config.PROTO / "memory_cargo.csv")["memory_cargo_index"]
        add("Memory cargo to US assembly sites", f"{mc.iloc[-1] / mc.iloc[-13] - 1:+.0%} in 3 months", 1, "prototype",
            "rising shipments point to easing memory costs")
    if a["key"] == "BRENT":
        b = snap["brent"]["real"]
        fl = list(b["hormuz_flow_mbd"].values())
        add("Oil through the Strait of Hormuz", f"{fl[-1]} mb/d", 1, "reported",
            f"{fl[-1] / fl[0] - 1:+.0%} against pre-war levels: the barrels are not back yet")
        add("Ships waiting outside Hormuz", f"about {b['ships_waiting']}", 1, "reported", "a queue this long takes weeks to clear")
    if a["key"] in ("BRENT", "WTI"):
        tk = satellite.tank_table(pd.read_csv(config.PROTO / "tanks.csv"))
        hubs = tk.index if a["key"] == "BRENT" else [x for x in tk.index if x in ("Cushing, US", "US Gulf Coast")]
        ch = (tk.loc[hubs, "now"] - tk.loc[hubs, "4 weeks ago"]).mean() * 100
        add("Storage tank fill (satellite shadows)", f"{ch:+.1f} pts in 4 weeks", 1 if ch < -0.5 else (-1 if ch > 0.5 else 0),
            "prototype", "falling levels mean buyers are drawing on stocks" if ch < 0 else "stocks are building")
    e = d.get("eia")
    if e:
        w = e["weekly"]
        if w.get("crude_vs_5y") is not None:
            v = w["crude_vs_5y"]
            add("US commercial crude stocks", f"{w['commercial_crude_mb']:.1f} mb", 1 if v < -0.02 else (-1 if v > 0.02 else 0),
                "real" if e["live"] else "reported", f"{v:+.0%} against the 5 year average for this week (week to {w['week_ending']})")
        if w.get("distillates_vs_5y") is not None:
            v = w["distillates_vs_5y"]
            add("US distillate stocks", f"{v:+.0%} vs 5 year average", 1 if v < -0.02 else (-1 if v > 0.02 else 0),
                "real" if e["live"] else "reported", "diesel and heating oil")
        if e.get("stocks_history"):
            charts.append({"title": "US commercial crude stocks, million barrels", "note": "Weekly, last two years.", "status": "real",
                           "kind": "line", "x": [p["t"] for p in e["stocks_history"]], "y": [p["v"] for p in e["stocks_history"]],
                           "fmt": "{:.0f}"})
    wx = d.get("weather")
    if wx is not None and len(wx):
        t = signals.weather_table(wx, d["regions"])
        for r in t.itertuples():
            dry, wet = r.rain_pct_normal < 0.7, r.rain_pct_normal > 1.3
            add(f"Rain in {r.region}", f"{r.rain_pct_normal:.0%} of normal", 1 if dry else 0, "real",
                ("much drier than usual: a risk to the crop" if dry else "much wetter than usual" if wet else "close to normal")
                + f", temperature {r.temp_anomaly_c:+.1f} C against normal")
            wx_rows.append({"region": r.region, "rain_mm": _f(r.rain_mm, 0), "normal_mm": _f(r.normal_mm, 0),
                            "pct_normal": _f(r.rain_pct_normal, 3), "temp_anomaly_c": _f(r.temp_anomaly_c, 1)})
        if len(t):
            charts.append({"title": "Rain over the last 30 days, % of normal", "note": "By growing region.", "status": "real",
                           "kind": "bars", "x": list(t.region), "y": [round(v * 100) for v in t.rain_pct_normal], "fmt": "{:.0f}%"})
    alerts = []
    if a["sites"]:
        al = site_alerts(a["sites"], d.get("quakes"), d.get("fires"))
        alerts = [{"site": r.site, "alert": r.alert, "time": pd.Timestamp(r.time).strftime("%d %b %H:%M")} for r in al.itertuples()]
        add("Live alerts near the places it depends on", f"{len(alerts)} of {len(a['sites'])} places",
            1 if alerts and a["kind"] == "commodity" else (-1 if alerts else 0), "real",
            "; ".join(f"{x['site']}: {x['alert']}" for x in alerts[:3]) or "no earthquake within 100 km, no fire within 30 km")
    real = [i for i in items if i["status"] != "prototype"]
    n = {k: sum(i["status"] == k for i in items) for k in ("real", "reported", "prototype")}
    score = sum(i["direction"] * (0.5 if i["status"] == "prototype" else 1.0) for i in items)
    if not items:
        summary = "We do not track physical evidence for this asset yet, so the reading rests on market data only."
    else:
        lean = "supports a stronger outcome" if score > 0.5 else "points to a weaker outcome" if score < -0.5 else "is mixed"
        parts = [f"{v} {txt}" for v, txt in ((n["real"], "from live feeds"), (n["reported"], "from published figures"),
                                             (n["prototype"], "from prototype satellite inputs")) if v]
        summary = (f"{len(items)} observable signal{'s' if len(items) > 1 else ''}: {', '.join(parts)}. "
                   f"Taken together the evidence {lean}.")
    return {"summary": summary, "score": _f(score, 1), "items": items, "charts": charts, "alerts": alerts, "weather": wx_rows,
            "n_real": len(real), "n_prototype": len(items) - len(real)}


def _contracts(a, d, today):
    rows = normalize.kalshi_contracts(d["kalshi"]) if len(d["kalshi"]) else []
    poly = d.get("poly")
    rows += normalize.poly_contracts(poly) if poly is not None and len(poly) else []
    day = today.strftime("%Y-%m-%d")
    keep = [c for c in rows if c["closes"] >= day and (c["series"] in a["kalshi_series"] or resolver.relevant(c["title"], a))]
    own = ("price_above", "touch_high", "touch_low", "earnings_beat", "data_release")   # about the asset itself, shown first
    return sorted(keep, key=lambda c: (c["kind"] not in own, -c["volume"]))


def _ladder(contracts, spot):
    """The most traded set of 'closes above X on date' contracts on the asset's own price."""
    groups = {}
    for c in contracts:
        if c["kind"] == "price_above" and c["level"] and 0.5 * spot < c["level"] < 2 * spot:
            groups.setdefault((c["venue"], c["series"] if c["venue"] == "Kalshi" else "", c["closes"]), []).append(c)
    groups = {k: v for k, v in groups.items() if len(v) >= 3}
    if not groups:
        return None
    best = max(groups.values(), key=lambda v: sum(c["volume"] for c in v))
    return sorted(best, key=lambda c: c["level"])


def _gaps(a, d, contracts, px, today, f):
    """Our probability against the market's, most informative first. Returns (gaps, ladder table, headline history)."""
    gaps, table, hist = [], [], pd.Series(dtype=float)
    spot = float(px.iloc[-1])
    sigma = float(np.log(px).diff().iloc[-60:].std())
    ladder = _ladder(contracts, spot)
    call = REPORT_CALLS.get(a["key"])
    snap = json.load(open(config.SNAPSHOT))

    def days_to(date):
        return int(np.busday_count(today.date(), pd.Timestamp(date).date()))

    # 1. the call of the event report
    if call and pd.Timestamp(call["date"]) >= today:
        if call["kind"] == "earnings_beat":
            m = [c for c in contracts if c["kind"] == "earnings_beat"]
            if m:
                gaps.append(_gap(call["question"], 0.90, m[0]["prob"], call["method"], call["basis"], m[0]["venue"], m[0]["closes"], m[0]["volume"]))
                gaps[-1].update(kind="earnings_beat", level=None)
                hist = f.poly_history(m[0]["id"], m[0]["token"]) if m[0]["token"] else hist
                if hist.empty:
                    bh = pd.Series(snap["nvda"]["real"]["polymarket_beat_history"])
                    hist = pd.Series(bh.values, index=pd.to_datetime(bh.index))
        else:
            lad = [c for c in contracts if c["kind"] == "price_above" and c["series"] == call["series"] and c["closes"][:7] == call["date"][:7]]
            if len(lad) >= 3:
                ours = gapmod.scenario_prob_above([gapmod.Scenario(**s) for s in snap["brent"]["prototype"]["scenarios"]], call["level"])
                mkt = gapmod.ladder_prob_above([c["level"] for c in lad], [c["prob"] for c in lad], call["level"])
                gaps.append(_gap(call["question"], ours, mkt, call["method"], call["basis"], "Kalshi", lad[0]["closes"],
                                 sum(c["volume"] for c in lad)))
                gaps[-1].update(kind="price_above", level=call["level"])
                near = sorted(lad, key=lambda c: abs(c["level"] - call["level"]))[:8]   # enough strikes to bracket the level
                cd = f.kalshi_candles([c["id"] for c in near])
                if len(cd):
                    lv = {c["id"]: c["level"] for c in lad}
                    cd = cd.dropna(subset=["price"]).assign(level=lambda x: x.ticker.map(lv))
                    hist = cd.groupby("date").apply(lambda g: gapmod.ladder_prob_above(g.level, g.price, call["level"])
                                                    if len(g) >= 3 else np.nan, include_groups=False).dropna()
    # 2. earnings beat from the company's own record
    eb = [c for c in contracts if c["kind"] == "earnings_beat"]
    if eb and not gaps:
        e = d.get("earn")
        if e is not None and len(e.dropna()) >= 4:
            e = e.dropna().sort_values("date").iloc[-8:]
            beats, n = int((e.actual > e.estimate).sum()), len(e)
            gaps.append(_gap(f"{a['short_name']} beats EPS consensus", (beats + 1) / (n + 2), eb[0]["prob"],
                             f"Base rate: {beats} beats in the last {n} reports (Laplace's rule)", "base_rate", eb[0]["venue"],
                             eb[0]["closes"], eb[0]["volume"]))
            gaps[-1].update(kind="earnings_beat", level=None)
            if eb[0]["token"]:
                hist = f.poly_history(eb[0]["id"], eb[0]["token"])
    # 3. what the price itself implies, against the ladder of price contracts
    if ladder:
        dd = days_to(ladder[0]["closes"])
        for c in ladder:
            mp = model_prob("price_above", spot, c["level"], sigma, dd)
            table.append({"level": c["level"], "market": _f(c["prob"]), "model": _f(mp), "volume": _f(c["volume"], 0),
                          "gap_pts": _f((mp - c["prob"]) * 100, 1)})
        traded = [c for c in ladder if c["quality"] != "low"] or [c for c in ladder if c["volume"] > 0] or ladder
        atm = min(traded, key=lambda c: abs(c["prob"] - 0.5))
        mp = model_prob("price_above", spot, atm["level"], sigma, dd)
        ok = 0.15 <= atm["prob"] <= 0.85  # a ladder whose best strike is far from 50% does not bracket today's price: stale quotes
        if ok:
            gaps.append(_gap(f"{a['short_name']} closes above {atm['level']:,.2f} on {pd.Timestamp(atm['closes']):%d %b}", mp, atm["prob"],
                             "Price implied: a random walk from today's price with the volatility of the last 60 days",
                             "price_model", atm["venue"], atm["closes"], atm["volume"]))
            gaps[-1].update(kind="price_above", level=atm["level"])
        if ok and hist.empty and atm["venue"] == "Kalshi":
            cd = f.kalshi_candles([atm["id"]])
            hist = cd.dropna(subset=["price"]).set_index("date")["price"] if len(cd) else hist
    # 4. touch contracts (Polymarket 'hit $X') when there is no ladder
    if not any(g["basis"] == "price_model" for g in gaps):
        tc = [c for c in contracts if c["kind"] in ("touch_high", "touch_low") and c["level"] and 0.5 * spot < c["level"] < 2 * spot
              and c["volume"] > 0]
        if tc:
            c = min(tc, key=lambda c: abs(c["prob"] - 0.5))
            mp = model_prob(c["kind"], spot, c["level"], sigma, days_to(c["closes"]))
            verb = "touches" if c["kind"] == "touch_high" else "falls to"
            gaps.append(_gap(f"{a['short_name']} {verb} {c['level']:,.0f} by {pd.Timestamp(c['closes']):%d %b}", mp, c["prob"],
                             "Price implied: a random walk from today's price with the volatility of the last 60 days",
                             "price_model", c["venue"], c["closes"], c["volume"]))
            gaps[-1].update(kind=c["kind"], level=c["level"])
            if c["token"]:
                hist = f.poly_history(c["id"], c["token"])
    for g in gaps:
        _blend(g, contracts)
    return gaps, table, hist


def venue_quotes(contracts, kind, level, closes):
    """What each venue says about the same question: the same kind of contract on the same day (within 2 days).
    For 'closes above X' a venue's whole ladder for that day is interpolated at X, so different strikes still compare."""
    out = []
    if not closes:
        return out
    day = pd.Timestamp(closes)
    for venue in ("Kalshi", "Polymarket"):
        cs = [c for c in contracts if c["venue"] == venue and c["kind"] == kind and c["closes"]
              and abs((pd.Timestamp(c["closes"]) - day).days) <= 2]
        if not cs:
            continue
        if kind == "earnings_beat":
            c = max(cs, key=lambda c: c["volume"])
            out.append({"venue": venue, "prob": _f(c["prob"]), "volume": _f(c["volume"], 0), "how": "same question"})
        elif kind == "price_above" and level:
            lv = sorted({c["level"]: c for c in cs if c["level"]}.values(), key=lambda c: c["level"])
            exact = [c for c in lv if abs(c["level"] / level - 1) < 0.005]
            if exact:
                out.append({"venue": venue, "prob": _f(exact[0]["prob"]), "volume": _f(exact[0]["volume"], 0), "how": "same level"})
            elif len(lv) >= 2 and lv[0]["level"] < level < lv[-1]["level"]:
                p = gapmod.ladder_prob_above([c["level"] for c in lv], [c["prob"] for c in lv], level)
                out.append({"venue": venue, "prob": _f(p), "volume": _f(sum(c["volume"] for c in lv), 0),
                            "how": f"interpolated across {len(lv)} price levels"})
        elif level:
            exact = [c for c in cs if c["level"] and abs(c["level"] / level - 1) < 0.005]
            if exact:
                c = max(exact, key=lambda c: c["volume"])
                out.append({"venue": venue, "prob": _f(c["prob"]), "volume": _f(c["volume"], 0), "how": "same level"})
    return out


def _blend(g, contracts):
    """When both venues price the question, the market probability is their average weighted by traded volume."""
    q = venue_quotes(contracts, g.get("kind"), g.get("level"), g.get("closes"))
    g["quotes"] = q
    if len(q) < 2:
        return
    w = [max(x["volume"] or 0, 0) for x in q]
    mkt = sum(x["prob"] * v for x, v in zip(q, w)) / sum(w) if sum(w) > 0 else sum(x["prob"] for x in q) / len(q)
    g["market"] = _f(mkt)
    g["gap_pts"] = _f((g["ours"] - mkt) * 100, 1)
    g["label"] = _label(g["gap_pts"])
    g["venue"] = "Kalshi and Polymarket, weighted by volume"
    g["volume"] = _f(sum(w), 0)
    g["venue_spread_pts"] = _f(abs(q[0]["prob"] - q[1]["prob"]) * 100, 1)


def _expectations(a, d, contracts, px):
    own = [c for c in contracts if c["kind"] not in ("event", "mention")][:7]
    rest = sorted([c for c in contracts if c["kind"] in ("event", "mention")], key=lambda c: -c["volume"])[:6]
    top = [{k: c[k] for k in ("venue", "title", "contract", "prob", "volume", "closes", "kind", "quality")} for c in own + rest]
    cons, curve = None, None
    fund = d.get("fund")
    if fund is not None and len(fund) and a["key"] in set(fund["ticker"]):
        s = valuation.consensus(fund, a["key"])
        cons = [{"label": k, "value": v} for k, v in s.items()]
    cv = d.get("curve")
    if cv is not None and len(cv):
        lc = valuation.latest_curve(cv, a["curve"])
        if len(lc) >= 2:
            sp = float(lc.iloc[0] - lc.iloc[min(5, len(lc) - 1)])
            curve = {"points": [{"t": pd.Period(m).strftime("%b %y"), "v": _f(v, 2)} for m, v in lc.items()], "spread": _f(sp, 2),
                     "shape": "backwardation" if sp > 0 else "contango",
                     "meaning": "buyers pay more for delivery now than later: supply looks tight" if sp > 0 else
                                "delivery later costs more than now: supply looks ample"}
    vol = sum(c["volume"] for c in contracts)
    if contracts:
        big = max(contracts, key=lambda c: c["volume"])
        summary = (f"{len(contracts)} live prediction market contracts linked to {a['short_name']}. "
                   f"The most traded: “{big['title']}” at {big['prob']:.0%}.")
    else:
        summary = f"No open prediction market on {a['short_name']} was found, so expectations come from prices and analysts only."
    return {"summary": summary, "contracts": top, "n_contracts": len(contracts), "total_volume": _f(vol, 0), "consensus": cons, "curve": curve}


def _priced_in(a, d, px, gaps):
    items = []
    r = valuation.runup(px)
    for k, v in r.items():
        items.append({"label": f"Price change, {k}", "value": f"{v:+.1%}"})
    items.append({"label": "Distance from the 1 year high", "value": f"{px.iloc[-1] / px.iloc[-252:].max() - 1:+.1%}"})
    lk = {t: s for t, s in (d.get("linked") or {}).items() if len(s) > 22}
    if lk:
        med = float(np.median([s.iloc[-1] / s.iloc[-22] - 1 for s in lk.values()]))
        items.append({"label": "Linked assets, 1 month (median)", "value": f"{med:+.1%}"})
    fund = d.get("fund")
    if fund is not None and len(fund) and a["key"] in set(fund["ticker"]) and "forward_pe" in fund:
        peers = [t for t in fund["ticker"] if t != a["key"]]
        m = valuation.multiples(fund, a["key"], peers)
        pe, prem = m.loc[a["key"], "forward_pe"], m.loc[f"{a['key']} vs peers", "forward_pe"] if peers else None
        if pe == pe:
            items.append({"label": "Forward P/E", "value": f"{pe:.1f}x" + (f" ({prem:+.0%} vs peers)" if prem is not None and prem == prem else "")})
    if a["key"] == "NVDA":
        mv = earnings.next_day_moves(px, earnings.NVDA_REPORTS)
        if len(mv):
            s = earnings.reaction_summary(mv)
            items.append({"label": "Share price the day after the last reports",
                          "value": f"fell after {s['negative']} of {s['reports']}, average move {s['avg_abs_move']:.1%}"})
    if gaps:
        g = abs(gaps[0]["gap_pts"])
        level = "largely priced in" if g < 3 else "partly priced in" if g < 10 else "not priced in"
        summary = (f"The market already assigns {gaps[0]['market']:.0%} to “{gaps[0]['question']}”. Against our "
                   f"{gaps[0]['ours']:.0%}, the outcome looks {level}.")
    else:
        level = "unknown"
        mv = r.get("1 month")
        summary = ("There is no market probability to compare with. " +
                   (f"The price moved {mv:+.1%} in a month, which is the only read on what is already expected." if mv is not None else ""))
    return {"summary": summary, "level": level, "items": items}


def _attention(a, d):
    """How much the news talks about the asset compared with normal, in what tone, and the latest headlines (GDELT)."""
    n = d.get("news")
    if not n or n["volume"].empty:
        return {"available": False, "pending": True, "summary": "Loading the news coverage…"}
    v, t = n["volume"], n["tone"]
    recent, base = v.iloc[-7:].mean(), v.iloc[:-7].mean() if len(v) > 14 else None
    ratio = recent / base if base else None
    tone_now = float(t.iloc[-7:].mean()) if len(t) else None
    tone_base = float(t.iloc[:-7].mean()) if len(t) > 14 else None
    if ratio is None:
        level = "unknown"
    else:
        level = "far above normal" if ratio >= 2 else "above normal" if ratio >= 1.3 else "below normal" if ratio <= 0.7 else "normal"
    mood = None if tone_now is None else "negative" if tone_now < -1.5 else "positive" if tone_now > 1.5 else "neutral"
    parts = []
    if ratio is not None:
        parts.append(f"News coverage in the last week is {ratio:.1f} times its 3 month average ({level}).")
    if mood:
        shift = "" if tone_base is None else (" and darker than usual" if tone_now < tone_base - 0.7 else
                                              " and brighter than usual" if tone_now > tone_base + 0.7 else "")
        parts.append(f"The tone of the coverage is {mood}{shift}.")
    return {"available": True, "summary": " ".join(parts), "ratio": _f(ratio, 2), "level": level, "tone": _f(tone_now, 2),
            "tone_3m": _f(tone_base, 2), "mood": mood, "volume": normalize.series(v, 4), "tone_series": normalize.series(t, 3),
            "headlines": n["articles"][:6], "source": "GDELT, news worldwide"}


def _attention_headlines(items):
    """Fallback when GDELT is not available: what the latest headlines say, with a simple word list tone."""
    from .sources.headlines import tone
    df = pd.DataFrame(items)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    now = pd.Timestamp.now()
    week = df[df["time"] >= now - pd.Timedelta(days=7)] if df["time"].notna().any() else df
    score, hit = tone(list(df["title"]))
    mood = "negative" if score < -0.2 else "positive" if score > 0.2 else "mixed"
    days = week.dropna(subset=["time"]).groupby(week["time"].dt.normalize()).size() if len(week) else pd.Series(dtype=float)
    parts = [f"{len(week)} headlines about it in the last 7 days." if len(week) else f"{len(df)} recent headlines."]
    if hit:
        parts.append(f"Their tone is {mood}: {hit} of them use clearly positive or negative words.")
    heads = [{"title": r.title, "url": r.url, "domain": r.domain,
              "seen": r.time.strftime("%Y%m%d") if pd.notna(r.time) else ""} for r in df.head(6).itertuples()]
    return {"available": True, "mode": "headlines", "summary": " ".join(parts), "ratio": None, "level": None,
            "tone": _f(score, 2), "tone_3m": None, "mood": mood, "count_7d": int(len(week)),
            "volume": normalize.series(days.astype(float), 0), "tone_series": [], "headlines": heads,
            "source": "Google News and Yahoo Finance headlines (GDELT, which gives the 3 month trend, is not answering)"}


def _confidence(a, ev, contracts, gaps, f, days):
    score, why = 50, []

    def adj(pts, text):
        nonlocal score
        score += pts
        why.append({"points": pts, "text": text})
    if ev["n_real"] >= 2:
        adj(15, f"{ev['n_real']} signals come from live feeds or published figures")
    elif ev["n_real"] == 1:
        adj(7, "one signal comes from a live feed or a published figure")
    else:
        adj(-10, "no real physical evidence for this asset")
    if ev["n_prototype"]:
        adj(-5, f"{ev['n_prototype']} signal{'s' if ev['n_prototype'] > 1 else ''} rest{'' if ev['n_prototype'] > 1 else 's'} on prototype satellite inputs")
    vol = sum(c["volume"] for c in contracts)
    if vol >= 100000:
        adj(12, "prediction markets on it are actively traded")
    elif vol >= 5000:
        adj(5, "prediction markets on it have moderate volume")
    else:
        adj(-10, "prediction markets on it are thin or missing")
    if gaps:
        b = gaps[0]["basis"]
        adj({"evidence": 10, "base_rate": 3, "price_model": -8}[b],
            {"evidence": "our probability comes from a full event report", "base_rate": "our probability is a simple historical base rate",
             "price_model": "our probability is only what the price implies, not independent evidence"}[b])
    else:
        adj(-12, "no comparable market probability, so no gap can be measured")
    bad = [s["label"] for s in f.status.values() if s["state"] in ("failed", "missing")]
    old = [s["label"] for s in f.status.values() if s["state"] in ("stale", "file")]
    if bad:
        adj(-10, "could not reach: " + ", ".join(bad))
    if old:
        adj(-6, "using saved copies for: " + ", ".join(old))
    if days is not None and days > 45:
        adj(-6, "the next event is more than six weeks away")
    score = int(max(5, min(95, score)))
    return {"score": score, "level": "High" if score >= 70 else "Medium" if score >= 45 else "Low", "reasons": why}


def _risks(a, ev, contracts, gaps, f, att=None):
    out = list(ASSET_RISKS.get(a["key"], []))
    if att and att.get("ratio") and att["ratio"] >= 2:
        out.append(f"News coverage is {att['ratio']:.1f} times normal: prices and odds can move quickly on headlines.")
    if gaps and gaps[0].get("venue_spread_pts") and gaps[0]["venue_spread_pts"] >= 5:
        out.append(f"Kalshi and Polymarket disagree by {gaps[0]['venue_spread_pts']:.0f} points on the same question.")
    if ev["n_prototype"]:
        out.append("Satellite readings in this prototype are illustrative; real imagery could tell a different story.")
    if gaps and gaps[0]["basis"] == "price_model":
        out.append("Our number is only what price and volatility imply. A gap here shows the two markets disagree, not that we know more.")
    if gaps and gaps[0]["basis"] == "base_rate":
        out.append("A base rate ignores what is different this quarter.")
    if sum(c["volume"] for c in contracts) < 5000:
        out.append("Thin prediction markets can show prices that few people actually traded at.")
    if any(c["quality"] == "low" for c in contracts[:5]):
        out.append("Some of the contracts shown have a wide bid ask spread or no recent trade.")
    if any(s["state"] in ("stale", "file", "failed", "missing") for s in f.status.values()):
        out.append("Part of the data could not be refreshed, so some figures may be out of date.")
    out.append("Prediction markets can move within hours of news; the gap is a snapshot, not a forecast.")
    return out[:6]


def _conclusion(a, price, ev, exp, pin, gaps, conf, nxt):
    name = a["short_name"]
    s = []
    if gaps:
        g = gaps[0]
        if g["label"] == "PRICED IN":
            title = f"{name}: the market already expects it"
            s.append(f"On “{g['question']}” we say {g['ours']:.0%} and the market says {g['market']:.0%}. "
                     "That is within 3 points, so there is no edge on this question.")
        else:
            more = "more likely" if g["gap_pts"] > 0 else "less likely"
            title = f"{name}: the market sees it as {'less' if g['gap_pts'] > 0 else 'more'} likely than we do"
            s.append(f"We think “{g['question']}” is {more} than the market does: {g['ours']:.0%} against {g['market']:.0%}, "
                     f"a gap of {abs(g['gap_pts']):.0f} points.")
        if g["basis"] == "price_model":
            s.append("Our figure here is a neutral yardstick taken from the price itself, so read the gap as two markets disagreeing.")
    else:
        title = f"{name}: no measurable gap yet"
        s.append("There is no prediction market we can compare a probability with, so we cannot say how much is priced in.")
    if ev["items"]:
        s.append(ev["summary"])
    if price and price.get("change_1m") is not None:
        s.append(f"The price has moved {price['change_1m']:+.1%} over the last month.")
    if nxt:
        s.append(f"Next date to watch: {nxt['event']} on {pd.Timestamp(nxt['date']):%d %B}.")
    s.append(f"Confidence in this reading is {conf['level'].lower()} ({conf['score']} out of 100).")
    return {"title": title, "text": s}


def _network_warning(f):
    """A plain message when the prediction markets could not be reached, so a thin result is not mistaken for 'nothing found'."""
    pm = [s for k, s in f.status.items() if k in ("kalshi", "polymarket") and s["state"] in ("failed", "missing", "stale", "file")]
    if not pm:
        return None
    names = " and ".join(s["label"] for s in pm)
    blocked = any("HANDSHAKE" in (s["note"] or "").upper() or "SSL" in (s["note"] or "").upper() for s in f.status.values())
    why = ("This network blocks them (the secure connection is refused): university and office networks often do. "
           "Switch to another network, for example a phone hotspot, and run the search again.") if blocked else \
          "They did not answer. Try again in a few minutes."
    return f"{names} could not be reached, so the prediction markets shown come from older saved data or are missing. {why}"


# ====================================================================== entry point
def analyze(query, progress=None, offline=False, save=True):
    """Run the whole pipeline for one ticker or commodity name. `progress(i, label)` is called at each stage."""
    step = progress or (lambda i, label: None)
    f = Fetcher(offline=offline, on_source=lambda name: step(1, f"{STAGES[1]}: {name}"))
    today = pd.Timestamp.now().normalize()

    step(0, STAGES[0])
    a = resolver.resolve(query, f)
    step(1, STAGES[1])
    d = _collect(a, f)
    px = d["px"]
    if len(px) < 30:
        raise NoData(f"We found {a['name']} but not enough price history to analyse it.", "At least 30 trading days are needed.")
    step(2, STAGES[2])
    contracts = _contracts(a, d, today)
    price = _price(px)
    step(3, STAGES[3])
    ev = _evidence(a, d, today)
    gaps, ladder, hist = _gaps(a, d, contracts, px, today, f)
    exp = _expectations(a, d, contracts, px)
    nq = resolver.search_terms(a)["news"]
    d["news"] = f.news(nq, cache_only=True)   # downloaded separately: see news_for
    att = _attention(a, d)
    if not att.get("available"):
        cached = f.headlines(nq, a["price_ticker"], cache_only=True)
        if cached:
            att = _attention_headlines(cached)
    att["query"], att["ticker"] = nq, a["price_ticker"]
    if att.get("available"):
        store.put_series(a["key"], "news_volume", [(p["t"], p["v"]) for p in att["volume"]])
    pin = _priced_in(a, d, px, gaps)
    events = sorted((pd.Timestamp(dt), e) for dt, e in a["events"] if pd.Timestamp(dt) >= today)
    nxt = {"date": events[0][0].strftime("%Y-%m-%d"), "event": events[0][1]} if events else (
        {"date": gaps[0]["closes"], "event": "the contract settles"} if gaps and gaps[0]["closes"] else None)
    days = (pd.Timestamp(nxt["date"]) - today).days if nxt else None
    conf = _confidence(a, ev, contracts, gaps, f, days)
    if gaps and not hist.empty:
        store.put_series(a["key"], "market_prob", [(dt, v) for dt, v in hist.items()])
    store.put_series(a["key"], "price", [(dt, v) for dt, v in px.iloc[-250:].items()])
    head = gaps[0] if gaps else None
    out = {
        "asset": {k: a[k] for k in ("key", "name", "short_name", "kind", "group", "region", "in_registry")} |
                 {"coverage": "full" if a["in_registry"] else "basic", "price_ticker": a["price_ticker"],
                  "report": (REPORT_CALLS.get(a["key"]) or {}).get("report")},
        "as_of": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "price": price, "headline": head, "next_event": nxt | {"days": days} if nxt else None,
        "evidence": ev, "expectations": exp, "priced_in": pin,
        "gap": {"summary": (f"{head['label'].replace('-', ' ').capitalize()}: we say {head['ours']:.0%}, the market says {head['market']:.0%}."
                            if head else "No gap can be measured for this asset yet."),
                "gaps": gaps, "ladder": ladder},
        "attention": att, "confidence": conf, "risks": _risks(a, ev, contracts, gaps, f, att),
        "conclusion": _conclusion(a, price, ev, exp, pin, gaps, conf, nxt),
        "history": {"market_prob": store.get_series(a["key"], "market_prob")[-180:] if gaps else []},
        "sites": [{"site": s["site"], "role": s["role"], "country": s["country"], "lat": s["lat"], "lon": s["lon"]} for s in a["sites"]],
        "sources": sorted(f.status.values(), key=lambda s: s["label"]),
        "warning": _network_warning(f),
        "disclaimer": "Prototype. Satellite inputs are illustrative where marked. Not investment advice.",
    }
    if att.get("available") and att.get("ratio") is not None:
        out["conclusion"]["text"].insert(-1, att["summary"].split(". ")[0].rstrip(".") + ".")
    if save:
        store.save_analysis(a["key"], out)
    out["history"]["analyses"] = store.past_analyses(a["key"])
    return out


def news_for(query, ticker=None, offline=False):
    """The news card on its own (GDELT is slow and rate limited, so the page loads it after the analysis).
    GDELT first, for the 3 month trend and tone; if it does not answer, the latest headlines from Google News and Yahoo."""
    f = Fetcher(offline=offline)
    n = f.news(query)
    if n is None and ticker:
        items = f.headlines(query, ticker)
        if items:
            return _attention_headlines(items)
    if n is None:
        note = (f.status.get("news") or {}).get("note", "")
        busy = "429" in note or "rate limit" in note.lower()
        return {"available": False, "busy": busy,
                "summary": "The news service is busy right now. Try again in a minute." if busy else
                           "News coverage could not be loaded right now.", "note": note}
    return _attention(None, {"news": n})
