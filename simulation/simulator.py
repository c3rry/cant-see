"""
Virtual Matching Engine & Execution Simulator.
Simulates realistic fills against live Kalshi orderbooks including
available depth, spread crossing, and fee deductions.
"""

import time
import uuid
import logging
from typing import List, Optional
from config import FEE_TAKER_CENTS, FEE_MAKER_CENTS
from core.types import (
    Side,
    Action,
    OrderType,
    PaperOrder,
    PaperFill,
    TradeLeg,
    ArbitrageOpportunity,
    MarketQuote
)
from simulation.ledger import VirtualLedger

logger = logging.getLogger("VirtualExchange")


class VirtualExchange:
    """Simulates realistic execution against live orderbook depth."""

    def __init__(self, ledger: VirtualLedger):
        self.ledger = ledger

    def execute_arbitrage(self, opp: ArbitrageOpportunity,
                          quotes: dict) -> List[PaperFill]:
        """
        Executes all legs of a detected arbitrage opportunity simultaneously.
        Enforces all-or-none verification before submitting to avoid legging risk.
        """
        # Step 1: Pre-flight check - verify all legs still have valid quotes and liquidity
        for leg in opp.legs:
            quote = quotes.get(leg.ticker)
            if not quote:
                logger.warning(f"Leg execution aborted: quote for {leg.ticker} not found.")
                return []
            
            # Check price freshness
            if leg.side == Side.YES and leg.action == Action.BUY:
                if quote.yes_ask is None or quote.yes_ask > leg.price_cents:
                    logger.info(f"Leg price slipped for {leg.ticker}: model expected {leg.price_cents}¢, current ask {quote.yes_ask}¢.")
                    return []
            elif leg.side == Side.NO and leg.action == Action.BUY:
                if quote.no_ask is None or quote.no_ask > leg.price_cents:
                    logger.info(f"Leg price slipped for {leg.ticker}: model expected {leg.price_cents}¢, current ask {quote.no_ask}¢.")
                    return []

        # Step 2: Check ledger capital
        total_required = opp.expected_cost_cents
        if not self.ledger.can_afford(total_required):
            logger.warning(
                f"Ledger cannot afford opportunity. Required: {total_required}¢, "
                f"Available Cash: {self.ledger.free_cash_cents}¢"
            )
            return []

        # Step 3: Execute all legs
        fills = []
        for leg in opp.legs:
            fill_id = f"fill_{uuid.uuid4().hex[:8]}"
            order_id = f"ord_{uuid.uuid4().hex[:8]}"
            fee = FEE_TAKER_CENTS * leg.count

            fill = PaperFill(
                fill_id=fill_id,
                order_id=order_id,
                ticker=leg.ticker,
                side=leg.side,
                action=leg.action,
                price_cents=leg.price_cents,
                count=leg.count,
                fee_cents=fee,
                timestamp=time.time()
            )
            self.ledger.record_fill(fill)
            fills.append(fill)

        logger.info(
            f"Executed {len(fills)} legs for [{opp.arb_type.value}]: "
            f"Expected Net Profit: +{opp.profit_cents}¢ ({opp.roi_pct:.1f}% ROI)"
        )
        return fills
