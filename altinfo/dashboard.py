"""Dashboard: where is the gap largest right now?

gap_ranking     each covered event with our probability, the market's, the gap, confidence and weekly change
upcoming        calendar of the next events in the coverage
alerts_feed     gap above a threshold, prediction market jumps, large price moves
to_html         a static page with the three blocks (the web app renders the same tables)
"""
import pandas as pd

from .brand import BAND_CSS, FAVICON, FONTS, band_html, logo_svg  # noqa: F401
from .coverage import COVERAGE


def gap_ranking(calls: pd.DataFrame):
    """calls: asset, event, date, ours, market, market_week_ago, confidence. Sorted by absolute gap."""
    t = calls.copy()
    t["gap_pts"] = (t["ours"] - t["market"]) * 100
    t["change_1w_pts"] = (t["market"] - t["market_week_ago"]) * 100
    t["label"] = t["gap_pts"].apply(lambda g: "PRICED IN" if abs(g) < 3 else ("UNDER-PRICED" if g > 0 else "OVER-PRICED"))
    return t.reindex(t["gap_pts"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def upcoming(today, days=14, live_calls=None, horizon=45):
    """Calendar of the next `days` days, plus the later dates of names with a live call (up to `horizon` days).
    The same event on the same day for several names (e.g. the USDA Crop Progress report for corn, wheat and
    soybeans) is one row listing all the names."""
    today = pd.Timestamp(today)
    rows = [{"date": pd.Timestamp(d), "asset": k, "name": v["name"], "event": e, "group": v["group"], "region": v.get("region", "")}
            for k, v in COVERAGE.items() for d, e in v["events"]]
    t = pd.DataFrame(rows)
    keep = t.asset.isin(set(live_calls or [])) & (t.date <= today + pd.Timedelta(days=horizon))
    t = t[(t.date >= today) & ((t.date <= today + pd.Timedelta(days=days)) | keep)]
    out = t.groupby(["date", "event"], sort=True).agg(
        names=("name", ", ".join), assets=("asset", list), group=("group", lambda x: "|".join(dict.fromkeys(x))),
        region=("region", lambda x: "|".join(dict.fromkeys(x)))).reset_index()
    return out


def alerts_feed(ranking=None, jumps=None, prices=None, gap_threshold=5.0, price_threshold=0.04, since=None):
    """One table of alerts from the three sources, newest first."""
    rows = []
    if ranking is not None:
        for r in ranking[ranking.gap_pts.abs() >= gap_threshold].itertuples():
            rows.append({"date": pd.Timestamp(r.date_asof), "type": "Gap", "asset": COVERAGE.get(r.asset, {}).get("name", r.asset),
                         "text": f"{r.event}: gap {r.gap_pts:+.0f} pts, {r.label.lower()}"})
    if jumps is not None:
        for r in jumps.itertuples():
            rows.append({"date": pd.Timestamp(r.date), "type": "Prediction market", "asset": r.key,
                         "text": f"probability {r.move_pts:+.0f} pts to {r.prob:.0%}"})
    if prices is not None:
        tick = {v["price"]: k for k, v in COVERAGE.items()}
        r = prices[[c for c in tick if c in prices]].pct_change(fill_method=None)
        big = r.stack()
        big = big[big.abs() >= price_threshold]
        for (d, t), v in big.items():
            rows.append({"date": d, "type": "Price", "asset": COVERAGE[tick[t]]["name"], "text": f"closed {v:+.1%} on the day ({t})"})
    t = pd.DataFrame(rows, columns=["date", "type", "asset", "text"])
    if since is not None:
        t = t[t.date >= pd.Timestamp(since)]
    return t.sort_values("date", ascending=False).reset_index(drop=True)


def sparkline_svg(values, w=150, h=34, color="#1f7ab8", lo=None, hi=None):
    """Tiny inline SVG line chart (no dependencies)."""
    v = [float(x) for x in values if x == x]
    if len(v) < 2:
        return ""
    lo = min(v) if lo is None else lo
    hi = max(v) if hi is None else hi
    rng = (hi - lo) or 1.0
    pts = " ".join(f"{i * (w - 4) / (len(v) - 1) + 2:.1f},{h - 3 - (x - lo) / rng * (h - 6):.1f}" for i, x in enumerate(v))
    lx, ly = pts.split(" ")[-1].split(",")
    return (f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}' aria-hidden='true'>"
            f"<polyline fill='none' stroke='{color}' stroke-width='1.8' points='{pts}'/>"
            f"<circle cx='{lx}' cy='{ly}' r='2.6' fill='{color}'/></svg>")


def coverage_table(prices, kalshi_markets=None, polymarket_markets=None, calls=None, today=None):
    """One row per covered name: last price, 1 week and 1 month change, linked markets, next event, gap."""
    import re
    today = pd.Timestamp(today) if today is not None else prices.index.max()
    rows = []
    for k, c in COVERAGE.items():
        p = prices[c["price"]].dropna() if c["price"] in prices else pd.Series(dtype=float)
        n_k = 0
        if kalshi_markets is not None:
            hit = kalshi_markets["series"].isin(c["kalshi"])
            if c.get("kalshi_pattern"):
                hit |= kalshi_markets["title"].str.contains(c["kalshi_pattern"], case=False, na=False, regex=True)
            n_k = int(hit.sum())
        n_p = 0
        if polymarket_markets is not None and c["polymarket"]:
            q = polymarket_markets
            n_p = int((q["question"].str.contains(c["polymarket"], case=False, na=False, regex=True) & (q["closed"] != True)).sum())  # noqa: E712
        ev = sorted((pd.Timestamp(d), e) for d, e in c["events"] if pd.Timestamp(d) >= today)
        g = calls[calls.asset == k] if calls is not None else pd.DataFrame()
        rows.append({"key": k, "name": c["name"], "group": c["group"], "region": c.get("region", ""), "kind": c["kind"],
                     "last": p.iloc[-1] if len(p) else None,
                     "w1": p.iloc[-1] / p.iloc[-6] - 1 if len(p) > 6 else None,
                     "m1": p.iloc[-1] / p.iloc[-22] - 1 if len(p) > 22 else None,
                     "spark": list(p.iloc[-60:]) if len(p) else [],
                     "markets": n_k + n_p, "next": ev[0] if ev else None,
                     "gap": (g.ours.iloc[0] - g.market.iloc[0]) * 100 if len(g) else None})
    return pd.DataFrame(rows)


def to_html(ranking, cal, alerts, cover=None, history=None, asof="", nav=None, signal_links=None):
    """Self contained dashboard page. The centrepiece is the gap map: for every live call, our probability and
    the market's on one 0 to 100% scale, so the size and direction of each gap can be read at a glance."""
    import html as h
    history = history or {}
    signal_links = signal_links or {}

    def sig(key, label):
        u = signal_links.get(key)
        return f"<a href='{u}' class='sl'>{label}</a>" if u else label

    def attrs(key, g=None):
        c = COVERAGE.get(key, {})
        return (f" data-group='{h.escape(c.get('group', ''))}' data-region='{h.escape(c.get('region', ''))}'"
                f" data-gap='{'' if g is None or g != g else abs(g):}'")
    css = """
:root{--navy:#010E29;--blue:#1f7ab8;--slate:#8a9bb0;--rust:#c0502e;--paper:#e9eef4;--ink:#1d2430;--muted:#5d6878;--rule:#dfe5ec;--white:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 Lato,Carlito,"Helvetica Neue",Arial,sans-serif;font-variant-numeric:tabular-nums}
a{color:inherit}


main{max-width:1120px;margin:0 auto;padding:34px 24px 64px}
.hero h1{font-size:40px;line-height:1.1;font-weight:800;color:var(--navy);margin:0 0 10px;letter-spacing:-.01em;max-width:18ch}
.hero p{margin:0;color:var(--muted);font-size:17px;max-width:62ch}
.hero .asof{display:block;margin-top:6px;font-size:14px}
h2{font-size:20px;font-weight:800;color:var(--navy);margin:0 0 4px}
.sub{color:var(--muted);font-size:14px;margin:0 0 16px;max-width:70ch}
.map{background:var(--white);border:1px solid #c3cfdc;border-radius:12px;box-shadow:0 1px 2px rgba(27,58,82,.08),0 14px 34px rgba(27,58,82,.16);padding:26px 28px 18px;margin:30px 0 34px}
.axis,.row{display:grid;grid-template-columns:minmax(220px,1.1fr) 2.4fr 140px;gap:24px;align-items:center}
.axis{padding-bottom:6px;border-bottom:1px solid var(--rule);color:var(--muted);font-size:12px}
.ticks{position:relative;height:16px}
.ticks span{position:absolute;transform:translateX(-50%)}
.row{padding:22px 0;border-bottom:1px solid var(--rule)}
.row:last-child{border-bottom:none}
.who b{display:block;font-size:20px;color:var(--navy);line-height:1.2}
.who span{display:block;color:var(--muted);font-size:14px}
.who em{font-style:normal;font-size:13px;color:var(--ink)}
.scale{position:relative;height:44px}
.scale .base{position:absolute;left:0;right:0;top:21px;height:2px;background:#e6ebf1}
.scale .grid{position:absolute;top:12px;bottom:12px;width:1px;background:#edf1f5}
.scale .span{position:absolute;top:18px;height:8px;border-radius:4px;transform-origin:left;animation:grow .9s ease-out both}
.scale .dot{position:absolute;top:13px;width:18px;height:18px;margin-left:-9px;border-radius:50%}
.scale .mkt{border:3px solid var(--slate);background:var(--white)}
.scale .our{background:var(--navy);box-shadow:0 0 0 3px var(--white)}
.scale .lab{position:absolute;top:-6px;font-size:12px;transform:translateX(-50%);white-space:nowrap}
.scale .lab.b{top:34px}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){.scale .span{animation:none}}
.gap{text-align:right}
.gap b{display:block;font-size:34px;font-weight:800;line-height:1}
.gap span{font-size:13px;color:var(--muted)}
.gap small{display:block;font-size:12px;color:var(--muted);margin-top:4px}
.legend{display:flex;gap:22px;font-size:13px;color:var(--muted);margin-top:14px;flex-wrap:wrap}
.legend i{display:inline-block;width:12px;height:12px;border-radius:50%;vertical-align:-1px;margin-right:6px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-bottom:34px}
.panel{background:var(--white);border:1px solid #c3cfdc;border-radius:12px;padding:22px 24px;box-shadow:0 1px 2px rgba(27,58,82,.08),0 12px 28px rgba(27,58,82,.14)}
.tl{list-style:none;margin:0;padding:0 0 0 18px;border-left:2px solid var(--rule)}
.tl li{position:relative;padding:0 0 16px 14px}
.tl li:before{content:"";position:absolute;left:-25px;top:6px;width:10px;height:10px;border-radius:50%;background:var(--white);border:2px solid var(--slate)}
.tl li.key:before{background:var(--blue);border-color:var(--blue)}
.tl .d{font-weight:800;color:var(--navy);font-size:14px}
.tl .d span{font-weight:400;color:var(--muted)}
.tl .e{font-size:15px}
.tl .g{color:var(--muted);font-size:13px}
.tl .cg{font-size:13px;font-weight:800;margin-left:8px}
.al{list-style:none;margin:0;padding:0}
.al li{display:grid;grid-template-columns:64px 1fr;gap:12px;padding:10px 0 10px 12px;border-left:3px solid var(--slate);margin-bottom:8px;background:#f3f6f9;border-radius:0 6px 6px 0}
.al li.Gap{border-color:var(--blue)}.al li.Price{border-color:#c9922f}.al li.Prediction{border-color:#7a5aa8}
.al .t{color:var(--muted);font-size:13px}
.al .x{font-size:14px}
.al .k{font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-weight:700;color:var(--muted);font-size:13px;padding:0 10px 10px;border-bottom:2px solid var(--rule)}
th.n,td.n{text-align:right}
td{padding:12px 10px;border-bottom:1px solid var(--rule);vertical-align:middle}
tr:last-child td{border-bottom:none}
td .nm{font-weight:800;color:var(--navy)}
td .tk{color:var(--muted);font-size:12px;margin-left:6px}
.up{color:#2e7d4f}.dn{color:var(--rust)}
.foot{color:var(--muted);font-size:13px;margin-top:28px;max-width:80ch}
.tbl{overflow-x:auto}
.filters{display:flex;flex-wrap:wrap;gap:22px;align-items:center;background:var(--white);border:1px solid #c3cfdc;border-radius:12px;padding:14px 20px;margin:26px 0 0;box-shadow:0 1px 2px rgba(27,58,82,.08),0 8px 20px rgba(27,58,82,.10);font-size:14px}
.filters label{display:flex;gap:8px;align-items:center;color:var(--muted);font-weight:700}
.filters select{font:inherit;color:var(--ink);border:1px solid #c3cfdc;border-radius:6px;padding:5px 8px;background:#fff}
.filters input[type=range]{accent-color:var(--blue);width:140px}.filters output{color:var(--navy);min-width:1.5ch}
.fn{margin-left:auto;color:var(--muted)}
a.sl{text-decoration:none;border-bottom:1px dotted var(--slate)}a.sl:hover{color:var(--blue)}
@media(max-width:860px){
 .hero h1{font-size:30px}.two{grid-template-columns:1fr}
 .axis{display:none}.row{grid-template-columns:1fr;gap:10px}.gap{text-align:left}
 main{padding:24px 16px 48px}.map{padding:18px 16px}
 .fn{margin-left:0}
}
"""
    def pct(x):
        return "" if x is None or x != x else f"<span class='{'up' if x >= 0 else 'dn'}'>{x:+.1%}</span>"

    def colour(g):
        return "var(--slate)" if abs(g) < 3 else ("var(--blue)" if g > 0 else "var(--rust)")

    today = pd.Timestamp(ranking["date_asof"].iloc[0]) if "date_asof" in ranking and len(ranking) else pd.Timestamp.today().normalize()
    rows = []
    for r in ranking.itertuples():
        o, m, g = r.ours * 100, r.market * 100, r.gap_pts
        lo, hi = min(o, m), max(o, m)
        days = (pd.Timestamp(r.date) - today).days
        # put the two value labels on opposite sides of the line when the dots are close
        lab_o = "lab" if o >= m else "lab b"
        lab_m = "lab b" if o >= m else "lab"
        hist = history.get(r.asset) or []
        trend = sparkline_svg(hist, 120, 26, "#8a9bb0", lo=0, hi=100) if len(hist) > 1 else ""
        rows.append(
            f"<div class='row f'{attrs(r.asset, g)}><div class='who'><b>{sig(r.asset, h.escape(COVERAGE.get(r.asset, {}).get('name', r.asset)))}</b>"
            f"<span>{h.escape(r.event)}</span>"
            f"<em>in {days} days, {pd.Timestamp(r.date):%d %b}, confidence {h.escape(str(getattr(r, 'confidence', '')))}</em></div>"
            f"<div class='scale' role='img' aria-label='Our view {o:.0f}%, market {m:.0f}%'>"
            f"<div class='base'></div>" + "".join(f"<div class='grid' style='left:{t}%'></div>" for t in (25, 50, 75)) +
            f"<div class='span' style='left:{lo:.1f}%;width:{hi - lo:.1f}%;background:{colour(g)}'></div>"
            f"<div class='dot mkt' style='left:{m:.1f}%'></div><div class='dot our' style='left:{o:.1f}%'></div>"
            f"<div class='{lab_o}' style='left:{o:.1f}%;color:var(--navy)'><b>Ours {o:.0f}%</b></div>"
            f"<div class='{lab_m}' style='left:{m:.1f}%;color:var(--muted)'>Market {m:.0f}%</div></div>"
            f"<div class='gap'><b style='color:{colour(g)}'>{g:+.0f}</b><span>pts, {r.label.lower()}</span>"
            f"<small>market {r.change_1w_pts:+.0f} pts this week</small>{trend}</div></div>")
    axis = ("<div class='axis'><div>Event</div><div class='ticks'>" +
            "".join(f"<span style='left:{t}%'>{t}%</span>" for t in (0, 25, 50, 75, 100)) + "</div><div style='text-align:right'>Gap</div></div>")

    gaps = {(a, pd.Timestamp(d)): g for a, d, g in zip(ranking["asset"], ranking["date"], ranking["gap_pts"])} if len(ranking) else {}

    def cal_item(d):  # the gap score sits on the date the call settles
        g = [gaps[(a, d.date)] for a in d.assets if (a, d.date) in gaps]
        gp = f"<span class='cg' style='color:{colour(g[0])}'>gap {g[0]:+.0f} pts</span>" if g else ""
        return (f"<li class='f {'key' if g else ''}' data-group='{h.escape(d.group)}' data-region='{h.escape(d.region)}' "
                f"data-gap='{abs(g[0]) if g else ''}'><div class='d'>{d.date:%a %d %b}<span> in {(d.date - today).days} days</span></div>"
                f"<div class='e'>{h.escape(d.event)}{gp}</div><div class='g'>{h.escape(d.names)}</div></li>")
    tl = "".join(cal_item(d) for d in cal.itertuples())
    al = "".join(
        f"<li class='{a.type.split()[0]}'><div class='t'>{pd.Timestamp(a.date):%d %b}</div>"
        f"<div><div class='x'><b>{h.escape(str(a.asset))}</b> {h.escape(a.text)}</div><div class='k'>{h.escape(a.type)}</div></div></li>"
        for a in alerts.head(8).itertuples())
    cov = ""
    if cover is not None and len(cover):
        trs = "".join(
            f"<tr class='f'{attrs(c.key, c.gap)}><td><span class='nm'>{sig(c.key, h.escape(c.name))}</span><span class='tk'>{h.escape(c.key)}</span></td>"
            f"<td>{h.escape(c.group)}</td><td>{h.escape(c.region)}</td>"
            f"<td class='n'>{'' if c.last is None else f'{c.last:,.2f}'}</td><td class='n'>{pct(c.w1)}</td><td class='n'>{pct(c.m1)}</td>"
            f"<td>{sparkline_svg(c.spark, 130, 28, '#1b3a52')}</td><td class='n'>{c.markets}</td>"
            f"<td>{'' if c.next is None else f'{c.next[1]}, {c.next[0]:%d %b}'}</td>"
            f"<td class='n'>{'' if c.gap is None or c.gap != c.gap else f'<b style=color:{colour(c.gap)}>{c.gap:+.0f}</b>'}</td></tr>"
            for c in cover.itertuples())
        cov = ("<section><h2>Everything we cover</h2><p class='sub'>Price, the last 60 days, how many Kalshi and Polymarket "
               "contracts we link to each name, the next event and the gap where we have a call. Click a name for its signal page.</p><div class='panel tbl'><table>"
               "<tr><th>Name</th><th>Sector</th><th>Region</th><th class='n'>Last</th><th class='n'>1 week</th><th class='n'>1 month</th>"
               f"<th>60 days</th><th class='n'>Linked markets</th><th>Next event</th><th class='n'>Gap, pts</th></tr>{trs}</table></div></section>")

    groups = sorted({v["group"] for v in COVERAGE.values()})
    regions = sorted({v.get("region", "") for v in COVERAGE.values()})
    opt = lambda xs: "".join(f"<option>{h.escape(x)}</option>" for x in xs)  # noqa: E731
    filters = ("<div class='filters' role='group' aria-label='Filters'>"
               f"<label>Sector<select id='fg'><option value=''>All</option>{opt(groups)}</select></label>"
               f"<label>Region<select id='fr'><option value=''>All</option>{opt(regions)}</select></label>"
               "<label>Gap at least <output id='fo'>0</output> pts<input id='fs' type='range' min='0' max='20' step='1' value='0'></label>"
               "<span id='fn' class='fn'></span></div>")
    script = """<script>(function(){
var g=document.getElementById('fg'),r=document.getElementById('fr'),s=document.getElementById('fs'),o=document.getElementById('fo'),n=document.getElementById('fn');
function ok(e){var gv=g.value,rv=r.value,sv=+s.value,eg=e.dataset.group,er=e.dataset.region,gp=e.dataset.gap;
 if(gv&&eg.split('|').indexOf(gv)<0)return false;
 if(rv&&er.split('|').indexOf(rv)<0)return false;
 if(sv>0&&(gp===''||+gp<sv))return false;return true;}
function run(){o.textContent=s.value;var shown=0,all=0;
 document.querySelectorAll('.f').forEach(function(e){var v=ok(e);e.style.display=v?'':'none';if(e.classList.contains('row')){all++;if(v)shown++;}});
 n.textContent=shown+' of '+all+' live calls shown';}
[g,r,s].forEach(function(x){x.addEventListener('input',run);});run();})();</script>"""
    n_week = int((alerts["date"] >= today - pd.Timedelta(days=7)).sum()) if len(alerts) else 0
    lead = (f"{len(ranking)} live calls, {len(cal)} key dates ahead and {n_week} alerts this week. "
            "The line between the dots is the part of the outcome the market has not priced in.")
    links = "".join(f"<a href='{u}' class='{'on' if l == 'Dashboard' else ''}'>{l}</a>" for l, u in (nav or []))
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>ALT/INFO dashboard</title>" + FAVICON + FONTS +
            f"<style>{css}{BAND_CSS}</style></head><body>{band_html(nav, 'Dashboard', next((u for l, u in (nav or []) if l == 'Search'), 'http://127.0.0.1:8000/'))}<main>"
            f"<div class='hero'><h1>Where is the gap largest right now?</h1><p>{h.escape(lead)}"
            f"<span class='asof'>Data as of {h.escape(asof)}</span></p></div>{filters}"
            f"<div class='map'>{axis}{''.join(rows)}<div class='legend'><span><i style='background:var(--navy)'></i>Our probability</span>"
            "<span><i style='border:3px solid var(--slate);background:#fff;width:12px;height:12px'></i>Market probability</span>"
            "<span><i style='background:var(--blue)'></i>Under-priced</span><span><i style='background:var(--rust)'></i>Over-priced</span>"
            "<span><i style='background:var(--slate)'></i>Priced in</span></div></div>"
            f"<div class='two'><section><h2>Upcoming events</h2><p class='sub'>The next two weeks for every name, plus the dates of live calls. Filled dots are the dates live calls settle, with their gap score.</p>"
            f"<div class='panel'><ol class='tl'>{tl}</ol></div></section>"
            f"<section><h2>Alerts</h2><p class='sub'>Gaps above 5 points, prediction market jumps of 10 points, daily price moves above 4%.</p>"
            f"<div class='panel'><ul class='al'>{al}</ul></div></section></div>{cov}"
            "<p class='foot'>Our probabilities come from the event reports; market probabilities from Kalshi and Polymarket. "
            "Satellite inputs in the prototype are illustrative. Not investment advice.</p></main>" + script + "</body></html>")
