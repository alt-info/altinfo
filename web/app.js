/* ALT/INFO frontend. It only talks to the backend (/api/...): no source is ever called from the browser.
   Every text coming from outside is written with textContent, never as HTML. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const views = ["start", "loading", "error", "result", "track", "dash"];
  const NAVY = "#010E29", BLUE = "#1f7ab8", RUST = "#c0502e", SLATE = "#8a9bb0";
  let current = 0;   // id of the analysis the page is waiting for; older ones finish in the background, unseen

  // ------------------------------------------------------------ small helpers
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function add(parent, ...kids) { kids.forEach((k) => k && parent.appendChild(k)); return parent; }
  function show(name) {
    views.forEach((v) => { $(v).hidden = v !== name; });
    $("mini").style.visibility = name === "start" ? "hidden" : "visible";   // hidden on the home page, but keeps the header height
    const tab = name === "track" ? "nav-track" : name === "dash" ? "nav-dash" : "nav-search";
    ["nav-search", "nav-track", "nav-dash"].forEach((id) => {
      $(id).classList.toggle("on", id === tab);
      id === tab ? $(id).setAttribute("aria-current", "page") : $(id).removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
  }
  async function api(path, opts) {
    const res = await fetch(path, opts);
    const js = await res.json().catch(() => ({}));
    if (!res.ok) throw (js.error || { message: "The server returned an error." });
    return js;
  }
  const pct = (x, d = 0) => (x === null || x === undefined ? "n/a" : (x * 100).toFixed(d) + "%");
  const signed = (x, d = 1) => (x === null || x === undefined ? "n/a" : (x >= 0 ? "+" : "") + (x * 100).toFixed(d) + "%");
  const num = (x, d = 2) => (x === null || x === undefined ? "n/a" : x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }));
  function pyfmt(spec) {            // "{:.0f}%" from the backend -> a JS formatter
    const m = /\{:(,)?\.(\d)f\}(.*)/.exec(spec || "{:.1f}");
    const d = m ? +m[2] : 1, suf = m ? m[3] : "";
    return (v) => v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: !!(m && m[1]) }) + suf;
  }
  function svg(tag, attrs, text) {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // ------------------------------------------------------------ charts (plain SVG)
  function lineChart(xs, ys, fmt, color) {
    const W = 520, H = 180, L = 50, R = 62, T = 12, B = 26, f = pyfmt(fmt);
    const lo0 = Math.min(...ys), hi0 = Math.max(...ys), pad = (hi0 - lo0) * 0.12 || Math.abs(hi0) * 0.1 || 1;
    const lo = lo0 - pad, hi = hi0 + pad, n = ys.length;
    const X = (i) => L + (i * (W - L - R)) / Math.max(n - 1, 1), Y = (v) => T + ((hi - v) / (hi - lo)) * (H - T - B);
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
    [0.5, 1.5, 2.5].forEach((k) => {
      const v = lo + ((hi - lo) * k) / 3;
      add(s, svg("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: "#e6ebf1" }),
        svg("text", { x: L - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "#56627a" }, f(v)));
    });
    const pts = ys.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    add(s, svg("polygon", { points: `${X(0)},${H - B} ${pts} ${X(n - 1)},${H - B}`, fill: color, opacity: 0.07 }),
      svg("polyline", { points: pts, fill: "none", stroke: color, "stroke-width": 2 }),
      svg("circle", { cx: X(n - 1), cy: Y(ys[n - 1]), r: 3.5, fill: color }),
      svg("text", { x: X(n - 1) + 7, y: Y(ys[n - 1]) + 4, "font-size": 12, "font-weight": 700, fill: color }, f(ys[n - 1])),
      svg("text", { x: L, y: H - 6, "font-size": 11, fill: "#56627a" }, String(xs[0])),
      svg("text", { x: W - R, y: H - 6, "text-anchor": "end", "font-size": 11, fill: "#56627a" }, String(xs[n - 1])));
    return s;
  }
  function barChart(xs, ys, fmt, highlightLast) {
    const W = 520, H = 180, L = 10, R = 10, T = 20, B = 30, f = pyfmt(fmt), n = ys.length;
    const top = Math.max(...ys, 0) * 1.18 || 1, bot = Math.min(...ys, 0) * 1.18, bw = (W - L - R) / n;
    const Y = (v) => T + ((top - v) / (top - bot)) * (H - T - B);
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
    add(s, svg("line", { x1: L, x2: W - R, y1: Y(0), y2: Y(0), stroke: "#c3cfdc" }));
    ys.forEach((v, i) => {
      const y0 = Math.min(Y(0), Y(v)), h = Math.max(Math.abs(Y(v) - Y(0)), 1), cx = L + bw * (i + 0.5);
      const last = highlightLast !== false && i === n - 1;
      add(s, svg("rect", { x: L + bw * i + bw * 0.18, y: y0, width: bw * 0.64, height: h, rx: 3, fill: last || highlightLast === false ? BLUE : "#dce7f2", stroke: BLUE }),
        svg("text", { x: cx, y: v >= 0 ? y0 - 5 : y0 + h + 13, "text-anchor": "middle", "font-size": 12, "font-weight": 700, fill: NAVY }, f(v)),
        svg("text", { x: cx, y: H - 10, "text-anchor": "middle", "font-size": 11, fill: "#56627a" }, String(xs[i]).slice(0, 16)));
    });
    return s;
  }
  function chartCard(title, note, node, status) {
    const c = el("div", "card chart");
    const h = el("h4", null, title);
    if (status && status !== "real") add(h, el("span", "st " + status, status));
    return add(c, h, node, note ? el("p", null, note) : null);
  }

  // ------------------------------------------------------------ sections
  function header(r) {
    const a = r.asset, p = r.price || {};
    const left = el("div");
    const h1 = el("h1", null, a.name);
    add(h1, el("span", "badge " + a.coverage, a.coverage === "full" ? "Full coverage" : "Basic coverage"));
    add(left, h1, el("div", "meta", [a.price_ticker, a.kind, a.group, a.region].filter(Boolean).join(" · ")));
    const px = el("div", "px");
    const cell = (k, v, cls) => { const d = el("div"); add(d, el("span", null, k), el("b", cls, v)); return d; };
    const tone = (x) => (x === null || x === undefined ? "" : x >= 0 ? "up" : "dn");
    add(px, cell("Last", num(p.last)), cell("1 week", signed(p.change_1w), tone(p.change_1w)), cell("1 month", signed(p.change_1m), tone(p.change_1m)),
      cell("From 1y high", signed(p.from_1y_high), tone(p.from_1y_high)));
    const save = el("button", "savebtn", "Save to my tickers"); save.type = "button";
    api("/api/watchlist").then((list) => { if (list.some((w) => w.key === a.key)) { save.textContent = "Saved in my tickers ✓"; save.classList.add("saved"); } }).catch(() => {});
    save.addEventListener("click", async () => {
      if (save.classList.contains("saved")) { history.pushState({}, "", "/track"); return track(); }
      try { await api("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q: a.key }) });
        save.textContent = "Saved in my tickers ✓"; save.classList.add("saved"); } catch (e) { save.textContent = "Could not save"; }
    });
    add(px, save);
    return add(el("div", "head"), left, px);
  }

  function verdict(r) {
    const h = r.headline, c = r.confidence, card = el("div", "card verdict"), main = el("div", "v-main"), side = el("div", "v-side");
    if (h) {
      const key = h.label.split(/[- ]/)[0];
      add(main, el("span", "v-label " + key, h.label.replace("-", " ")), el("div", "v-q", h.question),
        el("p", "v-how", "How we get our number: " + h.method + "."));
      const sc = el("div", "scale"), o = h.ours * 100, m = h.market * 100;
      const colour = Math.abs(h.gap_pts) < 3 ? SLATE : h.gap_pts > 0 ? BLUE : RUST;
      const span = el("div", "span"); span.style.left = Math.min(o, m) + "%"; span.style.width = Math.abs(o - m) + "%"; span.style.background = colour;
      const dm = el("div", "dot mkt"); dm.style.left = m + "%";
      const dn = el("div", "dot our"); dn.style.left = o + "%";
      const lo = el("div", "lab " + (o >= m ? "t" : "b")); lo.style.left = o + "%"; add(lo, el("b", null, "Ours " + pct(h.ours)));
      const lm = el("div", "lab " + (o >= m ? "b" : "t"), "Market " + pct(h.market)); lm.style.left = m + "%";
      add(sc, el("div", "base"), span, dm, dn, lo, lm);
      const ticks = el("div", "ticks"); ["0%", "25%", "50%", "75%", "100%"].forEach((t) => add(ticks, el("span", null, t)));
      add(main, sc, ticks);
      const g = el("div", "v-gap", (h.gap_pts >= 0 ? "+" : "") + Math.round(h.gap_pts)); add(g, el("small", null, "points"));
      add(side, el("div", "k", "The gap"), g, el("p", null, "our probability minus the market's" + (h.venue ? ", " + h.venue : "")));
      if (h.quotes && h.quotes.length > 1) {
        const qv = el("div", "quotes");
        h.quotes.forEach((x) => add(qv, add(el("span"), el("b", null, x.venue + " " + pct(x.prob)), el("small", null, x.how))));
        add(side, qv);
      }
    } else {
      add(main, el("span", "v-label NONE", "NO GAP YET"), el("div", "v-q", "No market probability to compare with"),
        el("p", "v-how", "We show what the data and the price say, but cannot measure how much is priced in."));
      add(side, el("div", "k", "The gap"), add(el("div", "v-gap", "n/a")), el("p", null, "no comparable prediction market"));
    }
    const meter = el("div", "meter"), bar = el("i"); bar.style.width = c.score + "%"; add(meter, bar);
    add(side, el("div", "k", "Confidence"), el("div", "conf", c.level + " · " + c.score + " / 100"), meter);
    if (r.headline && r.headline.closes) add(side, el("div", "next", "Our call settles on " + new Date(r.headline.closes).toLocaleDateString("en-GB", { day: "numeric", month: "short" })));
    if (r.next_event) add(side, el("div", "settle", "Next date: " + r.next_event.event + ", " + new Date(r.next_event.date).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) +
      (r.next_event.days !== null ? " (in " + r.next_event.days + " days)" : "")));
    return add(card, main, side);
  }

  function conclusion(r) {
    const c = el("div", "card concl");
    return add(c, el("h3", null, "In plain words"), el("h2", null, r.conclusion.title), el("p", null, r.conclusion.text.join(" ")));
  }

  function titled(n, title) { const h = el("h3"); add(h, el("b", null, n)); h.appendChild(document.createTextNode(title)); return h; }

  function evidence(r) {
    const e = r.evidence, c = el("div", "card");
    add(c, titled("1", "What the observable data show"), el("p", "sum", e.summary));
    if (e.items.length) {
      const ul = el("ul", "items");
      e.items.forEach((i) => {
        const li = el("li"), arrow = el("span", "arrow " + (i.direction > 0 ? "up" : i.direction < 0 ? "dn" : ""), i.direction > 0 ? "▲" : i.direction < 0 ? "▼" : "●");
        const mid = el("div"), l = el("span", "l", i.label); add(l, el("span", "st " + i.status, i.status)); add(mid, l, el("span", "n", i.note));
        add(ul, add(li, arrow, mid, el("span", "v", i.value)));
      });
      add(c, ul);
    }
    return c;
  }

  function expectations(r) {
    const x = r.expectations, c = el("div", "card");
    add(c, titled("2", "What the market expects"), el("p", "sum", x.summary));
    (x.consensus || []).forEach((k) => { const d = el("div", "kv"); add(c, add(d, el("span", null, k.label), el("b", null, k.value))); });
    if (x.curve) { const d = el("div", "kv"); add(c, add(d, el("span", null, "Futures curve: " + x.curve.shape), el("b", null, x.curve.meaning))); }
    x.contracts.filter((k) => k.kind !== "event" && k.kind !== "mention").slice(0, 4).forEach((k) => {
      add(c, add(el("div", "mk"), el("span", null, k.title + (k.contract && k.contract !== "Yes" ? " (" + k.contract + ")" : "")), el("b", null, pct(k.prob))));
    });
    if (x.contracts.length) {
      const det = el("details"), t = el("table"), hr = el("tr");
      ["Venue", "Market", "Chance", "Closes"].forEach((h, i) => add(hr, el("th", i >= 2 ? "r" : "", h)));
      add(t, hr);
      x.contracts.forEach((k) => {
        const tr = el("tr"), v = el("td"); add(v, el("span", "venue " + k.venue, k.venue));
        add(t, add(tr, v, el("td", null, k.title + (k.contract && k.contract !== "Yes" ? " (" + k.contract + ")" : "")), el("td", "r", pct(k.prob)), el("td", "r", k.closes)));
      });
      add(c, add(det, el("summary", null, "See " + x.contracts.length + " of " + x.n_contracts + " linked contracts"), t));
    }
    return c;
  }

  function attentionBody(c, t) {
    c.textContent = "";
    add(c, el("h3", null, "What the news is saying"), el("p", "sum", (t && t.summary) || "News coverage is not available."));
    if (!t || !t.available) return c;
    const row = el("div", "attrow"), left = el("div"), right = el("div");
    const kv = (k, v) => add(el("div", "kv"), el("span", null, k), el("b", null, v));
    const v = t.volume || [];
    if (t.mode === "headlines") {   // fallback without GDELT: counts and word list tone of the latest headlines
      add(left, kv("Headlines, last 7 days", String(t.count_7d)),
        kv("Tone of the headlines", (t.tone >= 0 ? "+" : "") + t.tone.toFixed(2) + " (" + t.mood + ")"));
      if (v.length > 1) add(left, barChart(v.map((x) => new Date(x.t).toLocaleDateString("en-GB", { day: "numeric", month: "short" })), v.map((x) => x.v), "{:.0f}", false),
        el("p", "m", "Headlines per day. Tone runs from −1 (only negative words) to +1 (only positive)."));
    } else {
      add(left, kv("Coverage, last 7 days", t.ratio !== null ? t.ratio.toFixed(1) + "× normal" : "n/a"),
        kv("Tone, last 7 days", t.tone !== null ? (t.tone >= 0 ? "+" : "") + t.tone.toFixed(1) + " (" + t.mood + ")" : "n/a"),
        kv("Tone, 3 month average", t.tone_3m !== null ? (t.tone_3m >= 0 ? "+" : "") + t.tone_3m.toFixed(1) : "n/a"));
      if (v.length > 5) add(left, lineChart(v.map((x) => x.t), v.map((x) => x.v), "{:.3f}%", NAVY), el("p", "m", "Share of all news articles worldwide that mention it, by day."));
    }
    const ul = el("ul", "heads");
    (t.headlines || []).forEach((hd) => {
      if (!/^https?:\/\//.test(hd.url || "")) return;   // only plain web links from outside data
      const li = el("li"), a = el("a", null, hd.title); a.href = hd.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      add(ul, add(li, a, el("small", null, (hd.domain || "") + (hd.seen ? " · " + hd.seen.slice(6, 8) + "/" + hd.seen.slice(4, 6) : ""))));
    });
    add(right, el("h4", null, "Latest headlines"), ul.children.length ? ul : el("p", "empty", "No English headline in the last week."));
    add(c, add(row, left, right), el("p", "m", "Source: " + t.source + "." + (t.mode === "headlines" ? "" : " Tone runs from about −10 (very negative) to +10 (very positive).")));
    return c;
  }
  function attention(r) {
    const t = r.attention, c = el("div", "card att");
    attentionBody(c, t);
    if (t && t.pending && t.query) {   // GDELT is slow and rate limited: the news card fills in after the analysis
      const me = current, started = Date.now();
      const tick = async () => {
        if (me !== current || !document.body.contains(c)) return;
        try {
          const j = await api("/api/news?q=" + encodeURIComponent(t.query) + "&t=" + encodeURIComponent(t.ticker || ""));
          if (j.state === "done") {
            attentionBody(c, j.result);
            if (!j.result.available) {
              const b = el("button", "ghost", "Try again"); b.type = "button";
              b.addEventListener("click", () => { attentionBody(c, { summary: "Loading the news coverage…" }); setTimeout(tick, 60000 - Math.min(59000, Date.now() - started)); });
              add(c, b);
            }
            return;
          }
        } catch (e) { /* keep waiting */ }
        const s = Math.round((Date.now() - started) / 1000);
        c.querySelector(".sum").textContent = "Loading the news coverage… " + s + " s (the news service allows one request every few seconds)";
        if (s < 240) setTimeout(tick, 3000);
      };
      setTimeout(tick, 300);
    }
    return c;
  }

  function pricedIn(r) {
    const p = r.priced_in, c = el("div", "card");
    add(c, titled("3", "How much is already in the price"), el("p", "sum", p.summary));
    p.items.forEach((k) => { const d = el("div", "kv"); add(c, add(d, el("span", null, k.label), el("b", null, k.value))); });
    return c;
  }

  function gap(r) {
    const g = r.gap, c = el("div", "card");
    add(c, titled("4", "Evidence against expectations"), el("p", "sum", g.summary));
    g.gaps.forEach((x) => {
      const d = el("div", "gapline"), nums = el("div", "nums");
      add(nums, el("span", null, "Ours " + pct(x.ours)), el("span", null, "Market " + pct(x.market)),
        el("b", x.gap_pts >= 0 ? "up" : "dn", (x.gap_pts >= 0 ? "+" : "") + x.gap_pts.toFixed(0) + " pts"));
      const per = (x.quotes || []).map((v) => v.venue + " " + pct(v.prob) + " (" + v.how + ")").join(" · ");
      add(c, add(d, el("div", "q", x.question), nums, el("div", "m", x.method + ". " + (x.venue || "") + (x.closes ? ", settles " + x.closes : "")),
        per ? el("div", "m", "By venue: " + per + (x.venue_spread_pts >= 5 ? ". The two venues disagree by " + Math.round(x.venue_spread_pts) + " points." : "")) : null));
    });
    if (g.ladder && g.ladder.length) {
      const det = el("details"), t = el("table"), hr = el("tr");
      ["Level", "Market", "Price implied", "Gap, pts"].forEach((h, i) => add(hr, el("th", i ? "r" : "", h)));
      add(t, hr);
      g.ladder.forEach((k) => add(t, add(el("tr"), el("td", null, "above " + num(k.level)), el("td", "r", pct(k.market)), el("td", "r", pct(k.model)),
        el("td", "r", (k.gap_pts >= 0 ? "+" : "") + k.gap_pts.toFixed(0)))));
      add(c, add(det, el("summary", null, "Every price level the market trades"), t));
    }
    return c;
  }

  function charts(r) {
    const box = el("div", "charts");
    const p = (r.price && r.price.series) || [];
    if (p.length > 1) add(box, chartCard("Price, last 6 months", "", lineChart(p.map((x) => x.t), p.map((x) => x.v), p[0].v > 100 ? "{:,.0f}" : "{:.2f}", BLUE)));
    const m = r.history.market_prob || [];
    if (m.length > 1) add(box, chartCard("Market probability over time", r.headline ? r.headline.question : "", lineChart(m.map((x) => x.t), m.map((x) => x.v * 100), "{:.0f}%", NAVY)));
    r.evidence.charts.forEach((c) => {
      if (!c.y || c.y.length < 2) return;
      add(box, chartCard(c.title, c.note, c.kind === "bars" ? barChart(c.x, c.y, c.fmt, c.highlight_last) : lineChart(c.x, c.y, c.fmt, NAVY), c.status));
    });
    const an = (r.history.analyses || []).filter((x) => x.gap_pts !== null && x.gap_pts !== undefined);
    if (an.length > 1) add(box, chartCard("Our gap at each past analysis, points", an.length + " analyses stored",
      lineChart(an.map((x) => new Date(x.at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" })), an.map((x) => x.gap_pts), "{:.0f}", RUST)));
    return box.children.length ? box : null;
  }

  function risksAndWhy(r) {
    const g = el("div", "grid"), a = el("div", "card"), b = el("div", "card");
    const ul = el("ul", "risks"); r.risks.forEach((t) => add(ul, el("li", null, t)));
    add(a, el("h3", null, "What could make this wrong"), ul);
    const rs = el("ul", "reasons");
    r.confidence.reasons.forEach((x) => add(rs, add(el("li"), el("b", x.points >= 0 ? "up" : "dn", (x.points >= 0 ? "+" : "") + x.points), el("span", null, x.text))));
    add(b, el("h3", null, "Why confidence is " + r.confidence.level.toLowerCase()), rs);
    const src = el("div", "src");
    r.sources.forEach((s) => {
      const cls = s.state === "live" || s.state === "cache" ? "g" : s.state === "failed" || s.state === "missing" ? "x" : "a";
      const txt = { live: "live", cache: "live", stale: "saved copy", file: "saved copy", snapshot: "report figures", failed: "unreachable", missing: "no data" }[s.state];
      const sp = el("span", cls); add(sp, el("i")); sp.appendChild(document.createTextNode(s.label + ": " + txt)); add(src, sp);
    });
    const det = el("details"); add(b, add(det, el("summary", null, "Data status"), src));
    return add(g, a, b);
  }

  function render(r) {
    const root = $("result"); root.textContent = "";
    const warn = r.warning ? el("div", "warnbar", r.warning) : null;
    add(root, header(r), warn, verdict(r), conclusion(r), add(el("div", "grid"), evidence(r), expectations(r)), attention(r),
      add(el("div", "grid"), pricedIn(r), gap(r)), charts(r), risksAndWhy(r));
    const foot = el("p", "asof", "Analysis of " + r.as_of + ".");
    if (r.asset.report) { const a = el("a", null, " Read the full event report."); a.href = "/files/" + r.asset.report; foot.appendChild(a); }
    add(root, foot);
    document.title = r.asset.short_name + " · ALT/INFO";
    show("result");
  }

  // ------------------------------------------------------------ flow: submit -> poll -> render
  function fail(err) {
    $("errtitle").textContent = (err && err.message) || "Something went wrong.";
    $("errdetail").textContent = (err && err.detail) || "Check your connection and try again.";
    show("error");
  }
  function steps(stages, at, label, elapsed) {
    const ol = $("steps"); ol.textContent = "";
    stages.slice(0, -1).forEach((s, i) => {
      const li = el("li", i < at ? "ok" : i === at ? "on" : ""), sp = el("span", null, s);
      if (i === at && label && label.indexOf(": ") > 0) add(sp, el("small", "now", label.split(": ")[1]));
      add(ol, add(li, el("i"), sp));
    });
    $("loadnote").textContent = elapsed >= 25 ? elapsed + " seconds. Some sources are slow today; sites that do not answer are skipped." :
      elapsed >= 5 ? elapsed + " seconds" : "";
  }
  // one analysis as a background job: resolves with the result, reports each stage
  function job(q, onStage) {
    return new Promise(async (resolve, reject) => {
      let js;
      try { js = await api("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q }) }); }
      catch (e) { return reject(e.message ? e : { message: "The server is not reachable.", detail: "Start it with: python server/app.py" }); }
      const t = setInterval(async () => {
        try {
          const j = await (await fetch("/api/jobs/" + js.job)).json();
          if (j.error && !j.state) { clearInterval(t); return reject(j.error); }
          if (onStage) onStage(j.stages, j.stage, j.label, j.elapsed);
          if (j.state === "done") { clearInterval(t); resolve(j.result); }
          if (j.state === "error") { clearInterval(t); reject(j.error); }
        } catch (e) { clearInterval(t); reject({ message: "The server stopped answering.", detail: "Restart it with: python server/app.py" }); }
      }, 400);
    });
  }
  async function run(q, push) {
    q = (q || "").trim();
    if (!q) return;
    const me = ++current;
    $("q").value = q; $("q2").value = q;
    $("loadtitle").textContent = "Analysing " + q.toUpperCase();
    steps(["Recognising the asset", "Collecting the data", "Making sources comparable", "Running the analysis", "Done"], 0);
    show("loading");
    if (push !== false) history.pushState({ q }, "", "/#" + encodeURIComponent(q));
    try {
      const r = await job(q, (...a) => { if (me === current) steps(...a); });
      if (me === current) render(r);
    } catch (e) { if (me === current) fail(e); }
  }

  // ------------------------------------------------------------ track record
  const ago = (ts) => {
    const m = Math.round((Date.now() / 1000 - ts) / 60);
    return m < 2 ? "just now" : m < 60 ? m + " minutes ago" : m < 1440 ? Math.round(m / 60) + " hours ago" : Math.round(m / 1440) + " days ago";
  };
  function watchCard(w) {
    const c = el("div", "card w"), last = w.last, first = w.first_after_save;
    const h = el("h4", null, w.name); add(h, el("small", null, w.key)); add(c, h);
    if (!last) {
      add(c, el("p", "wq empty", "Not analysed yet. Update to run the first analysis."));
    } else {
      add(c, el("p", "wq", last.question || last.title || "No market probability to compare with."));
      const nums = el("div", "nums");
      if (last.gap_pts !== null && last.gap_pts !== undefined) {
        const tone = Math.abs(last.gap_pts) < 3 ? "flat" : last.gap_pts > 0 ? "pos" : "neg";
        add(nums, el("span", "lab " + (last.label || "NONE").split(/[- ]/)[0], (last.label || "").replace("-", " ")),
          el("span", "g " + tone, (last.gap_pts >= 0 ? "+" : "") + Math.round(last.gap_pts) + " pts"),
          el("span", null, "ours " + pct(last.ours) + " · market " + pct(last.market)));
      } else add(nums, el("span", "lab NONE", "NO GAP YET"));
      add(nums, el("span", null, "confidence " + (last.level || "").toLowerCase() + " " + (last.confidence ?? "")));
      add(c, nums);
      let since = "Last analysed " + ago(last.at) + ".";
      if (first && first.at !== last.at && first.market !== null && last.market !== null && first.market !== undefined)
        since += " Market " + ((last.market - first.market) * 100 >= 0 ? "+" : "") + ((last.market - first.market) * 100).toFixed(0) + " pts since you saved it.";
      if (first && first.at !== last.at && last.price && first.price) since += " Price " + signed(last.price / first.price - 1) + ".";
      add(c, el("p", "since", since));
      const g = w.analyses.filter((x) => x.gap_pts !== null && x.gap_pts !== undefined);
      if (g.length > 1 && new Set(g.map((x) => Math.round(x.gap_pts))).size > 1) add(c, lineChart(g.map((x) => new Date(x.at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" })), g.map((x) => x.gap_pts), "{:.0f}", RUST));
    }
    const acts = el("div", "acts");
    const open = el("button", "ghost", "Open analysis"); open.type = "button"; open.addEventListener("click", () => run(w.key));
    const upd = el("button", "ghost", "Update"); upd.type = "button";
    upd.addEventListener("click", async () => {
      upd.disabled = true; upd.textContent = "Updating…";
      try { await job(w.key); } catch (e) { upd.textContent = "Failed"; }
      track(false);
    });
    const rm = el("button", "ghost", "Remove"); rm.type = "button";
    rm.addEventListener("click", async () => { await api("/api/watchlist/" + encodeURIComponent(w.key), { method: "DELETE" }).catch(() => {}); track(false); });
    add(acts, open, upd, rm);
    const rep = last && last.report;
    if (rep) { const a = el("a", null, "Full event report"); a.href = "/files/" + rep; add(acts, a); }
    upd.dataset.key = w.key;
    return add(c, acts);
  }
  async function track(scroll) {
    current++;   // leaving a running analysis: it finishes in the background and is stored
    document.title = "Track record · ALT/INFO";
    if (scroll !== false) show("track");
    let list = [];
    try { list = await api("/api/watchlist"); } catch (e) { return fail(e); }
    const box = $("watch"); box.textContent = "";
    list.forEach((w) => add(box, watchCard(w)));
    if (!list.length) add(box, el("p", "empty", "Nothing saved yet. Add a ticker above, or press Save on any analysis."));
    $("trcount").textContent = list.length + (list.length === 1 ? " ticker saved" : " tickers saved");
    $("refreshall").hidden = !list.length;
    try {
      const c = await api("/api/calls"), box2 = $("calls"); box2.textContent = "";
      const t = el("table"), hr = el("tr");
      ["Call", "Ours", "Market", "Outcome", "Brier, ours", "Brier, market", ""].forEach((x, i) => add(hr, el("th", i && i < 6 ? "r" : "", x)));
      add(t, hr);
      c.calls.forEach((r) => {
        const out = r.outcome === null ? "pending" : r.outcome ? "yes" : "no", b = (x) => (x === null ? "pending" : x.toFixed(3));
        const link = el("td", "r"); if (r.report) { const a = el("a", null, "Report"); a.href = r.report; add(link, a); }
        add(t, add(el("tr"), el("td", null, r.event), el("td", "r", pct(r.ours)), el("td", "r", pct(r.market) + " " + r.source_market),
          el("td", "r", out), el("td", "r", b(r.brier_ours)), el("td", "r", b(r.brier_market)), link));
      });
      const note = c.summary.resolved ? "Skill against the market: " + (c.summary.skill_vs_market * 100).toFixed(0) + "% (above 0 means we beat the market)."
        : "No call has resolved yet: NVIDIA reports on 17 November, Kalshi settles Brent on 30 November. The Brier score runs from 0 (perfect) to 0.25 (a coin toss).";
      const more = el("a", null, " How the scoring works."); more.href = c.scoring;
      const p = el("p", "since", note); p.appendChild(more);
      add(box2, t, p);
    } catch (e) { $("calls").textContent = "The report calls could not be loaded."; }
  }
  $("addform").addEventListener("submit", (e) => { e.preventDefault(); saveFrom($("addq"), $("addmsg"), track); });
  $("refreshall").addEventListener("click", () => updateAll($("refreshall"), track));

  // ------------------------------------------------------------ dashboard: saved tickers ranked by gap
  const fmtDay = (d) => new Date(d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  async function removeTicker(key, then) {
    await api("/api/watchlist/" + encodeURIComponent(key), { method: "DELETE" }).catch(() => {});
    then(false);
  }
  function gapScale(o, m, g) {
    const sc = el("div", "scale"), colour = Math.abs(g) < 3 ? SLATE : g > 0 ? BLUE : RUST;
    const span = el("div", "span"); span.style.left = Math.min(o, m) + "%"; span.style.width = Math.abs(o - m) + "%"; span.style.background = colour;
    const dm = el("div", "dot mkt"); dm.style.left = m + "%";
    const dn = el("div", "dot our"); dn.style.left = o + "%";
    const lo = el("div", "lab " + (o >= m ? "t" : "b")); lo.style.left = o + "%"; add(lo, el("b", null, "Ours " + Math.round(o) + "%"));
    const lm = el("div", "lab " + (o >= m ? "b" : "t"), "Market " + Math.round(m) + "%"); lm.style.left = m + "%";
    return add(sc, el("div", "base"), span, dm, dn, lo, lm);
  }
  async function dash(scroll) {
    current++;
    document.title = "Dashboard · ALT/INFO";
    if (scroll !== false) show("dash");
    let d;
    try { d = await api("/api/dashboard"); } catch (e) { return fail(e); }
    const map = $("dmap"); map.textContent = "";
    const withGap = d.rows.filter((r) => r.gap_pts !== null && r.gap_pts !== undefined);
    withGap.forEach((r) => {
      const row = el("div", "drow"), who = el("div", "who"), name = el("b", null, r.name);
      name.addEventListener("click", () => run(r.key));
      add(who, name, el("span", null, r.question), el("span", null, "confidence " + (r.level || "").toLowerCase() + (r.closes ? " · settles " + new Date(r.closes).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "")));
      const gp = el("div", "gp"), g = el("b", null, (r.gap_pts >= 0 ? "+" : "") + Math.round(r.gap_pts));
      g.style.color = Math.abs(r.gap_pts) < 3 ? SLATE : r.gap_pts > 0 ? BLUE : RUST;
      add(gp, g, el("span", null, "pts, " + (r.label || "").toLowerCase().replace("-", " ")));
      const x = el("button", "x", "×"); x.type = "button"; x.title = "Remove " + r.name; x.setAttribute("aria-label", "Remove " + r.name);
      x.addEventListener("click", () => removeTicker(r.key, dash));
      add(map, add(row, who, gapScale(r.ours * 100, r.market * 100, r.gap_pts), gp, x));
    });
    const rest = d.rows.filter((r) => r.gap_pts === null || r.gap_pts === undefined);
    if (rest.length) add(map, el("div", "dnone", "No measurable gap yet for: " + rest.map((r) => r.name + (r.analysed ? "" : " (not analysed)")).join(", ") + "."));
    if (!d.rows.length) add(map, el("p", "empty", "No saved tickers. Add one above, or press Save on any analysis."));
    $("dcount").textContent = d.rows.length + (d.rows.length === 1 ? " ticker saved" : " tickers saved");
    const ev = $("devents"); ev.textContent = "";
    d.events.forEach((e) => {
      const li = el("li"); add(li, el("b", null, fmtDay(e.date)), document.createTextNode(e.name + ": " + e.event));
      if (e.call && e.gap_pts !== null && e.gap_pts !== undefined) { const c = el("span", "c", (e.gap_pts >= 0 ? "+" : "") + Math.round(e.gap_pts) + " pts"); c.style.color = e.gap_pts > 0 ? BLUE : RUST; add(li, c); }
      add(ev, li);
    });
    if (!d.events.length) add(ev, el("li", "empty", "No dates in the next three weeks for your tickers."));
    const al = $("dalerts"); al.textContent = "";
    d.alerts.slice(0, 10).forEach((a) => { const li = el("li"); add(li, el("span", "ty", a.type), el("b", null, a.name + " "), document.createTextNode(a.text)); add(al, li); });
    if (!d.alerts.length) add(al, el("li", "empty", "No alerts at the last analysis."));
    const t = el("table", "dt"), hr = el("tr");
    ["Name", "Last", "1 week", "1 month", "Gap, pts", "Confidence", "Analysed", ""].forEach((h, i) => add(hr, el("th", i && i < 7 ? "r" : "", h)));
    add(t, hr);
    d.rows.forEach((r) => {
      const nm = el("td"), b = el("b", "nm", r.name); b.addEventListener("click", () => run(r.key)); add(nm, b);
      const tone = (x) => (x === null || x === undefined ? "" : x >= 0 ? "up" : "dn");
      const x = el("button", "x", "×"); x.type = "button"; x.setAttribute("aria-label", "Remove " + r.name); x.addEventListener("click", () => removeTicker(r.key, dash));
      const xt = el("td", "r"); add(xt, x);
      add(t, add(el("tr"), nm, el("td", "r", r.price ? num(r.price) : ""), el("td", "r " + tone(r.change_1w), r.analysed ? signed(r.change_1w) : ""),
        el("td", "r " + tone(r.change_1m), r.analysed ? signed(r.change_1m) : ""),
        el("td", "r", r.gap_pts === null || r.gap_pts === undefined ? "" : (r.gap_pts >= 0 ? "+" : "") + Math.round(r.gap_pts)),
        el("td", "r", r.confidence ?? ""), el("td", "r", r.analysed ? ago(r.at) : "not yet"), xt));
    });
    const tb = $("dtable"); tb.textContent = ""; add(tb, t);
  }
  async function saveFrom(input, msg, then) {
    const q = input.value.trim();
    if (!q) return;
    msg.className = "addmsg"; msg.textContent = "Saving " + q.toUpperCase() + "…";
    try {
      const r = await api("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q }) });
      input.value = ""; msg.textContent = r.name + " saved. Running the first analysis…";
      await then(false);
      await job(r.key).catch(() => {});
      msg.textContent = r.name + " saved."; then(false);
    } catch (err) { msg.className = "addmsg bad"; msg.textContent = err.message || "Could not save it."; }
  }
  async function updateAll(btn, then) {
    btn.disabled = true;
    const list = await api("/api/watchlist").catch(() => []);
    for (let i = 0; i < list.length; i++) { btn.textContent = "Updating " + (i + 1) + " of " + list.length + "…"; await job(list[i].key).catch(() => {}); }
    btn.disabled = false; btn.textContent = "Update all"; then(false);
  }
  $("dadd").addEventListener("submit", (e) => { e.preventDefault(); saveFrom($("daddq"), $("daddmsg"), dash); });
  $("drefresh").addEventListener("click", () => updateAll($("drefresh"), dash));

  function home() { current++; document.title = "ALT/INFO"; show("start"); $("q").focus(); }
  $("search").addEventListener("submit", (e) => { e.preventDefault(); run($("q").value); });
  $("mini").addEventListener("submit", (e) => { e.preventDefault(); run($("q2").value); });
  $("retry").addEventListener("click", () => { history.pushState({}, "", "/"); home(); });
  function route() {
    if (location.pathname === "/track") return track();
    if (location.pathname === "/dashboard") return dash();
    const q = decodeURIComponent(location.hash.slice(1));
    q ? run(q, false) : home();
  }
  window.addEventListener("popstate", route);
  $("nav-track").addEventListener("click", (e) => { e.preventDefault(); history.pushState({}, "", "/track"); track(); });
  $("nav-dash").addEventListener("click", (e) => { e.preventDefault(); history.pushState({}, "", "/dashboard"); dash(); });
  $("nav-search").addEventListener("click", (e) => { e.preventDefault(); history.pushState({}, "", "/"); home(); });

  fetch("/api/assets").then((r) => r.json()).then((list) => {
    const box = $("chips"); add(box, el("span", null, "Covered in depth:"));
    list.forEach((a) => { const b = el("button", null, a.name); b.type = "button"; b.addEventListener("click", () => run(a.key)); add(box, b); });
  }).catch(() => {});
  route();
})();
