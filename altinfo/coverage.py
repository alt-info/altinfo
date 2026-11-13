"""What the platform covers: companies and commodities, the markets and places linked to each.

One entry per covered name. The dashboard, the ticker search and the monitors all read from here,
so adding a company or a commodity means adding one entry.

Fields
  name, kind, group (sector), region     used by the dashboard filters
  price                                  Yahoo ticker of the stock or front month future
  linked                                 linked assets: suppliers, customers, producers, users
  kalshi                                 Kalshi series tickers; kalshi_pattern matches market titles when no series is known
  polymarket                             regular expression on Polymarket questions
  events                                 next key dates (official sources)
  signals                                indices the platform tracks for the name
  sites                                  supply chain map: the places the name depends on. Coordinates are approximate
                                         public locations; owners (share of a company's output) are ILLUSTRATIVE.
"""


def _s(place, role, country, lat, lon, owners=None):
    return {"site": place, "role": role, "country": country, "lat": lat, "lon": lon, "owners": owners or {}}


# Crop calendar used by the agriculture entries (USDA, 2026 schedule)
WASDE_DEC = ("2026-12-10", "USDA WASDE report")
CROP_PROGRESS = [("2026-11-16", "USDA Crop Progress"), ("2026-11-23", "USDA Crop Progress"),
                 ("2026-11-30", "USDA Crop Progress (last of the season)")]

