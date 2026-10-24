"""
Core data types, enums, and dataclasses for the Kalshi automated platform.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class Side(str, Enum):
    YES = "yes"
    NO = "no"


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ArbType(str, Enum):
    PARITY = "complementary_parity"
    DUTCH_BOOK = "categorical_dutch_book"
    MONOTONICITY = "strike_monotonicity"


@dataclass
class MarketQuote:
    """Represents a standardized snapshot of a Kalshi market orderbook top."""
    ticker: str
    event_ticker: str
    series_ticker: str
    category: str
    title: str
    yes_bid: Optional[int] = None       # In cents (0-100)
    yes_ask: Optional[int] = None       # In cents (0-100)
    no_bid: Optional[int] = None        # In cents (0-100)
    no_ask: Optional[int] = None        # In cents (0-100)
    yes_bid_size: int = 0
    yes_ask_size: int = 0
    last_price: Optional[int] = None    # In cents
    volume_24h: int = 0
    status: str = "open"
    strike_type: Optional[str] = None
    floor_strike: Optional[float] = None
    cap_strike: Optional[float] = None
    close_time: Optional[str] = None

    @property
    def has_active_spread(self) -> bool:
        """Returns True if there is a tradeable bid or ask."""
        return (self.yes_bid is not None and self.yes_bid > 0) or \
               (self.yes_ask is not None and 0 < self.yes_ask < 100)


@dataclass
class TradeLeg:
    """A single leg in a multi-contract or multi-side trade."""
    ticker: str
    side: Side
    action: Action
    price_cents: int
    count: int


@dataclass
class ArbitrageOpportunity:
    """A detected structural or relative-value opportunity."""
    arb_type: ArbType
    description: str
    legs: List[TradeLeg]
    expected_cost_cents: int
    expected_payout_cents: int
    profit_cents: int
    roi_pct: float
    timestamp: float


@dataclass
class PaperOrder:
    """Simulated order submitted to the virtual exchange."""
    order_id: str
    ticker: str
    side: Side
    action: Action
    order_type: OrderType
    price_cents: int
    count: int
    status: OrderStatus = OrderStatus.PENDING
    created_at: float = 0.0


@dataclass
class PaperFill:
    """Simulated execution fill."""
    fill_id: str
    order_id: str
    ticker: str
    side: Side
    action: Action
    price_cents: int
    count: int
    fee_cents: int
    timestamp: float


@dataclass
class PaperPosition:
    """Simulated open position tracking."""
    ticker: str
    side: Side
    count: int
    avg_price_cents: float
    collateral_locked_cents: int
    current_value_cents: int = 0
    unrealized_pnl_cents: int = 0
