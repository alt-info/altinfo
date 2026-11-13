"""Signal histories for every covered name, small SVG charts and the supply chain map.

collect      everything the platform knows about one name: index histories, odds, attention, weather, site alerts
svg_line     line chart as inline SVG (no dependencies)
svg_bars     bar chart as inline SVG
map_html     supply chain map (Leaflet, OpenStreetMap/CARTO tiles; needs an internet connection to show the tiles)
page_html    one signal page per name, linked from the dashboard
"""
import html as h
import json
from pathlib import Path

import pandas as pd

from . import gap, satellite
from .brand import BAND_CSS, FAVICON, FONTS, band_html, logo_svg  # noqa: F401
from .coverage import COVERAGE
from .sources import weather

NAVY, BLUE, RUST, SLATE = "#1b3a52", "#1f7ab8", "#c0502e", "#8a9bb0"
ROLE_COLOURS = {"Supplier": "#1f7ab8", "Assembly": "#0f8b8d", "Customer": "#2e8b57", "Chokepoint": "#c0502e",
                "Export": "#7a5aa8", "Storage": "#c9922f", "Bonded": "#c9922f", "Mine": "#1b3a52", "Production": "#1b3a52",
                "Refining": "#7a5aa8", "Growing": "#2e8b57"}


def _role_colour(role):
    for k, v in ROLE_COLOURS.items():
        if role.startswith(k):
            return v
    return SLATE


# ------------------------------------------------------------------ charts
class _Svg(str):
    """An SVG string that also carries the data it was drawn from (`spec`), for the JSON API."""
    spec = None


def svg_line(x, y, fmt="{:.0f}", w=520, h=170, color=NAVY, ref=None, ref_label=""):
    """Line chart with the first and last date, min and max, and the last value labelled."""
    pts = [(a, float(b)) for a, b in zip(x, y) if b == b]
    if len(pts) < 2:
        return ""
    ys = [b for _, b in pts] + ([ref] if ref is not None else [])
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.12 or abs(hi) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 46, 58, 12, 26
    X = lambda i: L + i * (w - L - R) / (len(pts) - 1)  # noqa: E731
    Y = lambda v: T + (hi - v) / (hi - lo) * (h - T - B)  # noqa: E731
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = f"{X(0):.1f},{h - B} " + line + f" {X(len(pts) - 1):.1f},{h - B}"
    grid = "".join(f"<line x1='{L}' x2='{w - R}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' stroke='#e6ebf1'/>"
                   f"<text x='{L - 6}' y='{Y(v) + 4:.1f}' text-anchor='end'>{h_(fmt.format(v))}</text>"
                   for v in (lo + (hi - lo) * k / 3 for k in (0.5, 1.5, 2.5)))
    lab = lambda d: pd.Timestamp(d).strftime("%d %b %y") if not isinstance(d, str) else d  # noqa: E731
    lx, ly = X(len(pts) - 1), Y(pts[-1][1])
    refl = (f"<line x1='{L}' x2='{w - R}' y1='{Y(ref):.1f}' y2='{Y(ref):.1f}' stroke='{RUST}' stroke-dasharray='4 3'/>"
            f"<text x='{L + 4}' y='{Y(ref) - 4:.1f}' fill='{RUST}'>{h_(ref_label)}</text>") if ref is not None else ""
    out = _Svg(f"<svg viewBox='0 0 {w} {h}' class='chart' role='img'><g font-size='11' fill='#5d6878'>{grid}"
            f"<text x='{L}' y='{h - 6}'>{h_(lab(pts[0][0]))}</text><text x='{w - R}' y='{h - 6}' text-anchor='end'>{h_(lab(pts[-1][0]))}</text></g>"
            f"<polygon points='{area}' fill='{color}' opacity='.07'/>{refl}"
            f"<polyline points='{line}' fill='none' stroke='{color}' stroke-width='2'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='3.5' fill='{color}'/>"
            f"<text x='{lx + 7:.1f}' y='{ly + 4:.1f}' font-size='12' font-weight='700' fill='{color}'>{h_(fmt.format(pts[-1][1]))}</text></svg>")
    out.spec = {"kind": "line", "x": [lab(a) for a, _ in pts], "y": [b for _, b in pts], "fmt": fmt, "ref": ref, "ref_label": ref_label}
    return out


