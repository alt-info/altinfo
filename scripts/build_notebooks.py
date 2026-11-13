"""Write (and execute) the four notebooks in notebooks/.

The notebooks are ordinary Jupyter notebooks: open them in Jupyter and Run All to refresh.
This script exists so they can also be generated and executed without a Jupyter kernel.
    python scripts/build_notebooks.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)
from nbbuild import run, write_ipynb, to_report_html  # noqa: E402

LIVE = os.path.exists(os.path.join(ROOT, "data", "raw", "prices.csv"))

SETUP = '''
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, matplotlib.pyplot as plt
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))
from altinfo import gap, satellite, earnings, scoring, charts, valuation, eventbeta as eb
from altinfo.charts import NAVY, BLUE, RED, GREY
charts.style()
RAW = ROOT / "data" / "raw"
SNAP = json.load(open(ROOT / "data" / "snapshot_2026-11-09.json"))
LIVE = (RAW / "prices.csv").exists()
print("Mode:", "LIVE (data/raw)" if LIVE else "SNAPSHOT (figures of 9 Nov 2026; run scripts/fetch_data.py for live data)")
def kalshi_live(series):
    """Open Kalshi markets of a series with a mid price (bid/ask midpoint, else last trade)."""
    km = pd.read_csv(RAW / "kalshi_markets.csv")
    m = km[km["series"] == series].copy()
    mid = (m["yes_bid_dollars"] + m["yes_ask_dollars"]) / 2
    tight = (m["yes_ask_dollars"] - m["yes_bid_dollars"]).le(0.10) & m["yes_ask_dollars"].gt(0)
    m["mid"] = mid.where(tight, m["last_price_dollars"])
    return m
def poly_live(pattern):
    pm = pd.read_csv(RAW / "polymarket_markets.csv")
    return pm[pm.question.str.contains(pattern, case=False, na=False, regex=True) & (pm.closed != True)].sort_values("volume", ascending=False)
def live_calls(today="2026-11-10"):
    """The calls registered in the reports, with the market probability updated to the latest live data."""
    calls = pd.DataFrame(SNAP["calls"]).assign(asset=["NVDA", "BRENT"], date=["2026-11-17", "2026-11-30"],
                                                confidence="medium", date_asof=pd.Timestamp(today))
    calls["market_week_ago"] = [SNAP["nvda"]["real"]["polymarket_beat_history"]["2026-11-03"], np.nan]
    if LIVE:
        cd = pd.read_csv(RAW / "kalshi_candles.csv", parse_dates=["date"])
        cd = cd[cd.ticker.str.startswith("KXBRENTMON-26NOV30")].copy()
        cd["strike"] = cd.ticker.str.extract(r"-T([\\d.]+)$")[0].astype(float)
        daily = cd.dropna(subset=["price"]).groupby("date").apply(lambda d: gap.ladder_prob_above(d.strike, d.price, 96), include_groups=False)
        bm = kalshi_live("KXBRENTMON").dropna(subset=["floor_strike", "mid"])
        calls.loc[calls.asset == "BRENT", "market"] = gap.ladder_prob_above(bm.floor_strike, bm.mid, 96)
        calls.loc[calls.asset == "BRENT", "market_week_ago"] = daily.loc[:pd.Timestamp(today) - pd.Timedelta(days=7)].iloc[-1]
        nb_ = poly_live(r"N[Vv][Ii][Dd][Ii][Aa].*beat|NVDA.*beat")
        if len(nb_):
            calls.loc[calls.asset == "NVDA", "market"] = float(nb_["price"].iloc[0])
    return calls
def load_prices():
    p = pd.read_csv(RAW / "prices.csv")
    p["date"] = pd.to_datetime(p["date"], format="mixed").dt.normalize()
    return p.pivot_table(index="date", columns="ticker", values="close").sort_index()
'''


# "Search" is the live app (python server/app.py); an absolute address works both from the server and from a file opened on disk
from altinfo.config import HOST, PORT  # noqa: E402
APP = f"http://{HOST}:{PORT}/"
NAV = [("Search", APP), ("Track record", APP + "track"), ("Event betas", "03_event_betas.html"),
       ("Dashboard", APP + "dashboard"), ("Monitors", "07_monitors.html")]
CURRENT = {"01": "NVIDIA", "02": "Brent", "03": "Event betas", "04": "Track record", "05": "Dashboard", "07": "Monitors"}


def nb(name, cells, execute=True):
    from notes import NOTES
    k = 0
    for i, c in enumerate(cells):  # attach the explanation to the k-th code cell
        if c[0] == "code":
            if k in NOTES.get(name, {}):
                cells[i] = (c[0], c[1], {**c[2], "note": NOTES[name][k]})
            k += 1
    out, _ = run(cells, execute=execute)
    write_ipynb(out, os.path.join("notebooks", name + ".ipynb"))
    title = "ALT/INFO · " + name[3:].replace("_", " ").title()
    with open(os.path.join("notebooks", name + ".html"), "w") as f:
        f.write(to_report_html(out, title, open("notebook.css").read(), NAV, CURRENT.get(name[:2])))
    print("written", name, "(executed)" if execute else "(not executed)")


def code(s):
    return ("code", s.strip("\n"), {"hide": False, "show_stdout": True})


def md(s):
    return ("md", s.strip("\n"))


# =============================================================== 01 NVIDIA
nvda = [
    md("""# NVIDIA Q3 FY2027 Pre-Earnings Preview: the numbers behind the report
Reproduces every quantitative element of the preview of 9 Nov 2026 (results on 17 Nov, after the close).
Layers: **physical** (satellite build-out index, prototype data), **expectations** (Polymarket, Kalshi, consensus),
**attention** (X, prototype), and the **priced-in gap**. Live data are used when `data/raw` exists, otherwise the
snapshot of 9 Nov 2026 printed in the preview."""),
    code(SETUP),
    md("## 1. Stock data and drawdown"),
    code('''
nv = SNAP["nvda"]["real"]
if LIVE:
    px = load_prices()["NVDA"].dropna()
    dd = earnings.drawdown_from_high(px)
else:
    dd = {"last": nv["price_close_2026-11-06"], "high": nv["record_high_oct_2026"], "high_date": "Oct 2026"}
    dd["distance"] = dd["last"] / dd["high"] - 1
stock = pd.Series({"Price": dd["last"], "Record high": dd["high"], "Record date": dd["high_date"],
                   "Distance from record": f"{dd['distance']:.0%}", "Avg. analyst target": nv["analyst_target_avg"],
                   "Upside to target": f"{nv['analyst_target_avg'] / dd['last'] - 1:.0%}"})
stock.to_frame("NVDA")
'''),
    md("## 2. How the stock reacted to the last 8 reports"),
    code('''
if LIVE:
    moves = earnings.next_day_moves(px, earnings.NVDA_REPORTS)
else:
    moves = pd.DataFrame({"quarter": list(nv["next_day_moves_preview"]), "move": list(nv["next_day_moves_preview"].values())})
s = earnings.reaction_summary(moves)
print(f"{s['negative']} of the last {s['reports']} reactions were negative. Average absolute move: {s['avg_abs_move']:.1%}.")
fig, ax = plt.subplots(figsize=(6, 2.6)); charts.bar_moves(moves, ax); plt.show()
'''),
    md("""## 3. Physical layer: Data Center Build-out Index (prototype data)
