"""Tiny notebook builder: executes cells, writes a real .ipynb with outputs, renders HTML and PDF.

Used because the workspace has no Jupyter kernel. The .ipynb it writes opens and re-runs
in any Jupyter installation; File > Save and Export as PDF gives the same document.
"""
import re
import base64
import contextlib
import io
import json
import sys

import markdown
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def df_to_html(df, max_rows=60):
    """Clean table: no truncation, index only when meaningful, numbers right aligned."""
    import html as _h
    import pandas as pd
    if isinstance(df, pd.Series):
        df = df.to_frame(df.name if df.name is not None else "value")
    df = df.head(max_rows)
    show_idx = not (isinstance(df.index, pd.RangeIndex) or pd.api.types.is_integer_dtype(df.index))
    cols = list(df.columns)
    import re as _re
    numlike = _re.compile(r"^[+\-]?\$?[\d,]*\.?\d+(%|x| pts| mb| bn)?$")

    def _isnum(c):  # numeric columns, or text columns holding formatted numbers (+1.2%, 24.1x, $150)
        if pd.api.types.is_numeric_dtype(df[c]):
            return True
        v = [str(x) for x in df[c] if x is not None and x == x and str(x) != ""]
        return bool(v) and all(numlike.match(x) for x in v)
    num = {c: _isnum(c) for c in cols}

    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            if v != v:
                return ""
            return f"{v:,.3f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d") if getattr(v, "hour", 0) == 0 and getattr(v, "minute", 0) == 0 else v.strftime("%Y-%m-%d %H:%M")
        return str(v)

    def label(x):  # snake_case column names become "Sentence case"
        t = str(x).replace("_", " ").strip()
        return t[:1].upper() + t[1:] if t else t

    head = (f"<th>{_h.escape(label(df.index.name or ''))}</th>" if show_idx else "") + "".join(
        f"<th class='{'n' if num[c] else ''}'>{_h.escape(label(c))}</th>" for c in cols)
    rows = []
    for idx, r in df.iterrows():
        cells = (f"<th>{_h.escape(label(fmt(idx)) if isinstance(idx, str) else fmt(idx))}</th>" if show_idx else "") + "".join(
            f"<td class='{'n' if num[c] else ('nw' if len(fmt(r[c])) <= 16 else '')}'>{_h.escape(fmt(r[c]))}</td>" for c in cols)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table class='dataframe'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


class Display:
    def __init__(self):
        self.outputs = []

    def __call__(self, obj):
        import pandas as pd
        if isinstance(obj, (pd.DataFrame, pd.Series)):
            self.outputs.append({"output_type": "display_data", "metadata": {},
                                 "data": {"text/html": df_to_html(obj), "text/plain": obj.to_string()[:2000]}})
            return
        if hasattr(obj, "_repr_html_"):
            self.outputs.append({"output_type": "display_data", "metadata": {},
                                 "data": {"text/html": obj._repr_html_(), "text/plain": repr(obj)}})
        elif hasattr(obj, "to_html"):
            self.outputs.append({"output_type": "display_data", "metadata": {},
                                 "data": {"text/html": obj.to_html(), "text/plain": str(obj)}})
        else:
            self.outputs.append({"output_type": "display_data", "metadata": {},
                                 "data": {"text/plain": str(obj)}})


class HTML:
    def __init__(self, s):
        self.s = s

    def _repr_html_(self):
        return self.s

    def __repr__(self):
        return "<HTML>"


