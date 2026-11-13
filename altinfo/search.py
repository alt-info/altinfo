"""Ticker search: everything the platform knows about a company or a commodity, on one page.

Sections follow the product description: satellite intelligence, supply chain map, expectations (prediction markets,
consensus and price targets for companies, futures for commodities), attention, gap score and next event, linked assets.
"""
import html as h
import json
from pathlib import Path

import pandas as pd

from .coverage import COVERAGE, find


def _kalshi(km, c):
    hit = km["series"].isin(c["kalshi"])
    if c.get("kalshi_pattern"):
        hit |= km["title"].str.contains(c["kalshi_pattern"], case=False, na=False, regex=True)
    m = km[hit].copy()
    if m.empty:
        return m
    tight = (m["yes_ask_dollars"] - m["yes_bid_dollars"]).le(0.10) & m["yes_ask_dollars"].gt(0)
    m["prob"] = ((m["yes_bid_dollars"] + m["yes_ask_dollars"]) / 2).where(tight, m["last_price_dollars"])
    m = m.sort_values("volume_fp", ascending=False)
    return m.assign(venue="Kalshi")[["venue", "title", "yes_sub_title", "prob", "volume_fp", "close_time"]].rename(
        columns={"yes_sub_title": "contract", "volume_fp": "volume", "close_time": "closes"})


def _poly(pm, pattern):
    m = pm[pm["question"].str.contains(pattern, case=False, na=False, regex=True) & (pm["closed"] != True)]  # noqa: E712
    m = m.sort_values("volume", ascending=False)
    return m.assign(venue="Polymarket", contract="Yes")[["venue", "question", "contract", "price", "volume", "end"]].rename(
        columns={"question": "title", "price": "prob", "end": "closes"})


def _expectations(key, c, root, prices, snap):
    """Consensus and price targets for a company; the futures curve for a commodity."""
    raw = Path(root) / "data" / "raw" if root else None
    if c["kind"] == "company":
        f = raw / "fundamentals.csv" if raw else None
        if f is not None and f.exists():
            from .valuation import consensus
            s = consensus(pd.read_csv(f), key)
            return {"title": "Analyst consensus and price targets", "rows": s, "source": "Yahoo Finance (consensus of brokers)"}
        if key == "NVDA" and snap:
            nv = snap["nvda"]["real"]
            return {"title": "Analyst consensus", "source": "As printed in the report, 9 Nov",
                    "rows": pd.Series({"Q3 EPS consensus": nv["q3_eps_consensus"], "Q3 revenue consensus, $bn": nv["q3_revenue_consensus_bn"],
                                       "Average price target": nv["analyst_target_avg"]})}
        return None
    root_code = c.get("curve")
    f = raw / "futures_curve.csv" if raw else None
    if root_code and f is not None and f.exists():
        from .valuation import latest_curve
        lc = latest_curve(pd.read_csv(f), root_code)
        if len(lc):
            rows = pd.Series({pd.Period(m).strftime("%b %Y"): v for m, v in lc.items()})
            first, last = lc.iloc[0], lc.iloc[-1]
            shape = "backwardation (near above far: tight supply)" if first > last else "contango (near below far: ample supply)"
            return {"title": "Futures curve", "rows": rows.map("{:.2f}".format), "source": f"Yahoo Finance, NYMEX. Shape: {shape}"}
    p = prices[c["price"]].dropna() if c["price"] in prices else pd.Series(dtype=float)
    if len(p):
        return {"title": "Futures price", "rows": pd.Series({f"Front month ({c['price']})": f"{p.iloc[-1]:,.2f}"}),
                "source": "Yahoo Finance. Run fetch_data.py for the whole curve" if root_code else "Yahoo Finance"}
    return None