Each campus is classified from imagery into a construction stage; the index weights stages
(15% site preparation, 40% shell, 60% roof and mechanical, 85% power and cooling, 100% energized)
by planned power capacity. `data/prototype/campuses.csv` is illustrative (42 campuses, 18.6 GW)."""),
    code('''
camp = pd.read_csv(ROOT / "data" / "prototype" / "campuses.csv")
hist = satellite.buildout_history(camp)
hist["index"] = hist["index"].round(3)
display(hist)
fig, ax = plt.subplots(figsize=(6, 2.4)); charts.index_bars(hist, ax); plt.show()
'''),
    md("""**Nowcast.** GW entering fit-out leads revenue by one quarter. A line through the three known pairs
(fit-out at quarter end, revenue of the next quarter) gives a first read of the Q4 revenue that 4.2 GW can support.
Three points are not a model; they show the mechanics the platform runs on a longer history."""),
    code('''
rev = nv["revenue_by_quarter_bn"]              # Q1 FY27, Q2 FY27, Q3 FY27 guidance
x = hist["gw_fit_out"].values[:3]              # fit-out at the end of the previous quarter
y = list(rev.values())
q4, slope, icpt = gap.nowcast(x, y, hist["gw_fit_out"].values[3])
print(f"Revenue per extra GW in fit-out: ${slope:.1f}bn")
print(f"Q4 FY27 revenue supported by {hist['gw_fit_out'].values[3]:.1f} GW: ${q4:.0f}bn "
      f"({q4 / nv['q3_revenue_guidance_bn'] - 1:+.0%} vs Q3 guidance) -> supports a Q4 guide above a 'modest increase'")
'''),
    md("""## 4. Expectations: what is priced in
**Our beat probability.** NVIDIA beat EPS consensus in each of its last 8 reports (verify on the earnings history).
With a uniform prior, Laplace's rule gives (8 + 1) / (8 + 2) = 90%. The physical layer (revenue at or above
guidance) gives no reason to move away from the base rate."""),
    code('''
beats, n = 8, 8
ours = (beats + 1) / (n + 2)
market9 = nv["polymarket"]["EPS above analyst consensus"]       # 9 Nov, as printed in the preview
market = market9
if LIVE:
    cand = poly_live(r"N[Vv][Ii][Dd][Ii][Aa].*beat|NVDA.*beat")
    if len(cand):
        market = float(cand["price"].iloc[0])
        display(pd.DataFrame({"Polymarket market": cand["question"], "Probability": cand["price"].map("{:.0%}".format),
                              "Volume, $": cand["volume"].map("{:,.0f}".format), "Closes": cand["end"].astype(str).str[:10]}).head(3))
v9, v = gap.priced_in_gap(ours, market9), gap.priced_in_gap(ours, market)
print(f"Q3 beat on 9 Nov: ours {ours:.0%} vs Polymarket {market9:.0%} -> gap {v9['gap_pts']:+.0f} pts: {v9['label']}")
if LIVE:
    print(f"Q3 beat today:    ours {ours:.0%} vs Polymarket {market:.0%} -> gap {v['gap_pts']:+.0f} pts: {v['label']}")
'''),
    code('''
bh = pd.Series(nv["polymarket_beat_history"]); bh.index = pd.to_datetime(bh.index)
if LIVE:
    km = kalshi_live("KXEARNINGSMENTIONNVDA")
    km = km[km.volume_fp > 0].sort_values("mid", ascending=False)
    mentions = dict(zip(km.yes_sub_title, km.mid))
else:
    mentions = nv["kalshi_mentions"]
fig, axes = plt.subplots(1, 2, figsize=(9.5, 2.8))
charts.prob_line(bh, axes[0], "POLYMARKET: PROBABILITY NVIDIA BEATS EPS CONSENSUS (9 NOV SNAPSHOT)"); axes[0].set_ylim(70, 100)
axes[0].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%d %b"))
charts.hbar_shares(dict(list(mentions.items())[:8]), ax=axes[1], title="KALSHI: WORDS SAID ON THE CALL" + (" (LIVE)" if LIVE else ""))
plt.tight_layout(); plt.show()
'''),
    code('''
# Where the market sees the stock after the results: Polymarket "close above $X at the end of November"
if LIVE:
    pa = poly_live(r"NVIDIA \\(NVDA\\) close above .* end of November")
    pa = pa.assign(level=pa.question.str.extract(r"\\$(\\d+)")[0].astype(float)).sort_values("level")
    display(pd.DataFrame({"Polymarket market": pa["question"], "Probability": pa["price"].map("{:.0%}".format),
                          "Volume, $": pa["volume"].map("{:,.0f}".format)}))
    p200 = float(pa.loc[pa.level == 200, "price"].iloc[0]) if (pa.level == 200).any() else np.nan
    print(f"Live: P(NVDA closes November above $200) = {p200:.0%} | last close {dd['last']:.2f} -> needs {200 / dd['last'] - 1:+.1%}")
print("9 Nov snapshot: P(close above $200 the day after results) =", f"{nv['polymarket']['Stock closes above $200 the day after results']:.0%}")
'''),
    md("## 5. Attention (prototype: X topics classified by a language model)"),
    code('''
pr = SNAP["nvda"]["prototype"]
fig, ax = plt.subplots(figsize=(6, 2.2))
charts.hbar_shares(pr["x_topics"], pr["x_tone"], ax, "SHARE OF NVIDIA POSTS ON X BY TOPIC, LAST 30 DAYS"); plt.show()
print(f"Stocktwits bullish share: {nv['stocktwits_bullish']['month_ago']:.0%} a month ago -> {nv['stocktwits_bullish']['now']:.0%} now")
'''),
    md("## 6. Scenarios and verdict"),
    code('''
g, band, cons = nv["q3_revenue_guidance_bn"], nv["q3_revenue_guidance_band"], nv["q3_revenue_consensus_bn"]
low = g * (1 - band)
scen = pd.DataFrame({"Q3 revenue": [f"< ${low:.1f}bn", f"${low:.1f} to {cons:.1f}bn", f"${cons:.1f} to 111bn", "> $111bn and strong Q4 guide"],
                     "Likely reaction": ["Sharp fall", "Negative bias", "Flat to modest gain", "Rebound"]},
                    index=["Miss", "In line", "Small beat", "Beat + strong guide"])
display(scen)
print("PRICED-IN GAP  | Q3 beat:", "SMALL (priced in)", "| Q4 guide: POSITIVE (build-out nowcast above a modest increase)")
'''),
    md("""## 7. Costs: memory chip shipments (prototype)
Memory is NVIDIA's largest input cost after wafers. The platform counts memory cargo flown from Korea and Taiwan to the
US server assembly sites; rising volumes with stable memory prices point to easing costs and margins. The cargo series
is illustrative; Micron's share price is the market's real time read on memory prices."""),
    code('''
mc = pd.read_csv(ROOT / "data" / "prototype" / "memory_cargo.csv", parse_dates=["week"]).set_index("week")["memory_cargo_index"]
fig, axes = plt.subplots(1, 2, figsize=(9.5, 2.5))
axes[0].plot(mc.index, mc.values, color=NAVY, lw=1.3); axes[0].set_title("MEMORY CARGO INDEX, WEEKLY (PROTOTYPE)")
axes[0].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b"))
if LIVE:
    mu = load_prices()["MU"].dropna().loc["2026-05-01":]
    axes[1].plot(mu.index, mu.values, color=BLUE, lw=1.3); axes[1].set_title("MICRON (MU) SHARE PRICE, $")
    axes[1].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b"))
plt.tight_layout(); plt.show()
print(f"Memory cargo: {mc.iloc[-1] / mc.iloc[-13] - 1:+.0%} over 3 months"
      + (f" | Micron: {mu.iloc[-1] / mu.iloc[-63] - 1:+.0%} over 3 months" if LIVE else ""))
'''),
    md("""## 8. Valuation: is a beat enough to move the price?
