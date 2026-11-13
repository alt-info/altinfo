"""ALT/INFO logo as inline SVG paths, so every HTML page carries it with no image file and stays sharp at any size."""

NAVY, CYAN = "#010E29", "#00CCFB"
_W, _H = 1797, 298
_LETTERS = "M1486,12 1297,12 1297,282 1361,282 1362,174 1475,174 1476,119 1363,119 1361,116 1361,71 1363,69 1486,69ZM1009,12 1009,282 1075,282 1076,121 1190,282 1260,282 1260,12 1193,12 1192,170 1076,12ZM899,12 898,282 967,282 967,12ZM498,12 498,68 575,69 575,282 643,282 643,69 722,68 722,12ZM327,12 326,281 527,282 527,222 396,221 396,12ZM131,12 76,126 5,282 78,282 103,230 223,230 248,282 320,282 310,255 197,12ZM163,86 199,173 198,176 130,176 127,174ZM1632,6 1606,11 1586,18 1570,26 1544,45 1528,62 1517,78 1510,92 1502,115 1498,137 1498,168 1503,193 1517,225 1540,254 1556,267 1584,282 1609,290 1631,293 1666,292 1700,283 1719,274 1743,257 1759,241 1774,219 1786,191 1792,160 1791,127 1787,108 1776,81 1759,56 1743,40 1721,25 1691,12 1661,6ZM1637,67 1652,67 1666,70 1679,75 1689,82 1706,100 1713,113 1717,125 1720,147 1719,162 1715,180 1708,195 1700,206 1689,217 1674,226 1647,232 1626,230 1612,225 1598,216 1586,204 1578,192 1572,178 1568,157 1568,143 1571,124 1577,109 1587,94 1605,78 1619,71Z"
_SLASH = "M863,4 817,5 717,288 765,288Z"


def logo_svg(height=22, letters=NAVY, title="ALT/INFO"):
    """The logo; letters='#fff' for dark backgrounds (the slash stays cyan)."""
    w = round(height * _W / _H, 1)
    return (f"<svg class='logo' xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {_W} {_H}' width='{w}' height='{height}' "
            f"role='img' aria-label='{title}'><title>{title}</title>"
            f"<path fill='{letters}' fill-rule='evenodd' d='{_LETTERS}'/><path fill='{CYAN}' d='{_SLASH}'/></svg>")


# Browser tab icon: the cyan slash on a navy square
FAVICON = ("<link rel='icon' href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='6' fill='%23010E29'/%3E%3Cpath d='M18 5h6l-10 22h-6z' fill='%2300CCFB'/%3E%3C/svg%3E\">")


# ---------------------------------------------------------------- shared header for every static page
# Same look as the live app (web/style.css): logo, sections, active section underlined in cyan, quick search on the right.
BAND_CSS = """
.band{background:#010E29;color:#fff;font-family:Lato,"Helvetica Neue",Arial,sans-serif}
.band .in{max-width:1120px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.band .brand{display:flex;line-height:0}
.band .nav{display:flex;gap:18px;font-size:15px;margin-left:8px;flex-wrap:wrap}
.band .nav a{color:#c9d6ea;text-decoration:none;padding:4px 0;border-bottom:2px solid transparent;line-height:1.5}
.band .nav a:hover{color:#fff}
.band .nav a.on{color:#fff;border-bottom-color:#00CCFB}
.band .mini{margin-left:auto;display:flex;gap:8px}
.band .mini input{width:180px;padding:8px 12px;border-radius:8px;border:1px solid #2c3c5e;background:#0b1c40;color:#fff;font:inherit;font-size:15px}
.band .mini input::placeholder{color:#8fa0bd}
.band .mini button{padding:8px 14px;border-radius:8px;border:0;background:#00CCFB;color:#010E29;font:inherit;font-weight:900;font-size:14px;cursor:pointer}
.band .mini button:hover{filter:brightness(1.12)}
.band .mini input,.band .mini button{line-height:20px;height:38px;box-sizing:border-box}
.band .in{min-height:66px}
@media(max-width:860px){.band .in{padding:12px 16px}.band .mini{margin-left:0;width:100%}.band .mini input{flex:1;width:auto}
 .band .nav{margin-left:0;width:100%;overflow-x:auto;flex-wrap:nowrap;gap:16px;white-space:nowrap}}
"""
FONTS = "<link href='https://fonts.googleapis.com/css2?family=Lato:wght@400;700;900&display=swap' rel='stylesheet'>"


def band_html(nav, current=None, app_url="http://127.0.0.1:8000/"):
    """The header of every page: logo (back to the search), sections, and a search box that opens the live app."""
    import html as h
    links = "".join(f"<a href='{h.escape(u)}' class='{'on' if lab == current else ''}'>{h.escape(lab)}</a>" for lab, u in (nav or []))
    return (f"<header class='band'><div class='in'><a class='brand' href='{h.escape(app_url)}' aria-label='ALT/INFO search'>"
            f"{logo_svg(24, letters='#ffffff')}</a><nav class='nav' aria-label='Sections'>{links}</nav>"
            f"<form class='mini' role='search' onsubmit=\"var q=this.q.value.trim();if(q)location.href='{h.escape(app_url)}#'+encodeURIComponent(q);return false;\">"
            "<input name='q' type='text' autocomplete='off' spellcheck='false' maxlength='40' placeholder='Ticker or commodity' "
            "aria-label='Ticker or commodity'><button type='submit'>Analyse</button></form></div></header>")