def svg_bars(labels, values, fmt="{:.0f}", w=520, h=170, highlight_last=True, colors=None):
    """Vertical bars with value labels; the last bar is highlighted (latest reading)."""
    v = [float(x) for x in values]
    if not v:
        return ""
    top = max(max(v), 0) * 1.18 or 1
    bot = min(min(v), 0) * 1.18
    L, R, T, B = 10, 10, 18, 30
    n = len(v)
    bw = (w - L - R) / n
    Y = lambda x: T + (top - x) / (top - bot) * (h - T - B)  # noqa: E731
    out = [f"<line x1='{L}' x2='{w - R}' y1='{Y(0):.1f}' y2='{Y(0):.1f}' stroke='#c3cfdc'/>"]
    for i, (lab, x) in enumerate(zip(labels, v)):
        last = highlight_last and i == n - 1
        col = colors[i] if colors else (BLUE if last or not highlight_last else "#dce7f2")
        y0, y1 = sorted((Y(0), Y(x)))
        cx = L + bw * (i + 0.5)
        out.append(f"<rect x='{L + bw * i + bw * 0.18:.1f}' y='{y0:.1f}' width='{bw * 0.64:.1f}' height='{max(y1 - y0, 1):.1f}' "
                   f"rx='3' fill='{col}' stroke='{BLUE}' stroke-width='{0 if colors else 1}'/>"
                   f"<text x='{cx:.1f}' y='{(y0 - 5) if x >= 0 else (y1 + 13):.1f}' text-anchor='middle' font-size='12' "
                   f"font-weight='700' fill='{NAVY}'>{h_(fmt.format(x))}</text>"
                   f"<text x='{cx:.1f}' y='{h - 10}' text-anchor='middle' font-size='11' fill='#5d6878'>{h_(str(lab))}</text>")
    res = _Svg(f"<svg viewBox='0 0 {w} {h}' class='chart' role='img'>{''.join(out)}</svg>")
    res.spec = {"kind": "bars", "x": [str(l) for l in labels], "y": v, "fmt": fmt, "highlight_last": highlight_last, "colors": colors}
    return res


def h_(s):
    return h.escape(str(s))


# ------------------------------------------------------------------ map
_MAP_N = [0]


def map_html(sites, alerts=None, height=330):
    """Supply chain map: one dot per site coloured by role; sites with a live alert get a red ring.
    Leaflet and the map tiles load from the internet; the table below the map works offline."""
    _MAP_N[0] += 1
    mid = f"scmap{_MAP_N[0]}"
    al = {} if alerts is None or not len(alerts) else alerts.groupby("site")["alert"].apply(lambda s: "; ".join(s)).to_dict()
    pts = [{"n": s["site"], "r": s["role"], "c": s.get("country", ""), "la": s["lat"], "lo": s["lon"],
            "col": _role_colour(s["role"]), "a": al.get(s["site"], "")} for s in sites]
    js = f"""
<div id='{mid}' class='scmap' style='height:{height}px'><p class='maplo'>Loading the map (needs an internet connection). The places are listed below.</p></div>
<script>(function(){{
var P={json.dumps(pts)};
function go(){{
 document.getElementById('{mid}').innerHTML='';
 var m=L.map('{mid}',{{scrollWheelZoom:false,worldCopyJump:true}});
 L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{maxZoom:9,
   attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}}).addTo(m);
 var b=[];
 P.forEach(function(p){{
  if(p.a) L.circleMarker([p.la,p.lo],{{radius:13,color:'#c0502e',weight:3,fill:false}}).addTo(m);
  L.circleMarker([p.la,p.lo],{{radius:7,color:'#fff',weight:2,fillColor:p.col,fillOpacity:1}}).addTo(m)
   .bindPopup('<b>'+p.n+'</b><br>'+p.r+', '+p.c+(p.a?'<br><b style="color:#c0502e">'+p.a+'</b>':''));
  b.push([p.la,p.lo]);
 }});
 if(b.length>1) m.fitBounds(b,{{padding:[30,30],maxZoom:6}}); else m.setView(b[0],5);
}}
if(window.L){{go();return;}}
var s=document.getElementById('leaflet-js');
if(!s){{
 var c=document.createElement('link');c.rel='stylesheet';c.href='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';document.head.appendChild(c);
 s=document.createElement('script');s.id='leaflet-js';s.src='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';document.head.appendChild(s);
}}
s.addEventListener('load',go);
}})();</script>"""
    legend = sorted({(p["r"].split(":")[0], p["col"]) for p in pts})
    leg = "".join(f"<span><i style='background:{c}'></i>{h_(r)}</span>" for r, c in legend)
    leg += "<span><i style='background:#fff;border:3px solid #c0502e'></i>Live alert</span>"
    return f"{js}<div class='maplegend'>{leg}</div>"