The run-up before the release, multiples against peers and against NVIDIA's own history, and the analysts' targets.
Multiples and targets come from Yahoo Finance (`python scripts/fetch_data.py --reuse` downloads them)."""),
    code('''
if LIVE:
    P = load_prices()
    ru = pd.DataFrame({t: valuation.runup(P[t], asof="2026-11-10") for t in ["NVDA", "SMH", "SPY"] if t in P}).T
    ru.index.name = "Run-up to 10 Nov"
    display(ru.apply(lambda c: c.map("{:+.1%}".format)))
else:
    print("Run-up needs live prices (scripts/fetch_data.py).")
'''),
    code('''
FUND = RAW / "fundamentals.csv"
if FUND.exists():
    fund = pd.read_csv(FUND)
    mult = valuation.multiples(fund, "NVDA", ["AMD", "AVGO", "TSM", "MU", "QCOM", "INTC"])
    view = mult.copy().astype(object)
    for i in view.index:
        view.loc[i] = [("" if v != v else (f"{v:+.0%}" if "vs peers" in i else f"{v:.1f}x")) for v in mult.loc[i]]
    view.columns = ["Forward P/E", "Trailing P/E", "Price / sales", "EV / EBITDA", "PEG"][:len(view.columns)]
    display(view)
    display(valuation.consensus(fund, "NVDA").to_frame("NVDA"))
    eps, mon = pd.read_csv(RAW / "eps_annual.csv"), pd.read_csv(RAW / "monthly_prices.csv")
    pe = valuation.pe_history(mon, eps, "NVDA")
    if len(pe) > 3:
        fig, ax = plt.subplots(figsize=(7, 2.4)); ax.plot(pe.index, pe.values, color=NAVY, lw=1.3)
        ax.axhline(pe.median(), color=GREY, ls=":", lw=0.8); ax.set_title("NVIDIA TRAILING P/E, MONTHLY (DOTTED: MEDIAN)"); plt.show()
        print(f"Trailing P/E now {pe.iloc[-1]:.0f}x against a median of {pe.median():.0f}x since {pe.index[0]:%Y}")
else:
    nv = SNAP["nvda"]["real"]
    print(f"Snapshot of 9 Nov: market cap ${nv['market_cap_tn']}tn, Q3 EPS consensus ${nv['q3_eps_consensus']}, "
          f"average price target ${nv['analyst_target_avg']}.")
    print("Multiples against peers and history: run  python scripts/fetch_data.py --reuse  and rebuild.")
'''),
    md("## 9. Key drivers: what will move the stock, and can our data see it?"),
    code('''
drivers = pd.DataFrame([
    ("Q4 revenue guidance", "The market already prices the Q3 beat; the outlook is the surprise", "Yes", "Build-out Index, GW in fit-out"),
    ("Data centre revenue", "About 90% of revenue; tracks customers' AI campuses", "Yes", "Build-out Index, US assembly sites"),
    ("Gross margin", "Memory and packaging costs squeeze margins", "Partly", "Memory cargo, Micron share price"),
    ("Customer financing", "Top topic on X; debt-funded data centres could slow orders", "No", "Attention on X only"),
    ("China export rules", "Licences decide H20 / H200 sales", "No", "Kalshi words on the call, news"),
], columns=["Driver", "Why it matters", "Can our data see it?", "Signal"])
drivers
'''),
    md("## 10. Risks and sources"),
    code('''
risks = pd.DataFrame([
    ("Satellite stages misread", "Construction stage from imagery can lag the real fit-out", "Cross-check with power connections and heat"),
    ("Customer mix", "Campuses we see may not be the ones buying this quarter", "Weight by announced NVIDIA deployments"),
    ("Market already moved", "Polymarket can reprice in hours after news", "Report shows the live market price"),
    ("Thin prediction markets", "Low volume contracts give noisy probabilities", "Show volume next to every price"),
], columns=["Risk", "What could go wrong", "What we do about it"])
display(risks)
sources = pd.DataFrame([
    ("Share price, peers, Micron", "Yahoo Finance", "Real"), ("Beat probability, price contracts", "Polymarket", "Real"),
    ("Words on the call", "Kalshi", "Real"), ("Guidance, consensus, targets", "NVIDIA release, broker consensus", "Real"),
    ("Build-out Index, GW in fit-out", "Satellite imagery", "Prototype"), ("Memory cargo", "Airport cargo counts", "Prototype"),
    ("Topics on X", "X posts classified by a language model", "Prototype"), ("Stocktwits bullish share", "Stocktwits", "Real, as printed"),
], columns=["Figure", "Source", "Status"])
sources
'''),
]

# =============================================================== 02 Brent
brent = [
    md("""# Brent Pre-Event Preview: the numbers behind the report