COVERAGE = {
    "NVDA": {
        "name": "NVIDIA", "kind": "company", "group": "Semiconductors", "region": "North America",
        "price": "NVDA", "linked": ["SMH", "TSM", "MU", "AMD", "AVGO"],
        "kalshi": ["KXEARNINGSMENTIONNVDA", "KXNVDAMENTION"], "polymarket": r"NVIDIA|NVDA",
        "events": [("2026-11-17", "Q3 FY2027 results (after close)"), ("2026-12-01", "GTC Washington keynote")],
        "signals": ["Data Center Build-out Index", "GW in fit-out", "US assembly sites", "Memory cargo"],
        "sites": [
            _s("TSMC Fab 18, Tainan", "Supplier: wafers", "Taiwan", 23.11, 120.27),
            _s("TSMC Arizona, Phoenix", "Supplier: wafers", "United States", 33.75, -112.13),
            _s("SK hynix Icheon", "Supplier: HBM memory", "South Korea", 37.27, 127.49),
            _s("Micron Boise", "Supplier: memory", "United States", 43.53, -116.15),
            _s("Foxconn Houston", "Assembly: AI servers", "United States", 29.70, -95.40),
            _s("Wistron Fort Worth", "Assembly: AI servers", "United States", 32.75, -97.33),
            _s("Stargate Abilene", "Customer: AI data centre", "United States", 32.45, -99.73),
            _s("Colossus Memphis", "Customer: AI data centre", "United States", 35.06, -90.03),
            _s("Hyperion, Richland Parish", "Customer: AI data centre", "United States", 32.40, -91.75),
            _s("Fairwater, Mount Pleasant", "Customer: AI data centre", "United States", 42.70, -87.90),
        ],
    },
    "BRENT": {
        "name": "Brent crude", "kind": "commodity", "group": "Energy", "region": "Middle East",
        "price": "BZ=F", "linked": ["CL=F", "XLE", "USO", "JETS"],
        "kalshi": ["KXBRENTMON", "KXBRENTW", "KXHORMUZNORM"], "polymarket": r"Hormuz|Iran|Brent",
        "events": [("2026-11-12", "EIA weekly stocks"), ("2026-11-29", "OPEC+ meeting"),
                   ("2026-11-30", "Kalshi month-end settlement")],
        "signals": ["Hormuz tanker flow", "Ships waiting", "Tank fill (shadows)", "Gas flaring"],
        "curve": "BZ",
        "sites": [
            _s("Strait of Hormuz", "Chokepoint", "Oman / Iran", 26.57, 56.25),
            _s("Ras Tanura", "Export terminal", "Saudi Arabia", 26.64, 50.16),
            _s("Kharg Island", "Export terminal", "Iran", 29.23, 50.32),
            _s("Fujairah", "Storage hub", "UAE", 25.17, 56.36),
            _s("Bab el-Mandeb", "Chokepoint", "Yemen / Djibouti", 12.60, 43.30),
            _s("Sullom Voe", "Export terminal", "United Kingdom", 60.46, -1.29),
            _s("Rotterdam", "Storage hub", "Netherlands", 51.90, 4.10),
        ],
    },
    "WTI": {
        "name": "WTI crude", "kind": "commodity", "group": "Energy", "region": "North America",
        "price": "CL=F", "linked": ["BZ=F", "XLE", "USO"],
        "kalshi": ["KXWTIMAX", "KXWTIMIN", "KXWTIW"], "polymarket": r"\bWTI\b",
        "events": [("2026-11-12", "EIA weekly stocks"), ("2026-11-29", "OPEC+ meeting")],
        "signals": ["Cushing tank fill", "US Gulf Coast tank fill", "Refinery heat"],
        "curve": "CL",
        "sites": [
            _s("Cushing", "Storage hub", "United States", 35.98, -96.77),
            _s("Permian Basin, Midland", "Production", "United States", 31.99, -102.08),
            _s("Houston Ship Channel", "Export terminal", "United States", 29.73, -95.00),
            _s("Corpus Christi", "Export terminal", "United States", 27.81, -97.40),
        ],
    },
    "COPPER": {
        "name": "Copper", "kind": "commodity", "group": "Metals", "region": "Latin America",
        "price": "HG=F", "linked": ["FCX", "SCCO", "TECK", "COPX", "PRY.MI"],
        "kalshi": ["KXCOPPERMON", "KXCOPPERW"], "polymarket": r"\bcopper\b",
        "events": [("2026-11-27", "Monthly LME stocks review")],
        "signals": ["Mine site activity", "Port stockpiles", "Disasters near mines"],
        "sites": [],  # filled below from COPPER_MINES plus ports
    },
    "GOLD": {
        "name": "Gold", "kind": "commodity", "group": "Metals", "region": "Global",
        "price": "GC=F", "linked": ["GLD", "NEM"],
        "kalshi": ["KXGOLDMON", "KXGOLDW"], "polymarket": r"\bgold price|\bgold\b.*(?:\$|oz)",
        "events": [("2026-12-09", "FOMC decision")],
        "signals": ["Mine site activity", "Vault flows"],
        "sites": [
            _s("Carlin Trend, Nevada", "Mine", "United States", 40.90, -116.30, {"NEM": 0.25}),
            _s("Muruntau", "Mine", "Uzbekistan", 41.50, 64.60),
            _s("Grasberg", "Mine", "Indonesia", -4.05, 137.11, {"FCX": 0.10}),
            _s("Boddington", "Mine", "Australia", -32.75, 116.35, {"NEM": 0.12}),
            _s("Ticino refineries", "Refining", "Switzerland", 45.85, 9.00),
            _s("London vaults", "Storage", "United Kingdom", 51.51, -0.09),
        ],
    },
    "CORN": {
        "name": "Corn", "kind": "commodity", "group": "Agriculture", "region": "North America",
        "price": "ZC=F", "linked": ["ZS=F", "ZW=F", "ADM", "DE", "CTVA"],
        "kalshi": [], "kalshi_pattern": r"\bcorn\b", "polymarket": r"\bcorn\b",
        "events": CROP_PROGRESS + [WASDE_DEC],
        "signals": ["Rain and temperature in growing regions", "Crop condition from imagery", "Export port loadings"],
        "sites": [
            _s("Iowa", "Growing region", "United States", 42.00, -93.50),
            _s("Illinois", "Growing region", "United States", 40.00, -89.00),
            _s("Mato Grosso", "Growing region", "Brazil", -13.00, -56.00),
            _s("Poltava", "Growing region", "Ukraine", 49.60, 34.50),
            _s("New Orleans", "Export port", "United States", 29.95, -90.07),
        ],
    },
    "WHEAT": {
        "name": "Wheat", "kind": "commodity", "group": "Agriculture", "region": "Global",
        "price": "ZW=F", "linked": ["ZC=F", "ADM", "BG"],
        "kalshi": [], "kalshi_pattern": r"\bwheat\b", "polymarket": r"\bwheat\b",
        "events": CROP_PROGRESS + [WASDE_DEC],
        "signals": ["Rain and temperature in growing regions", "Crop condition from imagery", "Black Sea port loadings"],
        "sites": [
            _s("Kansas", "Growing region", "United States", 38.50, -98.50),
            _s("Krasnodar", "Growing region", "Russia", 45.00, 39.00),
            _s("Saskatchewan", "Growing region", "Canada", 52.00, -106.00),
            _s("New South Wales", "Growing region", "Australia", -32.00, 147.00),
            _s("Odesa", "Export port", "Ukraine", 46.48, 30.73),
        ],
    },
    "SOYBEANS": {
        "name": "Soybeans", "kind": "commodity", "group": "Agriculture", "region": "Latin America",
        "price": "ZS=F", "linked": ["ZC=F", "ADM", "BG"],
        "kalshi": [], "kalshi_pattern": r"\bsoy", "polymarket": r"\bsoybean",
        "events": CROP_PROGRESS + [WASDE_DEC],
        "signals": ["Rain and temperature in growing regions", "Crop condition from imagery", "Export port loadings"],
        "sites": [
            _s("Mato Grosso", "Growing region", "Brazil", -13.00, -56.00),
            _s("Illinois", "Growing region", "United States", 40.00, -89.00),
            _s("Rosario", "Growing region", "Argentina", -32.95, -60.65),
            _s("Santos", "Export port", "Brazil", -23.96, -46.33),
        ],
    },
    "COFFEE": {
        "name": "Coffee", "kind": "commodity", "group": "Agriculture", "region": "Latin America",
        "price": "KC=F", "linked": ["SBUX", "SB=F"],
        "kalshi": [], "kalshi_pattern": r"\bcoffee\b", "polymarket": r"\bcoffee\b",
        "events": [],
        "signals": ["Rain and temperature in growing regions", "Crop condition from imagery"],
        "sites": [
            _s("Sul de Minas", "Growing region", "Brazil", -21.50, -45.50),
            _s("Dak Lak", "Growing region", "Vietnam", 12.70, 108.10),
            _s("Huila", "Growing region", "Colombia", 2.50, -75.60),
            _s("Santos", "Export port", "Brazil", -23.96, -46.33),
        ],
    },
    "SUGAR": {
        "name": "Sugar", "kind": "commodity", "group": "Agriculture", "region": "Latin America",
        "price": "SB=F", "linked": ["KC=F", "ZC=F"],
        "kalshi": [], "kalshi_pattern": r"\bsugar\b", "polymarket": r"\bsugar\b",
        "events": [WASDE_DEC],
        "signals": ["Rain and temperature in growing regions", "Cane condition from imagery"],
        "sites": [
            _s("Sao Paulo state", "Growing region", "Brazil", -21.50, -48.50),
            _s("Uttar Pradesh", "Growing region", "India", 27.00, 80.50),
            _s("Maharashtra", "Growing region", "India", 19.50, 75.50),
            _s("Nakhon Ratchasima", "Growing region", "Thailand", 15.00, 102.00),
        ],
    },
}

