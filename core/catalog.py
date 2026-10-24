"""
Market Catalog Manager.
Indexes markets by event, series, category, and strike ladder.
Identifies mutually exclusive outcome sets for Dutch-book arbitrage.
"""

import logging
from typing import Dict, List, Optional, Any
from core.types import MarketQuote

logger = logging.getLogger("MarketCatalog")


def _to_cents(dollar_val: Optional[Any]) -> Optional[int]:
    """Converts a dollar string/float (e.g. '0.4500' or 0.45) to integer cents (45)."""
    if dollar_val is None:
        return None
    try:
        val = float(dollar_val)
        return int(round(val * 100))
    except (ValueError, TypeError):
        return None


def _infer_category(ticker: str, series_ticker: str, explicit_cat: Optional[str]) -> str:
    """Infers high-level market sector from series prefix or metadata."""
    if explicit_cat and explicit_cat not in ("General", "Uncategorized", ""):
        return explicit_cat
    
    check_str = (series_ticker or ticker).upper()
    if any(k in check_str for k in ("RAIN", "TEMP", "HIGH", "SNOW", "HURRICANE", "WEATHER")):
        return "Climate & Weather"
    if any(k in check_str for k in ("INTR", "FED", "CPI", "GDP", "JOBS", "PAYROLL", "RATE", "RECESSION")):
        return "Economics & Rates"
    if any(k in check_str for k in ("PRES", "SENATE", "HOUSE", "GOV", "ELEC", "PRIMARY", "CONGRESS", "SUPREME")):
        return "Elections & Politics"
    if any(k in check_str for k in ("NASDAQ", "SP500", "BTC", "ETH", "CRYPTO", "OIL", "GOLD", "TREASURY")):
        return "Financials & Commodities"
    if any(k in check_str for k in ("PGA", "NFL", "NBA", "MLB", "SOCCER", "TENNIS", "SUPERBOWL", "UFC")):
        return "Sports"
    if any(k in check_str for k in ("SPOTIFY", "BOXOFFICE", "OSCAR", "EMMY", "GRAMMY", "STREAM", "MOVIE")):
        return "Entertainment & Media"
    if "MVECROSSCATEGORY" in check_str or "KXMVE" in check_str:
        return "Cross-Category Combos"
    if any(k in check_str for k in ("AI", "TECH", "SPACE", "TESLA", "APPLE", "GOOGLE", "MICROSOFT", "NVIDIA")):
        return "Science & Technology"
    return "General Events"


class MarketCatalog:
    """Maintains indexed hierarchy of open Kalshi markets and events."""

    def __init__(self):
        self.quotes_by_ticker: Dict[str, MarketQuote] = {}
        self.markets_by_event: Dict[str, List[MarketQuote]] = {}
        self.markets_by_series: Dict[str, List[MarketQuote]] = {}
        self.markets_by_category: Dict[str, List[MarketQuote]] = {}
        self.events_metadata: Dict[str, Dict] = {}

    def update_events(self, raw_events: List[Dict]):
        """Indexes event-level metadata (e.g. mutually_exclusive flag, category)."""
        for ev in raw_events:
            ticker = ev.get("event_ticker") or ev.get("ticker")
            if ticker:
                self.events_metadata[ticker] = {
                    "title": ev.get("title", ""),
                    "category": ev.get("category", "General"),
                    "mutually_exclusive": ev.get("mutually_exclusive", False),
                    "series_ticker": ev.get("series_ticker", "")
                }

    def update_markets(self, raw_markets: List[Dict]):
        """Parses and updates the complete market quote index."""
        self.quotes_by_ticker.clear()
        self.markets_by_event.clear()
        self.markets_by_series.clear()
        self.markets_by_category.clear()

        for rm in raw_markets:
            ticker = rm.get("ticker")
            status = rm.get("status", "active")
            if not ticker or status not in ("active", "open", "opened"):
                continue

            event_ticker = rm.get("event_ticker", "")
            series_ticker = rm.get("series_ticker", "")
            ev_meta = self.events_metadata.get(event_ticker, {})
            raw_cat = ev_meta.get("category", rm.get("category", ""))
            category = _infer_category(ticker, series_ticker, raw_cat)

            # Parse quotes in cents
            yes_bid = _to_cents(rm.get("yes_bid_dollars"))
            yes_ask = _to_cents(rm.get("yes_ask_dollars"))
            no_bid = _to_cents(rm.get("no_bid_dollars"))
            no_ask = _to_cents(rm.get("no_ask_dollars"))
            last_price = _to_cents(rm.get("last_price_dollars"))

            # Sizes
            try:
                yes_bid_size = int(float(rm.get("yes_bid_size_fp") or 0))
                yes_ask_size = int(float(rm.get("yes_ask_size_fp") or 0))
            except (ValueError, TypeError):
                yes_bid_size = 0
                yes_ask_size = 0

            quote = MarketQuote(
                ticker=ticker,
                event_ticker=event_ticker,
                series_ticker=rm.get("series_ticker", ev_meta.get("series_ticker", "")),
                category=category,
                title=rm.get("title", ""),
                yes_bid=yes_bid,
                yes_ask=yes_ask,
                no_bid=no_bid,
                no_ask=no_ask,
                yes_bid_size=yes_bid_size,
                yes_ask_size=yes_ask_size,
                last_price=last_price,
                volume_24h=_to_cents(rm.get("volume_24h_fp")) or 0,
                status=rm.get("status", "open"),
                strike_type=rm.get("strike_type"),
                floor_strike=rm.get("floor_strike"),
                cap_strike=rm.get("cap_strike"),
                close_time=rm.get("close_time")
            )

            self.quotes_by_ticker[ticker] = quote

            # Index by event
            if event_ticker:
                self.markets_by_event.setdefault(event_ticker, []).append(quote)

            # Index by series
            if quote.series_ticker:
                self.markets_by_series.setdefault(quote.series_ticker, []).append(quote)

            # Index by category
            self.markets_by_category.setdefault(category, []).append(quote)

        logger.info(
            f"Catalog indexed: {len(self.quotes_by_ticker)} markets, "
            f"{len(self.markets_by_event)} events, {len(self.markets_by_category)} categories."
        )

    def get_mutually_exclusive_event_sets(self) -> Dict[str, List[MarketQuote]]:
        """
        Returns all event groups where outcomes are mutually exclusive and collectively exhaustive.
        Useful for Categorical Dutch-Book scanning.
        """
        exclusive_sets = {}
        for event_ticker, markets in self.markets_by_event.items():
            ev_meta = self.events_metadata.get(event_ticker, {})
            # Either explicitly flagged by Kalshi or has multiple bracket markets in a known bracket event
            if ev_meta.get("mutually_exclusive") and len(markets) >= 2:
                exclusive_sets[event_ticker] = markets
        return exclusive_sets

    def get_scalar_ladders(self) -> Dict[str, List[MarketQuote]]:
        """
        Returns series or events with ordered strike ladders for monotonicity verification.
        """
        ladders = {}
        for key, markets in self.markets_by_event.items():
            strikes = [m for m in markets if m.floor_strike is not None or m.cap_strike is not None]
            if len(strikes) >= 2:
                # Sort by floor strike or cap strike
                strikes.sort(key=lambda m: (m.floor_strike if m.floor_strike is not None else m.cap_strike or 0))
                ladders[key] = strikes
        return ladders