OPEC+ meets on 29 Nov 2026; the Kalshi month-end contract settles on 30 Nov. The question: is the US Iran ceasefire
priced in faster than the barrels can arrive? Physical layer: ship tracking (real, Kpler) and tank shadows (prototype).
Expectations: Kalshi price ladder, Hormuz and ceasefire markets, Polymarket WTI ladder. Our probability: scenarios."""),
    code(SETUP),
    md("## 1. Price action"),
    code('''
b = SNAP["brent"]["real"]
if LIVE:
    bz = load_prices()["BZ=F"].dropna()
    last, wk = bz.iloc[-1], bz.iloc[-1] / bz.loc[: bz.index[-1] - pd.Timedelta(days=7)].iloc[-1] - 1
    hi, lo = bz.loc["2026"].max(), bz.loc[bz.index[-1] - pd.Timedelta(days=365):].min()
    fig, ax = plt.subplots(figsize=(7, 2.4)); ax.plot(bz.loc["2026"], color=NAVY, lw=1.2); ax.set_title("BRENT FRONT MONTH, $/BBL"); plt.show()
else:
    last, wk, hi, lo = b["brent_intraday_2026-11-09"], b["brent_week_change"], b["brent_2026_closing_high"], b["brent_52w_low"]
print(f"Brent {last:.2f} | week {wk:+.0%} | {last / hi - 1:+.0%} from 2026 high {hi:.2f} | {last / lo - 1:+.0%} above 52-week low {lo:.2f}")
'''),
    md("## 2. Physical layer: Hormuz flows and storage"),
    code('''
fl = pd.Series(b["hormuz_flow_mbd"])
print(f"October flow {fl.iloc[-1]} mb/d: {fl.iloc[-1] / fl.iloc[-2] - 1:+.0%} vs Sep, {fl.iloc[-1] / fl.iloc[0] - 1:+.0%} vs pre-war;"
      f" ~{b['ships_waiting']} ships waiting, {b['attacks_since_6_oct']} attacks since 6 Oct")
tanks = satellite.tank_table(pd.read_csv(ROOT / "data" / "prototype" / "tanks.csv"))[["4 weeks ago", "now"]]
tanks["change, pts"] = (tanks["now"] - tanks["4 weeks ago"]) * 100
fig, axes = plt.subplots(1, 2, figsize=(9.5, 2.5))
axes[0].bar(fl.index, fl.values, color=[GREY, BLUE, BLUE], width=0.55); axes[0].set_title("OIL THROUGH HORMUZ, MB/D")
for i, v in enumerate(fl.values): axes[0].text(i, v + 0.2, f"{v}", ha="center", fontsize=7.5, weight="bold", color=NAVY)
t = tanks.sort_values("now")
axes[1].barh(t.index, t["4 weeks ago"] * 100, color="#e6ebf1", height=0.6, label="4 weeks ago")
axes[1].barh(t.index, t["now"] * 100, color=BLUE, height=0.32, label="now"); axes[1].legend(fontsize=7, frameon=False)
axes[1].set_title("TANK FILL FROM SATELLITE SHADOWS, % (PROTOTYPE)")
plt.tight_layout(); plt.show()
tanks.round(2)
'''),
    md("## 3. Expectations: the market's probability"),
    code('''
lad9 = b["kalshi_brent_above"]                       # 9 Nov, as printed in the preview
market9 = gap.ladder_prob_above([float(k) for k in lad9], list(lad9.values()), 96)
market = market9
if LIVE:
    bm = kalshi_live("KXBRENTMON").dropna(subset=["floor_strike", "mid"]).sort_values("floor_strike")
    market = gap.ladder_prob_above(bm.floor_strike, bm.mid, 96)
    # implied distribution of Brent on 30 Nov from the whole ladder
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 2.6))
    x = bm[bm.floor_strike <= 116]
    axes[0].plot(x.floor_strike, x.mid * 100, color=NAVY, marker="o", ms=3); axes[0].axvline(96, color=RED, lw=0.8, ls="--")
    axes[0].set_title("KALSHI: P(BRENT ABOVE LEVEL ON 30 NOV), LIVE"); axes[0].set_xlabel("$/bbl")
    # how the market probability of > $96 moved day by day
    cd = pd.read_csv(RAW / "kalshi_candles.csv", parse_dates=["date"])
    cd = cd[cd.ticker.str.startswith("KXBRENTMON-26NOV30")].copy()
    cd["strike"] = cd.ticker.str.extract(r"-T([\\d.]+)$")[0].astype(float)
    hist = cd.dropna(subset=["price"]).groupby("date").apply(
        lambda d: gap.ladder_prob_above(d.strike, d.price, 96) if len(d) >= 3 else np.nan, include_groups=False).dropna()
    charts.prob_line(hist, axes[1], "KALSHI: P(BRENT > $96 ON 30 NOV), DAILY")
    axes[1].axhline(market9 * 100, color=GREY, lw=0.8, ls=":"); axes[1].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%d %b"))
    plt.tight_layout(); plt.show()
print(f"Kalshi P(Brent > $96 on 30 Nov): {market9:.0%} on 9 Nov (preview), {market:.0%} now")
'''),
    code('''
if LIVE:
    hz = kalshi_live("KXHORMUZNORM").sort_values("close_time")
    hz = dict(zip(hz.yes_sub_title.str.replace("Before ", "").str.replace(", 20", " '"), hz.mid))
    snap9 = {"Ceasefire US x Iran by 30 Nov": 0.60, "Hormuz agreement by 31 Dec": 0.36, "Hormuz normal by 30 Nov": 0.04,
             "No normal traffic in 2026": 0.92}  # values printed in the preview
    pq = {"Ceasefire US x Iran by 30 Nov": r"US x Iran Effective Ceasefire by November 30",
          "Hormuz agreement by 31 Dec": r"US-Iran Hormuz Agreement by December 31",
          "Hormuz normal by 30 Nov": r"Hormuz traffic returns to normal by November 30",
          "No normal traffic in 2026": r"not return to normal in 2026"}
    for k, pat in pq.items():
        r = poly_live(pat)
        print(f"Polymarket  {k}: {r.price.iloc[0]:.0%} now, {snap9[k]:.0%} on 9 Nov" if len(r) else f"Polymarket  {k}: not found")
else:
    hz = b["kalshi_hormuz_normal_by"]
    for k, v in b["polymarket"].items(): print(f"Polymarket  {k}: {v:.0%}")
fig, axes = plt.subplots(1, 2, figsize=(9.5, 2.5))
charts.curve(list(hz), list(hz.values()), axes[0], "KALSHI: HORMUZ TRAFFIC NORMAL BY DATE")
axes[0].tick_params(axis="x", labelsize=6, rotation=45)
wt = b["polymarket_wti_touch"]; charts.ladder([float(k) for k in wt], list(wt.values()), b["wti_2026-11-09"], axes[1], "POLYMARKET: WTI TOUCHES LEVEL BEFORE 1 DEC (9 NOV)")
plt.tight_layout(); plt.show()
'''),
    md("""## 4. Our probability: scenarios
Each scenario has a weight and a price range for 30 Nov (uniform inside the range; the open ended collapse case
is taken as $105 to $115). Weights are analyst inputs informed by the physical layer."""),
    code('''
sc = [gap.Scenario(**s) for s in SNAP["brent"]["prototype"]["scenarios"]]
display(pd.DataFrame([{"scenario": s.name, "weight": s.weight, "range": f"{s.low} to {s.high or 'open'}",
                       "P(> $96 | scenario)": round(s.prob_above(96), 3)} for s in sc]))
ours = gap.scenario_prob_above(sc, 96)
v9, v = gap.priced_in_gap(ours, market9), gap.priced_in_gap(ours, market)
print(f"Registered call, 9 Nov: ours {ours:.0%} vs Kalshi {market9:.0%} -> gap {v9['gap_pts']:+.0f} pts: {v9['label']}")
if LIVE:
    print(f"Today, same weights:    ours {ours:.0%} vs Kalshi {market:.0%} -> gap {v['gap_pts']:+.0f} pts: {v['label']}")
    # which weight on 'deal signed' would make our model agree with the market today (collapse weight kept fixed)?
    c, p_mid = sc[2].weight, sc[1].prob_above(96)
    d_star = 1 - c - (market - c * sc[2].prob_above(96)) / p_mid
    print(f"The market today is consistent with a {d_star:.0%} weight on 'deal signed' (we used {sc[0].weight:.0%}): "
          "either diplomacy moved, or the gap has widened. The analyst reviews the weights before the next update.")
'''),
    md("**Robustness.** How the gap changes with the weights of the deal and collapse scenarios (talks continue takes the rest)."),
    code('''
wd = np.arange(0.10, 0.61, 0.05); wc = np.arange(0.05, 0.41, 0.05)
grid = np.full((len(wc), len(wd)), np.nan)
for i, c in enumerate(wc):
    for j, d in enumerate(wd):
        if c + d < 1:
            s2 = [gap.Scenario(sc[0].name, d, sc[0].low, sc[0].high), gap.Scenario(sc[1].name, 1 - c - d, sc[1].low, sc[1].high),
                  gap.Scenario(sc[2].name, c, sc[2].low, sc[2].high)]
            grid[i, j] = (gap.scenario_prob_above(s2, 96) - market9) * 100
fig, ax = plt.subplots(figsize=(7, 2.8))
im = ax.imshow(grid, cmap="RdBu", vmin=-40, vmax=40, aspect="auto", origin="lower")
ax.set_xticks(range(len(wd))); ax.set_xticklabels([f"{x:.0%}" for x in wd], fontsize=7); ax.set_xlabel("weight: deal signed")
ax.set_yticks(range(len(wc))); ax.set_yticklabels([f"{x:.0%}" for x in wc], fontsize=7); ax.set_ylabel("weight: collapse")
for i in range(len(wc)):
    for j in range(len(wd)):
        if not np.isnan(grid[i, j]):
            ax.text(j, i, f"{grid[i, j]:+.0f}", ha="center", va="center", fontsize=7,
                    color=charts.text_on(im.cmap(im.norm(grid[i, j]))))
ax.grid(False); ax.set_title("GAP VS KALSHI ON 9 NOV, POINTS"); plt.colorbar(im, ax=ax, fraction=0.03); plt.show()
row = grid[list(np.round(wc, 2)).index(0.20)]
flip = wd[np.where(row < 0)[0][0]] if (row < 0).any() else None
print(f"With a 20% collapse weight the gap turns negative only when the deal weight reaches {flip:.0%}" if flip is not None
      else "With a 20% collapse weight the gap stays positive for every deal weight tested")
'''),
    md("## 5. How much does Brent move when the odds move? (event betas, live data only)"),
    code('''
if LIVE:
    poly = pd.read_csv(RAW / "polymarket_history.csv")
    probs = eb.event_probs(poly)
    rets = eb.asset_returns(pd.read_csv(RAW / "prices.csv"))
    cal = rets["SPY"].dropna().index
    sh = eb.event_changes(probs[[c for c in ["hormuz_normal", "us_invades_iran", "iran_regime_falls"] if c in probs]], calendar=cal)
    bb = eb.event_betas(rets[["BZ=F", "XLE", "SPY"]], sh, scale={c: 10 for c in sh})
    display(bb.round(3))
else:
    print("Run scripts/fetch_data.py to estimate Brent's sensitivity to the Hormuz and Iran markets.")
'''),
    md("## 6. Attention (prototype)"),
    code('''
pr = SNAP["brent"]["prototype"]
fig, ax = plt.subplots(figsize=(6, 2.3)); charts.hbar_shares(pr["x_topics"], pr["x_tone"], ax, "SHARE OF OIL POSTS ON X BY TOPIC, LAST 7 DAYS"); plt.show()
print("PRICED-IN GAP | Ceasefire: PRICED IN | Supply gap: UNDER-PRICED")
'''),
    md("""## 7. Pricing: futures curve, physical premium and official data
