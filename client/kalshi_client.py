"""
Robust REST client for Kalshi API v2 with rate limiting, error handling,
pagination, and strict paper trading execution protection.
"""

import time
import logging
from typing import Dict, Any, List, Optional
import requests

from config import (
    KALSHI_API_BASE_URL,
    KALSHI_KEY_ID,
    KALSHI_PRIVATE_KEY_PATH,
    PAPER_MODE,
    MARKET_PAGE_LIMIT
)
from client.auth import KalshiAuth
from core.types import MarketQuote

logger = logging.getLogger("KalshiClient")


class KalshiClient:
    """Handles communication with Kalshi's API v2."""

    def __init__(self, key_id: str = KALSHI_KEY_ID, private_key_path: str = KALSHI_PRIVATE_KEY_PATH):
        self.base_url = KALSHI_API_BASE_URL.rstrip("/")
        self.auth = KalshiAuth(key_id, private_key_path) if key_id else None
        self.session = requests.Session()
        self._last_request_time = 0.0
        self._min_request_interval = 0.08  # Max ~12 req/sec to stay well under rate limits

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None,
                 data: Optional[Dict[str, Any]] = None, authenticated: bool = False) -> Dict[str, Any]:
        self._throttle()
        url = f"{self.base_url}{endpoint}"
        
        headers = {}
        if authenticated:
            if not self.auth:
                raise ValueError("Authentication requested but Kalshi credentials were not provided.")
            headers = self.auth.sign_request(method, endpoint)
        else:
            headers = {"Accept": "application/json", "Content-Type": "application/json"}

        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data if data else None,
                headers=headers,
                timeout=15.0
            )
            
            if resp.status_code == 429:
                logger.warning("Rate limit hit (429). Backing off for 2.0s...")
                time.sleep(2.0)
                return self._request(method, endpoint, params, data, authenticated)
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error on {method} {url}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise

    # ─── Portfolio Endpoints ──────────────────────────────────────────────

    def get_portfolio_balance(self) -> Dict[str, Any]:
        """Fetches live portfolio balance from exchange (cents)."""
        return self._request("GET", "/trade-api/v2/portfolio/balance", authenticated=True)

    # ─── Market & Event Data Endpoints ────────────────────────────────────

    def get_markets(self, limit: int = MARKET_PAGE_LIMIT, cursor: Optional[str] = None,
                    status: str = "open", series_ticker: Optional[str] = None,
                    event_ticker: Optional[str] = None) -> Dict[str, Any]:
        params = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        return self._request("GET", "/trade-api/v2/markets", params=params, authenticated=False)

    def get_all_open_markets(self, max_pages: int = 15) -> List[Dict[str, Any]]:
        """Paginates through all active markets across the entire Kalshi exchange."""
        all_markets = []
        cursor = None
        for page in range(max_pages):
            data = self.get_markets(limit=MARKET_PAGE_LIMIT, cursor=cursor, status="open")
            markets = data.get("markets", [])
            all_markets.extend(markets)
            cursor = data.get("cursor")
            if not cursor or not markets:
                break
        logger.info(f"Retrieved {len(all_markets)} open markets across {page + 1} pages.")
        return all_markets

    def get_events(self, limit: int = 200, cursor: Optional[str] = None,
                   status: str = "open") -> Dict[str, Any]:
        params = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/trade-api/v2/events", params=params, authenticated=False)

    def get_all_open_events(self, max_pages: int = 8) -> List[Dict[str, Any]]:
        """Paginates through all active events with category and exclusivity metadata."""
        all_events = []
        cursor = None
        for _ in range(max_pages):
            data = self.get_events(limit=200, cursor=cursor, status="open")
            events = data.get("events", [])
            all_events.extend(events)
            cursor = data.get("cursor")
            if not cursor or not events:
                break
        return all_events

    def get_orderbook(self, ticker: str) -> Dict[str, Any]:
        """Fetches full orderbook depth for a single market."""
        return self._request("GET", f"/trade-api/v2/markets/{ticker}/orderbook", authenticated=False)

    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Fetches market details and current status."""
        return self._request("GET", f"/trade-api/v2/markets/{ticker}", authenticated=False)

    # ─── Live Execution Guardrail ─────────────────────────────────────────

    def place_live_order(self, *args, **kwargs):
        """Hard safety lock: NEVER allows live order submission in paper trading mode."""
        if PAPER_MODE:
            raise PermissionError(
                "CRITICAL GUARDRAIL: PAPER_MODE is active. "
                "Live order placement is strictly disabled. "
                "All trades must route to VirtualExchange."
            )
        raise NotImplementedError("Live execution path requires explicit configuration override.")