# ------------------------------------------------------------------ data
def _read(path, **kw):
    return pd.read_csv(path, **kw) if Path(path).exists() else None


def weather_table(wx: pd.DataFrame, regions):
    """Rain over the last 30 days as % of the 10 year normal and the temperature anomaly, one row per region."""
    rows = []
    for r in regions:
        d = wx[wx.region == r]
        a = weather.anomaly(d) if len(d) else None
        if a:
            rows.append({"region": r, "rain_mm": a["rain_mm"], "normal_mm": a["rain_normal_mm"],
                         "rain_pct_normal": a["rain_pct_normal"], "temp_anomaly_c": a["temp_anomaly_c"],
                         "to": a["window_end"]})
    return pd.DataFrame(rows)


def collect(key, root, today="2026-11-10"):
    """Everything the platform knows about one name, from data/raw (live) and data/prototype.

    Returns {"charts": [...], "attention": {...} or None, "weather": DataFrame or None, "alerts": DataFrame}."""
    from .monitors import site_alerts
    root = Path(root)
    raw, proto = root / "data" / "raw", root / "data" / "prototype"
    snap = json.load(open(root / "data" / "snapshot_2026-11-09.json"))
    c = COVERAGE[key]
    charts = []

    def add(title, svg, source, note=""):
        if svg:
            charts.append({"title": title, "svg": svg, "source": source, "note": note, "spec": getattr(svg, "spec", None),
                           "prototype": "rototype" in source})

    if key == "NVDA":
        hist = satellite.buildout_history(pd.read_csv(proto / "campuses.csv"))
        add("Data Center Build-out Index, quarter end", svg_bars(hist.index, hist["index"] * 100, "{:.0f}%"),
            "Prototype satellite data", "How close customers' AI data centres are to receiving chips (0 to 100%).")
        add("GW of data centre capacity in fit-out", svg_bars(hist.index, hist["gw_fit_out"], "{:.1f}"),
            "Prototype satellite data", "Capacity at the stage where chips are installed; leads revenue by about a quarter.")
        mc = _read(proto / "memory_cargo.csv")
        if mc is not None:
            add("Memory cargo index, weekly", svg_line(pd.to_datetime(mc.week), mc.memory_cargo_index, "{:.0f}"),
                "Prototype", "Memory chips flown to US server assembly sites; rising volumes point to easing memory costs.")
        bh = pd.Series(snap["nvda"]["real"]["polymarket_beat_history"])
        add("Polymarket: probability NVIDIA beats EPS consensus", svg_line(pd.to_datetime(bh.index), bh * 100, "{:.0f}%"),
            "Polymarket (9 Nov snapshot)")
    if key == "BRENT":
        cd = _read(raw / "kalshi_candles.csv", parse_dates=["date"])
        if cd is not None:
            cd = cd[cd.ticker.str.startswith("KXBRENTMON-26NOV30")].copy()
            cd["strike"] = cd.ticker.str.extract(r"-T([\d.]+)$")[0].astype(float)
            d = cd.dropna(subset=["price"]).groupby("date").apply(
                lambda g: gap.ladder_prob_above(g.strike, g.price, 96) if len(g) >= 3 else float("nan"), include_groups=False).dropna()
            add("Kalshi: probability Brent closes November above $96", svg_line(d.index, d * 100, "{:.0f}%"), "Kalshi, live")
        fl = snap["brent"]["real"]["hormuz_flow_mbd"]
        add("Oil through the Strait of Hormuz, mb/d", svg_bars(list(fl), list(fl.values()), "{:.1f}"), "Ship tracking (Kpler), as printed in the report")
    if key in ("BRENT", "WTI"):
        tk = satellite.tank_table(pd.read_csv(proto / "tanks.csv"))
        hubs = tk.index if key == "BRENT" else [x for x in tk.index if x in ("Cushing, US", "US Gulf Coast")]
        t = tk.loc[hubs].sort_values("now")
        add("Tank fill from satellite shadows, now", svg_bars([x.split(",")[0].replace(" east coast", "") for x in t.index],
                                                                t["now"] * 100, "{:.0f}%", highlight_last=False),
            "Prototype satellite data", "Capacity weighted fill of floating roof tanks by storage hub.")
    p = _read(raw / "prices.csv")
    if p is not None:
        p = p[p.ticker == c["price"]].copy()
        p["date"] = pd.to_datetime(p["date"], format="mixed")
        p = p.set_index("date")["close"].sort_index().loc[:pd.Timestamp(today)].iloc[-126:]
        add(f"Price, last 6 months ({c['price']})", svg_line(p.index, p.values, "{:,.0f}" if p.max() > 100 else "{:,.2f}", color=BLUE), "Yahoo Finance")

    wx = None
    regions = [s["site"] for s in c["sites"] if s["role"] == "Growing region"]
    w = _read(raw / "weather.csv", parse_dates=["date"])
    if regions and w is not None:
        wx = weather_table(w, regions)
        if len(wx):
            add("Rain over the last 30 days, % of the 10 year normal",
                svg_bars(wx.region, wx.rain_pct_normal * 100, "{:.0f}%", highlight_last=False,
                         colors=[RUST if v < 0.7 else (BLUE if v > 1.3 else SLATE) for v in wx.rain_pct_normal]),
                "Open-Meteo (ERA5), live", "Red: drier than 70% of normal; blue: wetter than 130%.")
    quakes = _read(raw / "usgs_quakes.csv", parse_dates=["time"])
    fires = _read(raw / "firms_fires.csv", parse_dates=["time"])
    alerts = site_alerts(c["sites"], quakes, fires)

    att = None
    if key in ("NVDA", "BRENT"):
        s = snap[key.lower()]
        att = {"topics": s["prototype"]["x_topics"], "tone": s["prototype"]["x_tone"],
               "mentions_vs_90d": s["prototype"].get("x_mentions_vs_90d"),
               "stocktwits": s["real"].get("stocktwits_bullish")}
    return {"charts": charts, "attention": att, "weather": wx, "alerts": alerts,
            "live_sources": {"quakes": quakes is not None, "fires": fires is not None, "weather": w is not None}}