How far the price sits from its range is in section 1. Here: the gap between near and later futures contracts
(backwardation means the market pays up for barrels now), the premium of a physical Gulf grade over Brent, the spread
to WTI, the official weekly stocks and the EIA outlook."""),
    code('''
rows = {}
if LIVE:
    P = load_prices()
    sp = (P["BZ=F"] - P["CL=F"]).dropna()
    rows["Brent minus WTI, $/bbl"] = f"{sp.iloc[-1]:.2f} (3 month average {sp.iloc[-63:].mean():.2f})"
rows["Murban minus Brent, 9 Nov, $/bbl"] = f"{b['murban_2026-11-09'] - b['brent_intraday_2026-11-09']:+.2f} (physical Gulf grade, proxy for cargo premiums)"
e = b["eia_week_to_2026-10-30"]
rows["US commercial crude stocks, week to 30 Oct"] = f"{e['commercial_crude_mb']} mb, {e['crude_vs_5y']:+.0%} vs 5 year average"
rows["US distillate stocks vs 5 year average"] = f"{e['distillates_vs_5y']:+.0%}"
rows["US refinery utilisation"] = f"{e['refinery_utilisation']:.1%}"
for k, v in b["eia_steo_2026-10-06"].items():
    rows[f"EIA outlook (6 Oct): {k}"] = f"{v}"
pd.Series(rows).to_frame("Brent pricing")
'''),
    code('''
CURVE = RAW / "futures_curve.csv"
if CURVE.exists() and len(pd.read_csv(CURVE)):
    fc = pd.read_csv(CURVE, parse_dates=["date"])
    s = valuation.curve_spread(fc, "BZ", 1, 6)
    lc = valuation.latest_curve(fc, "BZ")
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 2.6))
    axes[0].plot(range(len(lc)), lc.values, color=NAVY, marker="o", ms=3)
    axes[0].set_xticks(range(len(lc))); axes[0].set_xticklabels([pd.Period(m).strftime("%b %y") for m in lc.index], rotation=45, fontsize=6.5)
    axes[0].set_title("BRENT FUTURES CURVE TODAY, $/BBL")
    axes[1].plot(s.index, s["spread"], color=BLUE, lw=1.3); axes[1].axhline(0, color=GREY, lw=0.8)
    axes[1].set_title(f"SPREAD {pd.Period(s.attrs['near_month']).strftime('%b').upper()} MINUS {pd.Period(s.attrs['far_month']).strftime('%b').upper()}, $/BBL")
    axes[1].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%d %b"))
    plt.tight_layout(); plt.show()
    print(f"Near minus 6th contract: {s['spread'].iloc[-1]:+.2f} $/bbl ->",
          "backwardation: the market still pays for prompt barrels" if s["spread"].iloc[-1] > 0 else "contango: prompt supply looks ample")
else:
    print("Futures curve: run  python scripts/fetch_data.py --reuse  (downloads the next 12 Brent and WTI contracts) and rebuild.")
'''),
    md("## 8. Key drivers: what will move Brent this month, and can our data see it?"),
    code('''
pd.DataFrame([
    ("US Iran deal", "A signed deal sends tankers back through Hormuz", "Partly", "Polymarket and Kalshi odds, tanker flow"),
    ("Hormuz tanker flow", "Still about 19% below pre-war: the barrels are not back yet", "Yes", "Ship tracking, ships waiting"),
    ("OPEC+ on 29 Nov", "Quota decision for 2027", "No", "Calendar only"),
    ("Storage draws", "Hubs drawing down replace lost Gulf supply", "Yes", "Tank fill from shadows, EIA weekly"),
    ("Fed and dollar", "A stronger dollar weighs on oil", "No", "Kalshi Fed markets (event betas)"),
], columns=["Driver", "Why it matters", "Can our data see it?", "Signal"])
'''),
    md("## 9. Risks and sources"),
    code('''
display(pd.DataFrame([
    ("Deal signed quickly", "Our 'talks continue' weight is too high", "Robustness grid in section 4"),
    ("Dark fleet", "Tankers with transponders off are missed by ship tracking", "Radar imagery in production"),
    ("Shadow readings", "Cloud and low sun angle add noise to tank fills", "Average several images, compare with EIA"),
    ("Thin Kalshi ladder", "Few trades at some strikes", "Interpolate across the whole ladder, show volume"),
], columns=["Risk", "What could go wrong", "What we do about it"]))
pd.DataFrame([
    ("Brent, WTI, futures curve", "Yahoo Finance (ICE, NYMEX)", "Real"), ("Price ladder, Hormuz markets", "Kalshi", "Real"),
    ("Ceasefire and WTI markets", "Polymarket", "Real"), ("Hormuz flow, ships waiting", "Kpler ship tracking", "Real, as printed"),
    ("US stocks, outlook", "EIA weekly report and STEO", "Real"), ("Murban price", "ADNOC / ICE Futures Abu Dhabi", "Real, as printed"),
    ("Tank fill", "Satellite shadows", "Prototype"), ("Topics on X", "X posts classified by a language model", "Prototype"),
    ("Scenario weights", "Analyst inputs", "Our view"),
], columns=["Figure", "Source", "Status"])
'''),
]

# =============================================================== 03 event betas
betas = [
    md("""# Event betas: how asset prices respond to prediction market odds
