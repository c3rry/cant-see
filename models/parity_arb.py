"""
Complementary Parity Arbitrage Model.
Exploits mispricings where P(YES) + P(NO) != $1.00.
"""

import time
import logging
from typing import List, Dict
from config import FEE_TAKER_CENTS
from core.types import (
    MarketQuote,
    ArbitrageOpportunity,
    ArbType,
    TradeLeg,
    Side,
    Action
)

logger = logging.getLogger("ParityArbModel")


class ParityArbModel:
    """Scans for buy-side and sell-side complementary parity dislocations."""

    def __init__(self, fee_per_contract: int = FEE_TAKER_CENTS):
        self.fee = fee_per_contract

    def scan_market(self, quote: MarketQuote, max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        opportunities = []
        if not quote.has_active_spread:
            return opportunities

        # ─── Long Parity Arbitrage: Buy YES + Buy NO < $1.00 ──────────
        # If yes_ask + no_ask + fees < 100 cents, we lock in a risk-free payout of 100 cents.
        if quote.yes_ask is not None and quote.no_ask is not None:
            if 0 < quote.yes_ask < 100 and 0 < quote.no_ask < 100:
                total_cost_per_unit = quote.yes_ask + quote.no_ask + (2 * self.fee)
                if total_cost_per_unit < 100:
                    profit_per_unit = 100 - total_cost_per_unit
                    count = min(max_contracts, quote.yes_ask_size or 1)
                    
                    expected_cost = total_cost_per_unit * count
                    expected_payout = 100 * count
                    net_profit = profit_per_unit * count
                    roi_pct = (net_profit / expected_cost) * 100.0

                    desc = (
                        f"Parity Dislocation on {quote.ticker}: "
                        f"Buy YES@{quote.yes_ask}¢ + Buy NO@{quote.no_ask}¢ "
                        f"(Total Cost: {total_cost_per_unit}¢, Edge: +{profit_per_unit}¢/contract)"
                    )

                    legs = [
                        TradeLeg(ticker=quote.ticker, side=Side.YES, action=Action.BUY, price_cents=quote.yes_ask, count=count),
                        TradeLeg(ticker=quote.ticker, side=Side.NO, action=Action.BUY, price_cents=quote.no_ask, count=count),
                    ]

                    opportunities.append(
                        ArbitrageOpportunity(
                            arb_type=ArbType.PARITY,
                            description=desc,
                            legs=legs,
                            expected_cost_cents=expected_cost,
                            expected_payout_cents=expected_payout,
                            profit_cents=net_profit,
                            roi_pct=roi_pct,
                            timestamp=time.time()
                        )
                    )

        return opportunities

    def scan_all(self, quotes: Dict[str, MarketQuote], max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        all_opps = []
        for quote in quotes.values():
            opps = self.scan_market(quote, max_contracts=max_contracts)
            all_opps.extend(opps)
        return all_opps