def attention_html(att):
    if not att:
        return "<p class='empty'>No attention data for this name yet.</p>"
    rows = "".join(
        f"<div class='att'><span>{h_(k)}</span><div class='bar'><i style='width:{v * 100 / max(att['topics'].values()) :.0f}%'></i></div>"
        f"<b>{v:.0%}</b><em class='{'dn' if any(x in att['tone'].get(k, '') for x in ('Neg', 'Bear')) else 'up' if any(x in att['tone'].get(k, '') for x in ('Pos', 'Bull')) else ''}'>"
        f"{h_(att['tone'].get(k, ''))}</em></div>" for k, v in att["topics"].items())
    extra = []
    if att.get("mentions_vs_90d"):
        extra.append(f"Posts on X: {att['mentions_vs_90d']:.1f}x the 90 day average")
    if att.get("stocktwits"):
        st = att["stocktwits"]
        extra.append(f"Stocktwits bullish share: {st['month_ago']:.0%} a month ago, {st['now']:.0%} now")
    return rows + "".join(f"<p class='attx'>{h_(e)}</p>" for e in extra) + \
        "<p class='src'>Topic shares and tone: prototype outputs of a language model on X posts.</p>"


SIGNAL_CSS = """
:root{--navy:#010E29;--blue:#1f7ab8;--slate:#8a9bb0;--rust:#c0502e;--paper:#e9eef4;--ink:#1d2430;--muted:#5d6878;--rule:#dfe5ec}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 Lato,Carlito,"Helvetica Neue",Arial,sans-serif}
a{color:var(--blue)}main{max-width:1120px;margin:0 auto;padding:34px 24px 64px}h1{font-size:38px;font-weight:900;color:var(--navy);margin:0 0 8px;line-height:1.1}
.lead{color:var(--muted);margin:0 0 22px;max-width:75ch}.links a{margin-right:18px;font-weight:700}
h2{font-size:19px;color:var(--navy);margin:30px 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:22px}
.card{background:#fff;border:1px solid #c3cfdc;border-radius:12px;padding:18px 20px 14px;box-shadow:0 1px 2px rgba(27,58,82,.08),0 12px 28px rgba(27,58,82,.14)}
.card h3{margin:0 0 2px;font-size:15px;color:var(--navy)}.card p{margin:4px 0 0;color:var(--muted);font-size:13px}
.src{font-size:12px;color:var(--muted);margin:6px 0 0}svg.chart{width:100%;height:auto;display:block;margin-top:8px}
.att{display:grid;grid-template-columns:200px 1fr 46px 110px;gap:12px;align-items:center;padding:6px 0;border-bottom:1px solid var(--rule);font-size:14px}
.att .bar{background:#eef3f8;border-radius:4px;height:10px}.att .bar i{display:block;height:10px;border-radius:4px;background:var(--blue)}
.att em{font-style:normal;font-size:13px}.attx{margin:10px 0 0;font-size:14px}.up{color:#2e7d4f}.dn{color:var(--rust)}
.scmap{border-radius:10px;border:1px solid #c3cfdc;margin-top:6px;background:#eef3f8}
.maplo{margin:0;padding:20px;color:var(--muted);font-size:14px}
.maplegend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--muted);margin:10px 0 0}
.maplegend i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:var(--muted);font-size:13px;padding:0 8px 8px;border-bottom:2px solid var(--rule)}
td{padding:9px 8px;border-bottom:1px solid var(--rule)}td.n,th.n{text-align:right}.empty{color:var(--muted)}
.foot{color:var(--muted);font-size:13px;margin-top:28px}
@media(max-width:700px){main{padding:22px 16px 48px}.grid{grid-template-columns:1fr}.att{grid-template-columns:1fr 60px 40px}.att em{display:none}}
"""