def ticker_page(query, prices: pd.DataFrame, kalshi_markets=None, polymarket_markets=None, signals=None, calls=None,
                today=None, top=12, root=None):
    """Return a dict with every section of the page. With `root` (the project folder) it also reads the signal
    histories, the supply chain alerts, consensus or futures curve from data/raw and data/prototype."""
    key = find(query)
    if key is None:
        raise KeyError(f"{query!r} is not covered yet")
    c = COVERAGE[key]
    today = pd.Timestamp(today) if today else prices.index.max()
    out = {"key": key, "profile": pd.Series({"name": c["name"], "type": c["kind"], "group": c["group"],
                                             "region": c.get("region", ""), "price ticker": c["price"]})}
    p = prices[c["price"]].dropna() if c["price"] in prices else pd.Series(dtype=float)
    p = p.loc[:today]
    if len(p) > 22:
        out["price"] = pd.Series({"last": round(p.iloc[-1], 2), "1 week": f"{p.iloc[-1] / p.iloc[-6] - 1:+.1%}",
                                  "1 month": f"{p.iloc[-1] / p.iloc[-22] - 1:+.1%}",
                                  "from 1y high": f"{p.iloc[-1] / p.iloc[-252:].max() - 1:+.1%}"})
    mk = []
    if kalshi_markets is not None and (c["kalshi"] or c.get("kalshi_pattern")):
        mk.append(_kalshi(kalshi_markets, c).head(top))
    if polymarket_markets is not None and c["polymarket"]:
        mk.append(_poly(polymarket_markets, c["polymarket"]).head(top))
    out["markets"] = pd.concat([m for m in mk if len(m)], ignore_index=True) if any(len(m) for m in mk) else pd.DataFrame()

    lk = [t for t in c["linked"] if t in prices and prices[t].dropna().size > 22]
    out["linked"] = pd.DataFrame({t: {"1 month": prices[t].loc[:today].dropna().iloc[-1] / prices[t].loc[:today].dropna().iloc[-22] - 1,
                                      "corr 1y": prices[t].pct_change(fill_method=None).iloc[-252:].corr(
                                          prices[c["price"]].pct_change(fill_method=None).iloc[-252:])}
                                  for t in lk}).T if lk and len(p) else pd.DataFrame()
    out["signals"] = pd.DataFrame({"signal": c["signals"]})
    ev = sorted((pd.Timestamp(d), e) for d, e in c["events"] if pd.Timestamp(d) >= today)
    nxt = ev[0] if ev else (None, "none scheduled")
    out["events"] = ev
    g = calls[calls.asset == key] if calls is not None else pd.DataFrame()
    out["gap"] = pd.Series({"next event": f"{nxt[1]} ({nxt[0]:%d %b %Y})" if nxt[0] is not None else nxt[1],
                            "our probability": f"{g.ours.iloc[0]:.0%}" if len(g) else "no call yet",
                            "market": f"{g.market.iloc[0]:.0%}" if len(g) else "",
                            "gap": f"{(g.ours.iloc[0] - g.market.iloc[0]) * 100:+.0f} pts" if len(g) else ""})
    if root is not None:
        from . import signals as sg
        snap_f = Path(root) / "data" / "snapshot_2026-11-09.json"
        snap = json.load(open(snap_f)) if snap_f.exists() else None
        s = sg.collect(key, root, today)
        out["indices"] = s["charts"]
        out["weather"] = s["weather"]
        out["sites"] = c["sites"]
        out["alerts"] = s["alerts"]
        out["attention"] = s["attention"]
        out["expectations"] = _expectations(key, c, root, prices, snap)
        out["live_sources"] = s["live_sources"]
    out["monitor"] = {"watch": {"name": c["name"], "sites": [x["site"] for x in c["sites"]]},
                      "signals": c["signals"] + ["Earthquake within 100 km", "Fire within 30 km", "Prediction market moves 10 pts"],
                      "trigger": "threshold, change against normal or a combination", "action": ["app", "email", "watchlist"]}
    return out


# ------------------------------------------------------------------ html
def _chg(v):
    v = str(v)
    return f"<span class='{'dn' if v.startswith('-') else 'up'}'>{h.escape(v)}</span>"


def _locked(what):
    return f"<div class='locked'><b>Institutional tier</b><span>{h.escape(what)}</span></div>"