def run(cells, ns=None, execute=True):
    ns = ns if ns is not None else {}
    disp = Display()
    ns.update({"display": disp, "HTML": HTML, "plt": plt})
    nb_cells = []
    for c in cells:
        kind, src = c[0], c[1]
        opts = c[2] if len(c) > 2 else {}
        if kind == "md":
            nb_cells.append({"cell_type": "markdown", "metadata": {}, "source": src, "_opts": opts})
            continue
        if not execute:
            nb_cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                             "source": src, "outputs": [], "_opts": opts})
            continue
        disp.outputs = []
        buf = io.StringIO()
        plt.close("all")
        import ast
        tree = ast.parse(src)
        last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
        with contextlib.redirect_stdout(buf):
            exec(compile(tree, "<cell>", "exec"), ns)
            if last is not None:
                val = eval(compile(ast.Expression(last.value), "<cell>", "eval"), ns)
                if val is not None and not (hasattr(val, "__class__") and val.__class__.__module__.startswith("matplotlib")):
                    disp(val)
        outs = []
        if buf.getvalue():
            outs.append({"output_type": "stream", "name": "stdout", "text": buf.getvalue()})
        outs += disp.outputs
        for num in plt.get_fignums():
            fig = plt.figure(num)
            b = io.BytesIO()
            fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
            outs.append({"output_type": "display_data", "metadata": {"width": opts.get("width"),
                                                                     "width_in": float(fig.get_size_inches()[0])},
                         "data": {"image/png": base64.b64encode(b.getvalue()).decode(), "text/plain": "<Figure>"}})
        plt.close("all")
        meta = {"jupyter": {"source_hidden": True}, "tags": ["remove_input"]} if opts.get("hide", True) else {}
        nb_cells.append({"cell_type": "code", "metadata": meta, "execution_count": None,
                         "source": src, "outputs": outs, "_opts": opts})
    return nb_cells, ns


def write_ipynb(nb_cells, path):
    cells = []
    for i, c in enumerate(nb_cells, 1):
        note = c.get("_opts", {}).get("note")
        c = {k: v for k, v in c.items() if k != "_opts"}
        if c["cell_type"] == "code" and c["outputs"]:
            c["execution_count"] = i
        cells.append(c)
        if note:
            cells.append({"cell_type": "markdown", "metadata": {}, "source": f"**How to read it.** {note}"})
    nb = {"nbformat": 4, "nbformat_minor": 5,
          "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                       "language_info": {"name": "python"}},
          "cells": cells}
    for c in nb["cells"]:
        c["id"] = f"c{nb['cells'].index(c):03d}"
    with open(path, "w") as f:
        json.dump(nb, f, indent=1)


def to_html(nb_cells, css, title):
    md = markdown.Markdown(extensions=["tables", "attr_list", "md_in_html"])
    parts = []
    for c in nb_cells:
        opts = c.get("_opts", {})
        col = opts.get("col")
        if col == "L":
            parts.append("<div class='cols'><div>")
        elif col == "R":
            parts.append("</div><div>")
        if c["cell_type"] == "markdown":
            parts.append(md.convert(c["source"]))
            md.reset()
        else:
            if not opts.get("hide", True):
                parts.append(f"<pre class='code'>{c['source']}</pre>")
            for o in c["outputs"]:
                d = o.get("data", {})
                if "image/png" in d:
                    w = opts.get("width", "100%")
                    parts.append(f"<img class='fig' style='width:{w}' src='data:image/png;base64,{d['image/png']}'/>")
                elif "text/html" in d:
                    parts.append(d["text/html"])
                elif o.get("output_type") == "stream" and opts.get("show_stdout"):
                    parts.append(f"<pre>{o['text']}</pre>")
        if opts.get("end"):
            parts.append("</div></div>")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{css}</style></head><body>{''.join(parts)}</body></html>")


def to_pdf(html_path, pdf_path, footer=True):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + html_path)
        pg.pdf(path=pdf_path, print_background=True, prefer_css_page_size=True,
               display_header_footer=footer, header_template="<span></span>",
               footer_template="<div style='font-size:7px;width:100%;text-align:center;color:#8a94a3;"
                               "font-family:Arial'>ALT&middot;INFO &middot; <span class='pageNumber'></span> / "
                               "<span class='totalPages'></span></div>")
        b.close()


