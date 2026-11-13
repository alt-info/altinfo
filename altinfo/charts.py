"""Charts in the house style of the ALT/INFO previews."""
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

NAVY, BLUE, RED, GREY, LIGHT = "#1b3a52", "#1f7ab8", "#c0502e", "#8a94a3", "#e6ebf1"


def style():
    mpl.rcParams.update({
        "font.family": ["Lato", "Carlito", "DejaVu Sans"], "font.size": 8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GREY,
        "axes.titlesize": 8.5, "axes.titleweight": "bold", "axes.titlecolor": BLUE, "axes.titlelocation": "left",
        "xtick.color": "#5d6878", "ytick.color": "#5d6878", "axes.grid": True, "grid.color": LIGHT,
        "grid.linewidth": 0.6, "figure.dpi": 110})


def _label_bars(ax, bars, fmt):
    for b in bars:
        v = b.get_height()
        ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, v), ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=7, xytext=(0, 2 if v >= 0 else -2),
                    textcoords="offset points", color=BLUE if v >= 0 else RED, weight="bold")


def bar_moves(moves, ax=None, title="NEXT-DAY MOVE AFTER LAST 8 REPORTS"):
    ax = ax or plt.gca()
    v = moves["move"].values * 100
    bars = ax.bar(moves["quarter"].str.replace(" ", "\n"), v, color=[BLUE if x >= 0 else RED for x in v], width=0.6)
    _label_bars(ax, bars, "{:+.1f}%")
    ax.axhline(0, color=GREY, lw=0.6); ax.set_yticks([]); ax.grid(False); ax.spines["left"].set_visible(False)
    ax.set_title(title)
    return ax


def prob_line(s, ax=None, title="", color=BLUE, pct=True, label_last=True):
    ax = ax or plt.gca()
    y = s * 100 if pct else s
    ax.plot(s.index, y, color=color, lw=1.3)
    if label_last and len(s):
        ax.annotate(f"{y.iloc[-1]:.0f}%" if pct else f"{y.iloc[-1]:.1f}", (s.index[-1], y.iloc[-1]),
                    xytext=(3, 0), textcoords="offset points", fontsize=7.5, color=color, weight="bold", va="center")
    ax.set_title(title)
    return ax


def curve(labels, probs, ax=None, title="", color=BLUE):
    """Probability by date (e.g. Hormuz traffic normal by ...)."""
    ax = ax or plt.gca()
    y = np.asarray(probs) * 100
    ax.plot(range(len(y)), y, color=color, lw=1.3, marker="o", ms=3.5)
    for i, v in enumerate(y):
        ax.annotate(f"{v:.0f}%", (i, v), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=7,
                    color=color, weight="bold")
    ax.set_xticks(range(len(y))); ax.set_xticklabels(labels, fontsize=7); ax.set_ylim(0, max(y) * 1.25 + 2)
    ax.set_title(title)
    return ax


def ladder(levels, probs, spot, ax=None, title="", fmt="${:.0f}"):
    """Touch probabilities by level: red below the spot price, blue above."""
    ax = ax or plt.gca()
    y = np.asarray(probs) * 100
    cols = [RED if l < spot else BLUE for l in levels]
    bars = ax.bar([fmt.format(l) for l in levels], y, color=cols, width=0.6)
    _label_bars(ax, bars, "{:.0f}%")
    ax.set_yticks([]); ax.grid(False); ax.spines["left"].set_visible(False); ax.set_title(title)
    return ax


def hbar_shares(shares, tones=None, ax=None, title=""):
    """Topic shares (dict label -> share) with an optional tone label on the right."""
    ax = ax or plt.gca()
    lab, val = list(shares.keys())[::-1], np.array(list(shares.values())[::-1]) * 100
    ax.barh(lab, val, color=BLUE, height=0.55)
    for i, v in enumerate(val):
        ax.text(v + 0.8, i, f"{v:.0f}%", va="center", fontsize=7, weight="bold", color=NAVY)
        if tones:
            t = tones.get(lab[i], "")
            ax.text(val.max() * 1.25, i, t, va="center", fontsize=7, weight="bold",
                    color=RED if "Bear" in t or "Neg" in t else (BLUE if "Bull" in t or "Pos" in t else GREY))
    ax.set_xlim(0, val.max() * 1.55); ax.set_xticks([]); ax.grid(False); ax.spines["bottom"].set_visible(False)
    ax.set_title(title)
    return ax


def index_bars(hist, ax=None, title="DATA CENTER BUILD-OUT INDEX, QUARTER END"):
    ax = ax or plt.gca()
    y = hist["index"].values * 100
    bars = ax.bar(hist.index, y, color=[LIGHT] * (len(y) - 1) + [BLUE], edgecolor=BLUE, width=0.55)
    _label_bars(ax, bars, "{:.0f}%")
    ax.set_ylim(0, max(y) * 1.2); ax.set_yticks([]); ax.grid(False); ax.spines["left"].set_visible(False)
    ax.set_title(title)
    return ax


def text_on(rgba):
    """Black or white, whichever reads better on a cell of colour rgba (relative luminance)."""
    r, g, b = rgba[:3]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "white" if lum < 0.55 else "#1d2430"