def to_html(page, query):
    """One page per ticker, like a quote page: header with price, then markets, gap, satellite indices, supply chain,
    expectations, attention and linked assets. Sections missing from a free tier page are shown as locked."""
    from . import signals as sg
    pr, pf = page.get("price", pd.Series(dtype=object)), page["profile"]
    free = page.get("tier") == "Free"
    stats = "".join(f"<div><span>{h.escape(k[:1].upper() + k[1:])}</span><b>{_chg(v) if k != 'last' else h.escape(f'{v:,.2f}')}</b></div>"
                    for k, v in pr.items())
    mk = page.get("markets", pd.DataFrame())
    rows = "".join(
        f"<tr><td><span class='venue {r.venue}'>{r.venue}</span></td><td>{h.escape(str(r.title))}</td>"
        f"<td>{h.escape(str(r.contract))}</td><td class='n'><b>{'' if r.prob != r.prob else f'{r.prob:.0%}'}</b></td>"
        f"<td class='n'>{r.volume:,.0f}</td><td class='n'>{str(r.closes)[:10]}</td></tr>" for r in mk.itertuples()) if len(mk) else ""
    markets = (f"<div class='tbl-wrap'><table class='dataframe'><thead><tr><th>Venue</th><th>Market</th><th>Contract</th><th class='n'>Probability</th>"
               f"<th class='n'>Volume</th><th class='n'>Closes</th></tr></thead><tbody>{rows}</tbody></table></div>"
               if rows else "<p class='empty'>No open prediction market on this name in the last download.</p>")
    lk = page.get("linked", pd.DataFrame())
    linked = ("<div class='chips'>" + "".join(f"<div class='chip'><b>{h.escape(t)}</b>{_chg(f'{r[0]:+.1%}')}<small>corr {r[1]:.2f}</small></div>"
                                             for t, r in zip(lk.index, lk.values)) + "</div>") if len(lk) else "<p class='empty'>No linked assets.</p>"
    sigs = "".join(f"<span class='sigtag'>{h.escape(str(x))}</span>" for x in page.get("signals", pd.DataFrame()).get("signal", []))
    if free:
        gap_html = _locked("Gap score: our probability against the market's")
    else:
        gap_html = "<div class='tp-gap'>" + "".join(
            f"<div class='{'stack' if len(str(v)) > 18 else ''}'><span>{h.escape(k[:1].upper() + k[1:])}</span><b>{h.escape(str(v)) or 'none'}</b></div>"
            for k, v in page["gap"].items()) + "</div>" if "gap" in page else _locked("Gap score")
    if free:
        ev = page.get("events", [])
        gap_html = ("<div class='tp-gap'>" + "".join(f"<div><span>{d:%d %b %Y}</span><b>{h.escape(e)}</b></div>" for d, e in ev[:3]) +
                    "</div>" if ev else "<p class='empty'>No event scheduled.</p>") + gap_html

    # full width sections
    sec = []
    if "indices" in page:
        cards = "".join(f"<div class='tcard'><h5>{h.escape(x['title'])}</h5>{x['svg']}<p>{h.escape(x['note'])}</p>"
                        f"<p class='src'>Source: {h.escape(x['source'])}</p></div>" for x in page["indices"])
        sec.append(f"<section class='tp-sec'><h4>Satellite intelligence and signal history</h4><div class='tgrid'>{cards}</div></section>")
        wx = page.get("weather")
        if wx is not None and len(wx):
            rws = "".join(f"<tr><td>{h.escape(r.region)}</td><td class='n'>{r.rain_mm:.0f}</td><td class='n'>{r.normal_mm:.0f}</td>"
                          f"<td class='n'><b>{r.rain_pct_normal:.0%}</b></td><td class='n'>{r.temp_anomaly_c:+.1f}</td></tr>" for r in wx.itertuples())
            sec.append("<section class='tp-sec'><h4>Weather in the key growing regions, last 30 days</h4><div class='tbl-wrap'>"
                       "<table class='dataframe'><thead><tr><th>Region</th><th class='n'>Rain, mm</th><th class='n'>Normal, mm</th>"
                       f"<th class='n'>% of normal</th><th class='n'>Temperature vs normal, C</th></tr></thead><tbody>{rws}</tbody></table></div>"
                       f"<p class='src'>Open-Meteo ERA5 reanalysis, 30 days to {wx.to.max():%d %b %Y}; normal is the same window in the previous 10 years.</p></section>")
    elif free:
        sec.append(f"<section class='tp-sec'><h4>Satellite intelligence</h4>{_locked('Live satellite readings are never shown in the free tier')}</section>")
    if "sites" in page:
        al = page["alerts"]
        alt = "".join(f"<tr><td>{h.escape(r.site)}</td><td>{h.escape(r.alert)}</td><td class='n'>{pd.Timestamp(r.time):%d %b %H:%M}</td></tr>"
                      for r in al.itertuples())
        live = page.get("live_sources", {})
        srcs = ", ".join(n for n, ok in (("USGS earthquakes", live.get("quakes")), ("NASA FIRMS fires", live.get("fires"))) if ok) or "none downloaded yet"
        tbl = (f"<div class='tbl-wrap'><table class='dataframe'><thead><tr><th>Site</th><th>Live alert</th><th class='n'>When, UTC</th></tr></thead>"
               f"<tbody>{alt}</tbody></table></div>" if alt else
               "<p class='empty'>No earthquake within 100 km and no fire within 30 km of these places in the last download.</p>")
        sites = "".join(f"<tr><td>{h.escape(s['site'])}</td><td>{h.escape(s['role'])}</td><td>{h.escape(s['country'])}</td></tr>"
                        for s in page["sites"])
        sec.append(f"<section class='tp-sec'><h4>Supply chain map</h4>{sg.map_html(page['sites'], al)}{tbl}"
                   f"<p class='src'>Feeds checked: {h.escape(srcs)}. Coordinates are approximate public locations.</p>"
                   f"<details class='sites'><summary>All {len(page['sites'])} places</summary><div class='tbl-wrap'><table class='dataframe'>"
                   f"<thead><tr><th>Place</th><th>Role</th><th>Country</th></tr></thead><tbody>{sites}</tbody></table></div></details></section>")
    elif free:
        sec.append(f"<section class='tp-sec'><h4>Supply chain map</h4>{_locked('Places, live alerts and custom sites')}</section>")
    ex = page.get("expectations")
    if ex:
        rr = "".join(f"<div><span>{h.escape(str(k))}</span><b>{h.escape(v if isinstance(v, str) else f'{v:,.2f}')}</b></div>"
                     for k, v in ex["rows"].items() if v is not None and v == v)
        exp = f"<h4>{h.escape(ex['title'])}</h4><div class='tp-gap'>{rr}</div><p class='src'>{h.escape(ex['source'])}</p>"
    else:
        exp = ""
    att = sg.attention_html(page["attention"]) if page.get("attention") else "<p class='empty'>No attention data for this name yet.</p>"
    sec.append(f"<section class='tp-sec'><h4>Attention on X and Stocktwits</h4>{att}</section>")
    mon = ""
    if not free and "monitor" in page:
        mon = ("<h4>Turn a signal into a monitor</h4><div class='sigtags'>" +
               "".join(f"<button class='mbtn' type='button' title='Creates a monitor on this signal in the web app'>+ {h.escape(s_)}</button>"
                       for s_ in page["monitor"]["signals"][:6]) +
               f"</div><details class='spec'><summary>Monitor spec</summary><pre>{h.escape(json.dumps(page['monitor'], indent=1))}</pre></details>")
    badge = f"<span class='tier {'free' if free else 'inst'}'>{'Free' if free else 'Institutional'} view</span>"
    return (f"<div class='tp'><div class='tp-head'><div><div class='tp-name'>{h.escape(pf['name'])} {badge}</div>"
            f"<div class='tp-meta'>{h.escape(query.upper())}, {h.escape(pf['type'])}, {h.escape(pf['group'])}, {h.escape(pf.get('region', ''))}, "
            f"priced on {h.escape(pf['price ticker'])}</div></div><div class='tp-stats'>{stats}</div></div>"
            f"<div class='tp-body'><div class='tp-main'><h4>Prediction markets on Kalshi and Polymarket</h4>{markets}</div>"
            f"<div class='tp-side'><h4>{'Next events' if free else 'Gap and next event'}</h4>{gap_html}{exp}"
            f"<h4>Linked assets, last month</h4>{linked}<h4>Signals we track</h4><div class='sigtags'>{sigs}</div>{mon}</div></div>"
            + "".join(sec) + "</div>")
