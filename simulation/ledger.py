"""
Virtual Ledger for Paper Trading.
Implements full collateral tracking, mark-to-market accounting,
settlement processing, and drawdown monitoring with $10 initial balance.
"""

import time
import logging
from typing import Dict, List, Optional
from config import INITIAL_VIRTUAL_BALANCE_CENTS
from core.types import (
    Side,
    Action,
    PaperFill,
    PaperPosition,
    MarketQuote
)

logger = logging.getLogger("VirtualLedger")


class VirtualLedger:
    """Maintains paper cash, collateral, positions, and audited PnL."""

    def __init__(self, initial_cash_cents: int = INITIAL_VIRTUAL_BALANCE_CENTS):
        self.initial_capital_cents = initial_cash_cents
        self.cash_cents = initial_cash_cents
        self.locked_collateral_cents = 0
        self.realized_pnl_cents = 0
        self.unrealized_pnl_cents = 0
        self.total_fees_paid_cents = 0
        self.peak_equity_cents = initial_cash_cents

        self.positions: Dict[str, PaperPosition] = {}
        self.fills: List[PaperFill] = []
        self.trade_history: List[Dict] = []
        self.settlement_history: List[Dict] = []

    @property
    def total_equity_cents(self) -> int:
        """Total portfolio net liquidation value in cents."""
        return self.cash_cents + self.locked_collateral_cents + self.unrealized_pnl_cents

    @property
    def free_cash_cents(self) -> int:
        return self.cash_cents

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity_cents <= 0:
            return 0.0
        dd = (self.peak_equity_cents - self.total_equity_cents) / self.peak_equity_cents
        return max(0.0, dd * 100.0)

    def can_afford(self, required_cents: int) -> bool:
        """Verifies sufficient free cash for collateral and fees."""
        return self.cash_cents >= required_cents

    def record_fill(self, fill: PaperFill):
        """Processes an executed trade fill and updates balance and positions."""
        self.fills.append(fill)
        cost_of_contracts = fill.price_cents * fill.count
        total_cash_outflow = cost_of_contracts + fill.fee_cents

        if fill.action == Action.BUY:
            if self.cash_cents < total_cash_outflow:
                logger.error(f"Ledger cash deficit! Needed {total_cash_outflow}¢, has {self.cash_cents}¢.")
            self.cash_cents -= total_cash_outflow
            self.locked_collateral_cents += cost_of_contracts
            self.total_fees_paid_cents += fill.fee_cents
            self.realized_pnl_cents -= fill.fee_cents

            # Update or create position
            pos_key = f"{fill.ticker}_{fill.side.value}"
            if pos_key in self.positions:
                existing = self.positions[pos_key]
                new_count = existing.count + fill.count
                new_avg = ((existing.avg_price_cents * existing.count) + cost_of_contracts) / new_count
                existing.count = new_count
                existing.avg_price_cents = new_avg
                existing.collateral_locked_cents += cost_of_contracts
            else:
                self.positions[pos_key] = PaperPosition(
                    ticker=fill.ticker,
                    side=fill.side,
                    count=fill.count,
                    avg_price_cents=float(fill.price_cents),
                    collateral_locked_cents=cost_of_contracts
                )

        elif fill.action == Action.SELL:
            # Selling an existing position
            pos_key = f"{fill.ticker}_{fill.side.value}"
            if pos_key in self.positions:
                existing = self.positions[pos_key]
                realized = (fill.price_cents - existing.avg_price_cents) * fill.count - fill.fee_cents
                self.realized_pnl_cents += int(realized)
                self.cash_cents += (fill.price_cents * fill.count - fill.fee_cents)
                self.locked_collateral_cents -= int(existing.avg_price_cents * fill.count)
                existing.count -= fill.count
                if existing.count <= 0:
                    del self.positions[pos_key]

        # Update peak equity
        if self.total_equity_cents > self.peak_equity_cents:
            self.peak_equity_cents = self.total_equity_cents

        self.trade_history.append({
            "fill_id": fill.fill_id,
            "timestamp": fill.timestamp,
            "ticker": fill.ticker,
            "side": fill.side.value,
            "action": fill.action.value,
            "price_cents": fill.price_cents,
            "count": fill.count,
            "fee_cents": fill.fee_cents,
            "resulting_cash": self.cash_cents,
            "resulting_equity": self.total_equity_cents
        })

    def mark_to_market(self, quotes: Dict[str, MarketQuote]):
        """Recalculates current unrealized PnL based on live midpoints or bids."""
        unrealized = 0
        for pos_key, pos in self.positions.items():
            quote = quotes.get(pos.ticker)
            if not quote:
                continue

            current_price = None
            if pos.side == Side.YES:
                current_price = quote.yes_bid if quote.yes_bid is not None else quote.last_price
            else:
                current_price = quote.no_bid if quote.no_bid is not None else (100 - (quote.last_price or 50))

            if current_price is not None:
                pos.current_value_cents = int(current_price * pos.count)
                pos.unrealized_pnl_cents = int((current_price - pos.avg_price_cents) * pos.count)
                unrealized += pos.unrealized_pnl_cents

        self.unrealized_pnl_cents = unrealized
        if self.total_equity_cents > self.peak_equity_cents:
            self.peak_equity_cents = self.total_equity_cents

    def settle_contract(self, ticker: str, winning_side: Side):
        """
        Processes formal market settlement.
        Each winning contract pays 100 cents. Losing contracts pay 0 cents.
        Collateral is returned to free cash.
        """
        for side in (Side.YES, Side.NO):
            pos_key = f"{ticker}_{side.value}"
            if pos_key in self.positions:
                pos = self.positions.pop(pos_key)
                collateral_returned = pos.collateral_locked_cents
                self.locked_collateral_cents -= collateral_returned

                if side == winning_side:
                    payout = 100 * pos.count
                    net_profit = payout - collateral_returned
                    self.cash_cents += payout
                    self.realized_pnl_cents += net_profit
                    outcome_str = f"WIN (+{net_profit}¢)"
                else:
                    net_profit = -collateral_returned
                    self.realized_pnl_cents += net_profit
                    outcome_str = f"LOSS ({net_profit}¢)"

                logger.info(
                    f"Settled {ticker} [{side.value.upper()}]: {outcome_str}. "
                    f"Cash now: {self.cash_cents}¢ ($ {self.cash_cents/100:.2f})"
                )

                self.settlement_history.append({
                    "ticker": ticker,
                    "side": side.value,
                    "winning_side": winning_side.value,
                    "count": pos.count,
                    "collateral_released": collateral_returned,
                    "payout": 100 * pos.count if side == winning_side else 0,
                    "net_profit_cents": net_profit,
                    "timestamp": time.time()
                })

    def get_summary(self) -> Dict:
        """Returns clean performance metrics."""
        return {
            "initial_capital_dollars": self.initial_capital_cents / 100.0,
            "cash_dollars": self.cash_cents / 100.0,
            "locked_collateral_dollars": self.locked_collateral_cents / 100.0,
            "equity_dollars": self.total_equity_cents / 100.0,
            "realized_pnl_dollars": self.realized_pnl_cents / 100.0,
            "unrealized_pnl_dollars": self.unrealized_pnl_cents / 100.0,
            "total_pnl_dollars": (self.realized_pnl_cents + self.unrealized_pnl_cents) / 100.0,
            "total_fees_dollars": self.total_fees_paid_cents / 100.0,
            "drawdown_pct": self.drawdown_pct,
            "open_positions_count": len(self.positions),
            "total_fills_count": len(self.fills)
        }