Requires live data (`python scripts/fetch_data.py`). For each asset and event:
r = a + b · (Δp / 10) + e, Newey West errors, changes measured between NYSE trading days."""),
    code(SETUP),
    code('''
kal = pd.read_csv(RAW / "kalshi_fed.csv"); poly = pd.read_csv(RAW / "polymarket_history.csv")
rets = eb.asset_returns(pd.read_csv(RAW / "prices.csv")); cal = rets["SPY"].dropna().index
MEET = {"25JUL": "2025-07-30", "25SEP": "2025-09-17", "25OCT": "2025-10-29", "25DEC": "2025-12-10", "26JAN": "2026-01-28",
        "26MAR": "2026-03-18", "26APR": "2026-04-29", "26JUN": "2026-06-17", "26JUL": "2026-07-29", "26SEP": "2026-09-16",
        "26OCT": "2026-10-28", "26DEC": "2026-12-09", "27JAN": "2027-01-27", "27MAR": "2027-03-17"}
fed = eb.fed_expected_move(kal, MEET, calendar=cal)
probs = eb.event_probs(poly)
EV = [e for e in ["us_invades_iran", "hormuz_normal", "iran_regime_falls", "china_invades_taiwan", "us_recession_2026"] if e in probs]
shocks = eb.event_changes(probs[EV], calendar=cal); shocks["fed_move"] = fed["dE"]
UNITS = {e: 10.0 for e in shocks}
ASSETS = [a for a in ["NVDA", "SMH", "TSM", "SPY", "QQQ", "VGK", "EEM", "EWT", "TLT", "HYG", "GLD", "BZ=F", "XLE", "ITA", "JETS", "UUP", "^TNX", "^VIX"] if a in rets]
br = eb.event_betas(rets[ASSETS], shocks, scale=UNITS)
LAB = {"us_invades_iran": "US invades Iran", "hormuz_normal": "Hormuz reopens", "iran_regime_falls": "Iran regime falls",
       "china_invades_taiwan": "China invades Taiwan", "us_recession_2026": "US recession 2026", "fed_move": "Fed move (+10bp)"}
pd.DataFrame({"Event": [LAB[c] for c in shocks.columns], "Trading days with data": shocks.notna().sum().values})
'''),
    code('''
piv = br.pivot(index="asset", columns="event", values="beta").reindex(index=ASSETS)
tv = br.pivot(index="asset", columns="event", values="t").reindex(index=ASSETS, columns=piv.columns)
fig, ax = plt.subplots(figsize=(9, 5.5))
im = ax.imshow(tv.clip(-4, 4).values, cmap="RdBu", vmin=-4, vmax=4, aspect="auto")
for i in range(piv.shape[0]):
    for j in range(piv.shape[1]):
        v, t = piv.iat[i, j], tv.iat[i, j]
        if not np.isnan(v):
            col = charts.text_on(im.cmap(im.norm(np.clip(t, -4, 4))))
            ax.text(j, i, f"{v:+.2f}{'**' if abs(t) > 2.58 else '*' if abs(t) > 1.96 else ''}", ha="center", va="center",
                    fontsize=7.5, color=col, weight="bold" if abs(t) > 1.96 else "normal")
ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels([LAB.get(c, c) for c in piv.columns], rotation=30, ha="right", fontsize=7)
ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels(piv.index, fontsize=7); ax.grid(False)
plt.colorbar(im, ax=ax, fraction=0.03, label="t statistic"); ax.set_title("EVENT BETAS: % RETURN PER +10 PTS (FED: +10BP)"); plt.show()
'''),
    code('''
# Out of sample: fit on the first 60% of days, predict returns on days when an event moved 5+ points
X = shocks.div(pd.Series(UNITS)).fillna(0); common = rets[ASSETS].index.intersection(X.index)
Y, X = rets[ASSETS].loc[common], X.loc[common]; cut = common[int(len(common) * 0.6)]
pv, rv = [], []
for a in ASSETS:
    y = Y[a]; m = y.notna(); tr, te = m & (y.index < cut), m & (y.index >= cut)
    coef = np.linalg.lstsq(np.column_stack([np.ones(tr.sum()), X[tr].values]), y[tr].values, rcond=None)[0]
    p = coef[0] + X[te].values @ coef[1:]; big = (X[te].abs().max(axis=1) * 10 >= 5).values
    pv += list(p[big]); rv += list(y[te].values[big])
pv, rv = np.array(pv), np.array(rv)
print(f"Out of sample from {cut:%d %b %Y}: sign hit rate {(np.sign(pv) == np.sign(rv)).mean():.0%}, correlation {np.corrcoef(pv, rv)[0, 1]:.2f}")
'''),
    md("""**Reading.** In sample, several betas are significant (for example oil and energy stocks on the Hormuz and Iran
markets). Out of sample, betas estimated before January 2026 do not predict returns on later event days: the relation
changes as the war evolves. Event betas are therefore used as a **risk map** (what a portfolio is exposed to today,
re-estimated on rolling windows), not as a trading signal. The edge of the platform comes from the physical layer."""),
    code('''
PORT = {"US 60/40": {"SPY": .6, "TLT": .4}, "AI growth": {"QQQ": .5, "NVDA": .15, "SMH": .15, "EWT": .1, "TLT": .1},
        "Energy tilt": {"SPY": .45, "XLE": .25, "BZ=F": .1, "TLT": .2}}
expo = pd.DataFrame({p: eb.portfolio_exposure(br, {a: w for a, w in v.items() if a in ASSETS}) for p, v in PORT.items()}).T
SCEN = {"Deal signed": {"hormuz_normal": 25, "us_invades_iran": -15}, "Talks collapse": {"hormuz_normal": -20, "us_invades_iran": 20}}
for s, d in SCEN.items():
    expo[s] = [eb.scenario(expo.loc[p], {k: v for k, v in d.items() if k in expo}, UNITS) for p in expo.index]
view = expo.rename(columns=LAB).apply(lambda c: c.map("{:+.2f}".format))
view.index.name = "Portfolio (% per +10 pts; scenarios in %)"
view
'''),
]

# =============================================================== 04 track record
track = [
    md("""# Track record
Every preview ends with a probability that can be checked. After the event, fill in `outcome` (1 or 0) and rerun:
the Brier score compares our calls with the market's. Skill above 0 means we beat the market."""),
    code(SETUP),
    code('''
calls = pd.DataFrame(SNAP["calls"])
# Fill in after the events, e.g.:
# calls.loc[calls.event.str.startswith("NVDA"), "outcome"] = 1   # EPS above consensus on 17 Nov
# calls.loc[calls.event.str.startswith("Brent"), "outcome"] = 0  # Kalshi settlement on 30 Nov
scored, summary = scoring.track_record(calls)
# Brier scores exist only once an event has resolved: until then the row shows "pending"
view = pd.DataFrame({
    "Event": scored["event"],
    "Our probability": scored["ours"].map("{:.0%}".format),
    "Market probability": scored["market"].map("{:.0%}".format),
    "Market source": scored["source_market"],
    "Outcome": scored["outcome"].map(lambda o: "pending" if o is None or o != o else ("yes" if o == 1 else "no")),
    "Brier, ours": scored.get("brier_ours", pd.Series(index=scored.index, dtype=float)).map(lambda x: "pending" if x != x else f"{x:.3f}"),
    "Brier, market": scored.get("brier_market", pd.Series(index=scored.index, dtype=float)).map(lambda x: "pending" if x != x else f"{x:.3f}"),
})
display(view)
print(f"Resolved calls: {summary['resolved']} of {len(calls)}. Brier scores appear after NVIDIA reports (17 Nov) and Kalshi settles Brent (30 Nov).")
'''),
    code('''
# Until then: what each possible outcome would do to the score (the two calls of 9 Nov 2026)
rows = []
for o1 in (0, 1):
    for o2 in (0, 1):
        c = calls.copy(); c["outcome"] = [o1, o2]
        _, s = scoring.track_record(c)
        rows.append({"NVIDIA beats": "yes" if o1 else "no", "Brent above $96": "yes" if o2 else "no",
                     "Brier, ours": round(s["brier_ours"], 3), "Brier, market": round(s["brier_market"], 3),
                     "Skill vs market": round(s["skill_vs_market"], 2)})
pd.DataFrame(rows)
'''),
]

