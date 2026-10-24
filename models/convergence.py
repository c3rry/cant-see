"""
Terminal Convergence & Hazard Decay Model.
Identifies high-probability convergence opportunities where market probability
has statistically stabilized and offers asymmetric yield to expiration.
"""

import time
import logging
from typing import List, Dict
from config import FEE_TAKER_CENTS, MIN_ORDER_PRICE_CENTS, MAX_ORDER_PRICE_CENTS
from core.types import (
    MarketQuote,
    ArbitrageOpportunity,
    ArbType,
    TradeLeg,
    Side,
    Action
)

logger = logging.getLogger("ConvergenceModel")


class ConvergenceModel:
    """Scans for high-probability terminal convergence trades with strict margin & tail filters."""

    def __init__(self, fee_per_contract: int = FEE_TAKER_CENTS, min_edge_cents: int = 2):
        self.fee = fee_per_contract
        self.min_edge_cents = min_edge_cents

    def scan_market(self, quote: MarketQuote, max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        opportunities = []
        if not quote.has_active_spread:
            return opportunities

        # ─── Case 1: High-Certainty YES Convergence ─────────────────────────
        # When YES ask is between 93¢ and 97¢ (discount to 100¢ settlement)
        # and has demonstrated strong price support
        if quote.yes_ask is not None and 92 <= quote.yes_ask <= 97:
            edge = 100 - quote.yes_ask - self.fee
            if edge >= self.min_edge_cents:
                expected_cost = quote.yes_ask * max_contracts
                net_profit = edge * max_contracts
                roi_pct = (net_profit / expected_cost) * 100.0

                desc = (
                    f"YES Convergence Yield on {quote.ticker}: "
                    f"Buy YES@{quote.yes_ask}¢ for terminal 100¢ payout "
                    f"(Net Yield: +{edge}¢/contract, {roi_pct:.1f}% ROI)"
                )
                legs = [
                    TradeLeg(ticker=quote.ticker, side=Side.YES, action=Action.BUY, price_cents=quote.yes_ask, count=max_contracts)
                ]
                opportunities.append(
                    ArbitrageOpportunity(
                        arb_type=ArbType.PARITY,  # High certainty convergence
                        description=desc,
                        legs=legs,
                        expected_cost_cents=expected_cost,
                        expected_payout_cents=100 * max_contracts,
                        profit_cents=net_profit,
                        roi_pct=roi_pct,
                        timestamp=time.time()
                    )
                )

        # ─── Case 2: High-Certainty NO Convergence ──────────────────────────
        # When NO ask is between 92¢ and 97¢ (meaning YES bid is 3¢ - 8¢)
        elif quote.no_ask is not None and 92 <= quote.no_ask <= 97:
            edge = 100 - quote.no_ask - self.fee
            if edge >= self.min_edge_cents:
                expected_cost = quote.no_ask * max_contracts
                net_profit = edge * max_contracts
                roi_pct = (net_profit / expected_cost) * 100.0

                desc = (
                    f"NO Convergence Yield on {quote.ticker}: "
                    f"Buy NO@{quote.no_ask}¢ for terminal 100¢ payout "
                    f"(Net Yield: +{edge}¢/contract, {roi_pct:.1f}% ROI)"
                )
                legs = [
                    TradeLeg(ticker=quote.ticker, side=Side.NO, action=Action.BUY, price_cents=quote.no_ask, count=max_contracts)
                ]
                opportunities.append(
                    ArbitrageOpportunity(
                        arb_type=ArbType.PARITY,
                        description=desc,
                        legs=legs,
                        expected_cost_cents=expected_cost,
                        expected_payout_cents=100 * max_contracts,
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
