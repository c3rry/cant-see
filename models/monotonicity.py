"""
Scalar Strike Monotonicity Arbitrage Model.
Verifies cumulative distribution function (CDF) consistency across ordered strike ladders.
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

logger = logging.getLogger("MonotonicityModel")


class MonotonicityModel:
    """Detects inverted strike ladder pricing where a harder threshold trades higher than an easier one."""

    def __init__(self, fee_per_contract: int = FEE_TAKER_CENTS):
        self.fee = fee_per_contract

    def scan_ladder(self, ladder_name: str, ladder: List[MarketQuote],
                    max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        opportunities = []
        if len(ladder) < 2:
            return opportunities

        # Compare pairs (m_lower, m_higher) where strike(m_lower) < strike(m_higher)
        # Condition for monotonicity: P(S >= K_higher) <= P(S >= K_lower)
        # An arbitrage exists if Bid(K_higher) > Ask(K_lower) + 2*fees
        for i in range(len(ladder)):
            m_lower = ladder[i]
            for j in range(i + 1, len(ladder)):
                m_higher = ladder[j]

                if m_lower.yes_ask is None or m_higher.yes_bid is None:
                    continue

                if 0 < m_lower.yes_ask < 100 and 0 < m_higher.yes_bid < 100:
                    net_spread = m_higher.yes_bid - m_lower.yes_ask - (2 * self.fee)
                    if net_spread > 0:
                        # Free money: sell the higher strike, buy the lower strike
                        cost = (m_lower.yes_ask - m_higher.yes_bid + (2 * self.fee)) * max_contracts
                        # Net upfront credit received: abs(cost)
                        payout = max_contracts * 100
                        profit = net_spread * max_contracts
                        roi = (profit / (m_lower.yes_ask * max_contracts)) * 100.0

                        desc = (
                            f"Monotonicity Violation on [{ladder_name}]: "
                            f"Sell higher strike {m_higher.ticker}@{m_higher.yes_bid}¢, "
                            f"Buy lower strike {m_lower.ticker}@{m_lower.yes_ask}¢. "
                            f"Instant Net Credit: +{net_spread}¢/contract"
                        )

                        legs = [
                            TradeLeg(ticker=m_lower.ticker, side=Side.YES, action=Action.BUY, price_cents=m_lower.yes_ask, count=max_contracts),
                            TradeLeg(ticker=m_higher.ticker, side=Side.YES, action=Action.SELL, price_cents=m_higher.yes_bid, count=max_contracts),
                        ]

                        opportunities.append(
                            ArbitrageOpportunity(
                                arb_type=ArbType.MONOTONICITY,
                                description=desc,
                                legs=legs,
                                expected_cost_cents=max(0, cost),
                                expected_payout_cents=payout,
                                profit_cents=profit,
                                roi_pct=roi,
                                timestamp=time.time()
                            )
                        )

        return opportunities

    def scan_all(self, ladders: Dict[str, List[MarketQuote]],
                 max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        all_opps = []
        for name, ladder in ladders.items():
            opps = self.scan_ladder(name, ladder, max_contracts=max_contracts)
            all_opps.extend(opps)
        return all_opps