# Copper mines watched by the copper monitor. Coordinates are approximate public locations;
# the share of each company's copper output is ILLUSTRATIVE (to be replaced with company filings).
COPPER_MINES = [
    {"site": "Grasberg", "country": "Indonesia", "lat": -4.05, "lon": 137.11, "owners": {"FCX": 0.35}},
    {"site": "Escondida", "country": "Chile", "lat": -24.27, "lon": -69.07, "owners": {"BHP": 0.55}},
    {"site": "Collahuasi", "country": "Chile", "lat": -20.98, "lon": -68.64, "owners": {"GLEN": 0.20}},
    {"site": "El Teniente", "country": "Chile", "lat": -34.09, "lon": -70.35, "owners": {"Codelco": 0.25}},
    {"site": "Cerro Verde", "country": "Peru", "lat": -16.53, "lon": -71.59, "owners": {"FCX": 0.20}},
    {"site": "Antamina", "country": "Peru", "lat": -9.54, "lon": -77.05, "owners": {"TECK": 0.25}},
    {"site": "Las Bambas", "country": "Peru", "lat": -14.10, "lon": -72.32, "owners": {"MMG": 0.70}},
    {"site": "Kamoa-Kakula", "country": "DR Congo", "lat": -10.77, "lon": 25.88, "owners": {"IVN": 0.90}},
    {"site": "Tenke Fungurume", "country": "DR Congo", "lat": -10.58, "lon": 26.18, "owners": {"CMOC": 0.40}},
]
COVERAGE["COPPER"]["sites"] = [{**m, "role": "Mine"} for m in COPPER_MINES] + [
    _s("Antofagasta", "Export port", "Chile", -23.65, -70.40),
    _s("Callao", "Export port", "Peru", -12.05, -77.15),
    _s("Yangshan, Shanghai", "Bonded stocks", "China", 30.60, 122.06),
]


def find(query):
    """Resolve a free text query (ticker or name) to a coverage key."""
    q = query.strip().upper()
    if q in COVERAGE:
        return q
    for k, v in COVERAGE.items():
        if q in v["name"].upper() or q == v["price"].upper():
            return k
    if q.rstrip("S") in COVERAGE:  # "soybean" -> SOYBEANS
        return q.rstrip("S")
    for k in COVERAGE:
        if k.startswith(q) and len(q) >= 3:
            return k
    return None


def sites_for_holdings(holdings):
    """Personalized monitors, 'what to watch': map each holding (company ticker or covered commodity) to the
    places it depends on. A company is mapped to every site where it has an output share; a commodity to all
    the sites of its coverage entry."""
    rows = []
    for h in holdings:
        key = find(h)
        if key is not None and COVERAGE[key]["kind"] == "commodity":
            rows += [{"holding": h, **s} for s in COVERAGE[key]["sites"]]
            continue
        for v in COVERAGE.values():
            for s in v["sites"]:
                if h in s.get("owners", {}):
                    rows.append({"holding": h, **s})
    seen, out = set(), []
    for r in rows:  # the same mine can appear under copper and gold
        k = (r["holding"], r["site"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