nb("01_nvda_preview", nvda)
nb("02_brent_preview", brent)
nb("03_event_betas", betas, execute=LIVE)
nb("04_track_record", track)

# =============================================================== 05 dashboard
dash = [
    md("""# Dashboard: where is the gap largest right now?
Gap ranking, calendar of the next events and alerts feed, built from the live data and the calls in the reports.
The same tables feed the web dashboard; `dashboard.html` is a static export."""),
    code(SETUP),
    code("""
from altinfo import dashboard
today = pd.Timestamp("2026-11-10")
calls = live_calls(today)
rank = dashboard.gap_ranking(calls)
view = rank[["asset", "event", "date", "ours", "market", "gap_pts", "label", "confidence", "change_1w_pts"]].copy()
for c in ["ours", "market"]:
    view[c] = view[c].map("{:.0%}".format)
for c in ["gap_pts", "change_1w_pts"]:
    view[c] = view[c].map("{:+.0f}".format)
view.columns = ["Asset", "Event", "Date", "Our view", "Market", "Gap, pts", "Label", "Confidence", "Market 1w, pts"]
view
"""),
    code("""
cal = dashboard.upcoming(today, days=14, live_calls=list(calls.asset))
cal.assign(date=cal.date.dt.strftime("%a %d %b"))[["date", "event", "names", "group"]].rename(
    columns={"date": "Date", "event": "Event", "names": "Names", "group": "Sector"})
"""),
    code("""
jumps = None
if LIVE:
    ph = pd.read_csv(RAW / "polymarket_history.csv", parse_dates=["date"])
    ph = ph[ph.key.fillna("") != ""]
    from altinfo.monitors import market_jumps
    jumps = market_jumps(ph[ph.date >= today - pd.Timedelta(days=60)], threshold_pts=10)
    px = load_prices()
else:
    px = None
alerts = dashboard.alerts_feed(rank, jumps, px, since=today - pd.Timedelta(days=30))
alerts.head(15)
"""),
    code("""
sparks = {}
km = pd.read_csv(RAW / "kalshi_markets.csv") if LIVE else None
pm = pd.read_csv(RAW / "polymarket_markets.csv") if LIVE else None
bh = SNAP["nvda"]["real"]["polymarket_beat_history"]
sparks["NVDA"] = [v * 100 for v in bh.values()]
if LIVE:
    cd = pd.read_csv(RAW / "kalshi_candles.csv", parse_dates=["date"])
    cd = cd[cd.ticker.str.startswith("KXBRENTMON-26NOV30")].copy()
    cd["strike"] = cd.ticker.str.extract(r"-T([\\d.]+)$")[0].astype(float)
    daily = cd.dropna(subset=["price"]).groupby("date").apply(lambda d: gap.ladder_prob_above(d.strike, d.price, 96), include_groups=False)
    sparks["BRENT"] = list(daily.values * 100)
cover = dashboard.coverage_table(px, km, pm, calls, today) if px is not None else None
from altinfo.config import HOST, PORT
APP = f"http://{HOST}:{PORT}/"   # the live search app (python server/app.py)
NAVD = [("Search", APP), ("Track record", APP + "track"), ("Event betas", "notebooks/03_event_betas.html"),
        ("Dashboard", APP + "dashboard"), ("Monitors", "notebooks/07_monitors.html")]
from altinfo.coverage import COVERAGE
links = {k: f"signals/{k}.html" for k in COVERAGE}
html = dashboard.to_html(rank, cal, alerts, cover, sparks, asof=f"{today:%d %B %Y}", nav=NAVD, signal_links=links)
(ROOT / "dashboard.html").write_text(html)
print("written dashboard.html")
"""),
    md("""## Signal pages
One page per covered name with the history of each index, how the prediction market odds moved, attention on X and
the supply chain map with live alerts, linked from the dashboard (click a name)."""),
    code("""
from altinfo import signals
(ROOT / "signals").mkdir(exist_ok=True)
REPORTS = {"NVDA": "../notebooks/01_nvda_preview.html", "BRENT": "../notebooks/02_brent_preview.html"}
NAVS = [(l, u if u.startswith("http") else "../" + u) for l, u in NAVD]
rows = []
for k in COVERAGE:
    sig = signals.collect(k, ROOT, today)
    (ROOT / "signals" / f"{k}.html").write_text(signals.page_html(k, sig, NAVS, REPORTS.get(k), f"{today:%d %B %Y}"))
    rows.append({"Name": COVERAGE[k]["name"], "Charts": len(sig["charts"]), "Places on the map": len(COVERAGE[k]["sites"]),
                 "Live alerts": len(sig["alerts"]), "Page": f"signals/{k}.html"})
pd.DataFrame(rows)
"""),
    md("""## Free and Institutional tiers
What each tier sees. The free tier never shows live satellite readings; reports are released to it after each event."""),
    code("""
from altinfo import tiers
tiers.table()
"""),
]

# =============================================================== 06 ticker search
search_nb = [
    md("""# Ticker search: alternative data for any company or commodity
Type a ticker or a commodity and get one page, like Yahoo Finance for alternative data: price, every linked prediction
market on Kalshi and Polymarket, the gap and the next event, analyst consensus (companies) or the futures curve
(commodities), linked assets, the history of each satellite index, the supply chain map with live alerts and attention
on X. Any signal can be turned into a monitor. Ten names are covered: NVIDIA, Brent, WTI, copper, gold, corn, wheat,
soybeans, coffee and sugar."""),
    code(SETUP),
    code("""
from altinfo.search import ticker_page
px = load_prices() if LIVE else pd.DataFrame()
km = pd.read_csv(RAW / "kalshi_markets.csv") if LIVE else None
pm = pd.read_csv(RAW / "polymarket_markets.csv") if LIVE else None
calls = live_calls()
from altinfo import tiers
def show(query, tier="Institutional"):
    from altinfo.search import to_html
    page = ticker_page(query, px, km, pm, calls=calls, today="2026-11-10", root=ROOT)
    display(HTML(to_html(tiers.ticker_page_for(page, tier), query)))
show("NVDA")
"""),
    code("""
show("Brent")
"""),
    code("""
show("copper")
"""),
    md("""## Agriculture
Corn, wheat, soybeans, coffee and sugar. Physical evidence: rain and temperature in the key growing regions against the
10 year normal (Open-Meteo, free) and crop condition from imagery (paid, not in the prototype). Expectations: futures
prices; Kalshi listed crop contracts in April 2026 and withdrew them, so they appear only if they are relisted."""),
    code("""
show("corn")
"""),
    code("""
show("coffee")
"""),
    md("""## The same page in the free tier
No live satellite readings, no supply chain alerts and no gap score; prices, prediction markets, attention and the
calendar stay visible."""),
    code("""
show("NVDA", tier="free")
"""),
]

