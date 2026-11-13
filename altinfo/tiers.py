"""Free and Institutional tiers (product description, 'Who it is for and how we charge').

The free tier never shows live satellite readings: a signal loses value once many investors see it.
`FEATURES` is the table of what each tier gets; `ticker_page_for` strips a ticker search page down to the free view.
In production the same flags would be enforced by the server for each logged-in client.
"""
import pandas as pd

FEATURES = [
    # feature, free, institutional
    ("Earnings and commodity calendar", "Yes", "Yes"),
    ("Headline prediction market odds", "Yes", "Yes"),
    ("Attention on X", "Yes", "Yes"),
    ("Ticker search", "Basic: price, markets, attention", "Full: satellite indices, supply chain, gap"),
    ("Event reports", "Released after each event", "Live, before each event"),
    ("Dashboard and gap ranking", "No", "Yes"),
    ("Live satellite readings", "Never", "Yes"),
    ("Personalized monitors", "No", "Yes, private to each client"),
    ("Custom sites to track", "No", "Yes"),
]

FREE_SECTIONS = {"profile", "price", "markets", "attention", "events", "linked", "signals"}


def table():
    return pd.DataFrame(FEATURES, columns=["Feature", "Free", "Institutional"])


def ticker_page_for(page: dict, tier: str):
    """Institutional: the full page. Free: no satellite indices, no supply chain alerts, no gap score."""
    if tier.lower().startswith("inst"):
        return dict(page, tier="Institutional")
    out = {k: v for k, v in page.items() if k in FREE_SECTIONS}
    out["tier"] = "Free"
    return out


def report_available(tier: str, event_date, today):
    """Free users see a report only once the event has happened."""
    return tier.lower().startswith("inst") or pd.Timestamp(today) > pd.Timestamp(event_date)