def page_html(key, sig, nav=None, report=None, asof=""):
    """Signal page of one name: index histories, odds, attention and the supply chain map, with a link to the report."""
    c = COVERAGE[key]
    cards = "".join(f"<div class='card'><h3>{h_(x['title'])}</h3>{x['svg']}<p>{h_(x['note'])}</p>"
                    f"<p class='src'>Source: {h_(x['source'])}</p></div>" for x in sig["charts"])
    links = "".join(f"<a href='{u}'>{h_(l)}</a>" for l, u in (nav or []))
    rep = f"<a href='{report}'>Read the full report</a>" if report else "<span class='empty'>No event report for this name yet.</span>"
    wx = ""
    if sig.get("weather") is not None and len(sig["weather"]):
        rows = "".join(f"<tr><td>{h_(r.region)}</td><td class='n'>{r.rain_mm:.0f}</td><td class='n'>{r.normal_mm:.0f}</td>"
                       f"<td class='n'>{r.rain_pct_normal:.0%}</td><td class='n'>{r.temp_anomaly_c:+.1f}</td></tr>"
                       for r in sig["weather"].itertuples())
        wx = ("<h2>Weather in the growing regions</h2><div class='card'><table><tr><th>Region</th><th class='n'>Rain, 30 days, mm</th>"
              f"<th class='n'>Normal, mm</th><th class='n'>% of normal</th><th class='n'>Temperature vs normal, C</th></tr>{rows}</table>"
              f"<p class='src'>Open-Meteo ERA5 reanalysis, 30 days to {sig['weather'].to.max():%d %b %Y}, normal = same window 2015 onwards.</p></div>")
    al = sig["alerts"]
    alt = ("".join(f"<tr><td>{h_(r.site)}</td><td>{h_(r.alert)}</td><td>{pd.Timestamp(r.time):%d %b %H:%M}</td></tr>" for r in al.itertuples())
           if len(al) else "")
    alerts = (f"<table><tr><th>Site</th><th>Live alert</th><th>When (UTC)</th></tr>{alt}</table>" if alt else
              "<p class='empty'>No earthquake within 100 km or fire within 30 km of these sites in the last download.</p>")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{h_(c['name'])} signals</title>{FAVICON}{FONTS}"
            f"<style>{SIGNAL_CSS}{BAND_CSS}</style></head><body>{band_html(nav, None, next((u for l, u in (nav or []) if l == 'Search'), 'http://127.0.0.1:8000/'))}<main>"
            f"<h1>{h_(c['name'])}</h1><p class='lead'>{h_(c['group'])}, {h_(c['region'])}. The history of every index we track for this name, "
            f"how the prediction market odds moved and what people talk about. Data as of {h_(asof)}.</p>"
            f"<p class='links'>{rep}</p><h2>Indices and odds</h2><div class='grid'>{cards}</div>{wx}"
            f"<h2>Attention on X and Stocktwits</h2><div class='card'>{attention_html(sig['attention'])}</div>"
            f"<h2>Supply chain map and live alerts</h2><div class='card'>{map_html(c['sites'], al)}{alerts}</div>"
            "<p class='foot'>Satellite inputs, topic shares and output shares are illustrative prototype data. Not investment advice.</p>"
            "</main></body></html>")