def to_report_html(nb_cells, title, css, nav=None, current=None):
    """Polished, report style HTML: code folded behind a toggle, results in callouts, styled tables."""
    try:  # the logo is inline SVG: no image file, sharp on any screen
        from altinfo.brand import FAVICON, FONTS, BAND_CSS, band_html
        _fav, _fonts, _bandcss = FAVICON, FONTS, BAND_CSS
        _band = band_html(nav, current, next((u for l, u in (nav or []) if l == "Search"), "http://127.0.0.1:8000/"))
    except ImportError:
        _fav, _fonts, _bandcss, _band = "", "", "", ""
    import html as _h
    md = markdown.Markdown(extensions=["tables", "attr_list", "md_in_html"])
    mode, hero, body = "", "", []
    for c in nb_cells:
        if c["cell_type"] != "code":
            continue
        for o in c["outputs"]:
            if o.get("output_type") == "stream" and o["text"].startswith("Mode:"):
                mode = o["text"].split("\n")[0].replace("Mode: ", "")
    for i, c in enumerate(nb_cells):
        if c["cell_type"] == "markdown":
            src = c["source"]
            if not hero and src.lstrip().startswith("# "):
                first, _, rest = src.lstrip()[2:].partition("\n")
                first = re.sub(r"^\d+\s*\u00b7\s*", "", first)   # "03 · Event betas" -> "Event betas"
                badge = f"<span class='mode'>{_h.escape(mode)}</span>" if mode else ""
                hero = f"<div class='hero'><h1>{_h.escape(first)}</h1>{md.convert(rest)}{badge}</div>"
                md.reset()
                continue
            body.append(f"<section class='cell text'>{md.convert(src)}</section>")
            md.reset()
            continue
        parts = [f"<details class='code'><summary>Code</summary><pre>{_h.escape(c['source'])}</pre></details>"]
        lines = []
        for o in c["outputs"]:
            d = o.get("data", {})
            if o.get("output_type") == "stream":
                for ln in o["text"].rstrip("\n").split("\n"):
                    if ln.startswith("Mode:"):
                        continue
                    cls = " class='verdict'" if "PRICED-IN GAP" in ln or "->" in ln else ""
                    lines.append(f"<div{cls}>{_h.escape(ln)}</div>")
            elif "image/png" in d:
                if lines:
                    parts.append("<div class='result'>" + "".join(lines) + "</div>"); lines = []
                wpx = int(o.get("metadata", {}).get("width_in", 9) * 100)
                parts.append(f"<img class='fig' style='width:{wpx}px' src='data:image/png;base64,{d['image/png']}'/>")
            elif "text/html" in d:
                if lines:
                    parts.append("<div class='result'>" + "".join(lines) + "</div>"); lines = []
                hd = d["text/html"]
                is_table = hd.lstrip().startswith("<table")
                parts.append(f"<div class='tbl-wrap'>{hd}</div>" if is_table else f"<div class='raw'>{hd}</div>")
            elif "text/plain" in d:
                lines.append(f"<div>{_h.escape(d['text/plain'])}</div>")
        if lines:
            parts.append("<div class='result'>" + "".join(lines) + "</div>")
        note = c.get("_opts", {}).get("note")
        if note:
            parts.append(f"<p class='note'><b>How to read it.</b> {_h.escape(note)}</p>")
        if len(parts) == 1:  # code without visible output (setup): no card, just the toggle
            body.append("<div class='bare'>" + parts[0].replace("<summary>Code</summary>", "<summary>Setup code</summary>") + "</div>")
        else:
            body.append("<section class='cell'>" + "".join(parts) + "</section>")
    links = "".join(f"<a href='{href}' class='{'on' if lab == current else ''}'>{lab}</a>" for lab, href in (nav or []))
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_h.escape(title)}</title>{_fav}{_fonts}"
            f"<style>{css}{_bandcss}</style></head><body>{_band}"
            f"<main>{hero}{''.join(body)}</main>"
            f"<footer>Generated from the notebook of the same name. Prototype inputs are labelled; not investment advice.</footer>"
            f"</body></html>")