# =============================================================== 07 monitors
mon = [
    md("""# Personalized monitors
A monitor has four building blocks: **what to watch** (sites of a company, a commodity or a portfolio),
**which signal** (disasters near a site, activity from imagery, prediction market moves), **when to trigger**
(threshold, change against normal, combination) and **what happens** (alert, short report, watchlist).

Example from the product description: a fund holding copper miners is alerted if a disaster hits within 30 km of a
mine producing more than 10% of a company's output **and** activity at the site falls more than 20% below its
4 week average. Mine coordinates are approximate public locations; output shares and activity series are illustrative.
Free feeds keep monitors cheap: USGS earthquakes and NASA FIRMS fires are checked live below."""),
    code(SETUP),
    code("""
from altinfo import monitors
from altinfo.coverage import COPPER_MINES
mines = pd.DataFrame(COPPER_MINES)
mines["owners"] = mines["owners"].map(lambda d: ", ".join(f"{k} {v:.0%} of output" for k, v in d.items()))
mines[["site", "country", "lat", "lon", "owners"]].rename(columns={"site": "Mine", "country": "Country", "lat": "Latitude",
                                                                    "lon": "Longitude", "owners": "Company exposure (illustrative)"})
"""),
    md("## 1. Live check: earthquakes of the last 30 days near the mines (USGS feed)"),
    code("""
qf = RAW / "usgs_quakes.csv"
quakes = pd.read_csv(qf, parse_dates=["time"]) if qf.exists() else pd.DataFrame(columns=["time", "mag", "place", "lat", "lon"])
print(f"{len(quakes)} earthquakes M4.5+ in the last 30 days")
for r in (30, 150, 300):
    near = monitors.disasters_near(COPPER_MINES, quakes, radius_km=r)
    print(f"within {r:>3} km of a watched mine: {len(near)}")
nq = monitors.disasters_near(COPPER_MINES, quakes, radius_km=300).sort_values("km").head(10)
nq.assign(time=pd.to_datetime(nq["time"], utc=True).dt.strftime("%d %b %Y %H:%M")).rename(columns={"site": "Mine", "time": "Time (UTC)", "mag": "Magnitude",
                                                                         "km": "Distance, km", "place": "Location"})
"""),
    md("""## 2. Replay: the Grasberg mud rush (September 2025)
On 8 September 2025 a mud rush at Freeport's Grasberg Block Cave stopped operations at one of the world's largest
copper mines. No earthquake was involved, so the monitor fires on the activity leg. The activity series is a
prototype (trucks and staff parking counted from imagery); prices are real."""),
    code("""
days = pd.date_range("2025-06-01", "2025-11-30")
rng = np.random.default_rng(3)
act = pd.Series(100 + rng.normal(0, 4, len(days)), index=days)
act.loc["2025-09-09":] = act.loc["2025-09-09":] * 0.45          # operations halted after the mud rush
activity = {"Grasberg": act}
chg = monitors.activity_drop(act)
first = chg[chg <= -0.20].index[0]
print("Activity first more than 20% below its 4 week average on", first.date())
px = load_prices() if LIVE else pd.DataFrame()
m = monitors.Monitor("Copper supply disruption", COPPER_MINES, monitors.copper_rule)
alerts = m.run(activity=activity, prices=px, asof=first, horizon=first + pd.Timedelta(days=30))
alerts.rename(columns={"level": "Level", "site": "Mine", "country": "Country", "trigger": "Trigger", "output_at_risk": "Output at risk",
                       "moves_since": "Price move, next 30 days", "likely_gain": "Likely to gain", "likely_lose": "Likely to lose",
                       "channels": "Sent by"})
"""),
    code("""
if LIVE and {"FCX", "HG=F"} <= set(px.columns):
    w = px[["FCX", "HG=F"]].loc["2025-08-15":"2025-10-31"].dropna(how="all").ffill()
    w = w / w.loc[:first].iloc[-1] * 100
    fig, ax = plt.subplots(figsize=(7, 2.6))
    ax.plot(w.index, w["FCX"], color=RED, label="Freeport (FCX)"); ax.plot(w.index, w["HG=F"], color=BLUE, label="Copper futures")
    ax.axvline(first, color=GREY, ls="--", lw=0.8); ax.legend(frameon=False, fontsize=7)
    ax.set_title("REBASED TO 100 ON THE ALERT DAY"); plt.show()
else:
    print("Run scripts/fetch_data.py --reuse to download FCX and copper futures.")
"""),
    md("## 3. Prediction market monitor: alert when a linked market moves 10 points in a day"),
    code("""
if LIVE:
    ph = pd.read_csv(RAW / "polymarket_history.csv", parse_dates=["date"])
    j = monitors.market_jumps(ph[ph.key.fillna("") != ""], threshold_pts=10).sort_values("date", ascending=False).head(10)
    names = {"us_invades_iran": "US invades Iran before 2027", "hormuz_normal": "Hormuz traffic normal by 31 Dec",
             "iran_regime_falls": "Iranian regime falls in 2026", "china_invades_taiwan": "China invades Taiwan before 2027",
             "us_recession_2026": "US recession in 2026"}
    display(pd.DataFrame({"Date": j["date"].dt.strftime("%d %b %Y"), "Market (Polymarket)": j["key"].map(names),
                          "Probability after": j["prob"].map("{:.0%}".format), "Move, pts": j["move_pts"].map("{:+.0f}".format)}))
"""),
    md("""## 4. Live check: fires near the watched places (NASA FIRMS)
Active fires of the last 7 days from the MODIS satellites, free and updated several times a day. A fire within 30 km
of a mine, a plant or a field is flagged; paid high resolution imagery would then confirm the impact."""),
    code("""
from altinfo.coverage import COVERAGE
ff = RAW / "firms_fires.csv"
fires = pd.read_csv(ff, parse_dates=["time"]) if ff.exists() else None
quakes_all = quakes if len(quakes) else None
if fires is None:
    print("Run  python scripts/fetch_data.py --reuse  to download the NASA FIRMS fires and rebuild.")
else:
    allsites = list({s["site"]: s for v in COVERAGE.values() for s in v["sites"]}.values())  # each place once
    near = monitors.fires_near(allsites, fires, radius_km=30)
    print(f"{len(fires)} fires in the last 7 days within 300 km of a covered place; {near.site.nunique()} places with a fire within 30 km")
    if len(near):
        g = near.groupby("site").agg(fires=("frp", "size"), strongest_mw=("frp", "max"), nearest_km=("km", "min"), last=("time", "max"))
        g["last"] = g["last"].dt.strftime("%d %b %H:%M")
        display(g.sort_values("fires", ascending=False).rename(columns={"fires": "Fires", "strongest_mw": "Strongest, MW",
                "nearest_km": "Nearest, km", "last": "Last seen, UTC"}).rename_axis("Place").head(12))
"""),
    md("""## 5. A portfolio monitor
What to watch can be a whole portfolio: the platform maps each holding to the places it depends on and checks every
signal on them. Example: a fund holding Freeport, Teck, Newmont and copper futures."""),
    code("""
from altinfo.coverage import sites_for_holdings
book = ["FCX", "TECK", "NEM", "copper"]
places = sites_for_holdings(book)
watch = pd.DataFrame(places)[["holding", "site", "role", "country"]]
live = monitors.site_alerts(places, quakes_all, fires)
watch = watch.merge(live.groupby("site")["alert"].apply("; ".join).reset_index(), on="site", how="left").fillna({"alert": "none"})
print(f"{len(book)} holdings -> {watch.site.nunique()} places to watch; {int((watch.alert != 'none').sum())} with a live alert")
watch.rename(columns={"holding": "Holding", "site": "Place", "role": "Role", "country": "Country", "alert": "Live alert"})
"""),
]

nb("05_dashboard", dash)
nb("06_ticker_search", search_nb)
nb("07_monitors", mon)
