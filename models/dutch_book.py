"""
Categorical Dutch-Book Arbitrage Model.
Scans mutually exclusive and collectively exhaustive event sets where sum(P_i) < 1.00.
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

logger = logging.getLogger("DutchBookModel")


class DutchBookModel:
    """Scans mutually exclusive sets of event contracts for Dutch-book mispricings."""

    def __init__(self, fee_per_contract: int = FEE_TAKER_CENTS):
        self.fee = fee_per_contract

    def scan_event_set(self, event_ticker: str, markets: List[MarketQuote],
                       max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        opportunities = []
        if len(markets) < 2:
            return opportunities

        # Every bracket in the mutually exclusive set must have an active YES ask
        missing_ask = False
        sum_ask = 0
        legs = []

        for m in markets:
            if m.yes_ask is None or m.yes_ask <= 0 or m.yes_ask >= 100:
                missing_ask = True
                break
            sum_ask += m.yes_ask
            legs.append(TradeLeg(
                ticker=m.ticker,
                side=Side.YES,
                action=Action.BUY,
                price_cents=m.yes_ask,
                count=max_contracts
            ))

        if missing_ask:
            return opportunities

        # Total cost = sum of asks + fee for each leg
        total_fee = len(markets) * self.fee
        total_cost_per_set = sum_ask + total_fee

        # If total cost < 100 cents, purchasing 1 of each bracket guarantees 100 cents payout
        if total_cost_per_set < 100:
            profit_per_set = 100 - total_cost_per_set
            total_expected_cost = total_cost_per_set * max_contracts
            total_expected_payout = 100 * max_contracts
            total_net_profit = profit_per_set * max_contracts
            roi_pct = (total_net_profit / total_expected_cost) * 100.0

            bracket_desc = " + ".join([f"{m.ticker}({m.yes_ask}¢)" for m in markets[:4]])
            if len(markets) > 4:
                bracket_desc += f" + {len(markets)-4} more"

            desc = (
                f"Dutch-Book Arb on Event [{event_ticker}] across {len(markets)} brackets: "
                f"Buy all YES [{bracket_desc}]. Total Cost: {total_cost_per_set}¢, Guaranteed Profit: +{profit_per_set}¢"
            )

            opportunities.append(
                ArbitrageOpportunity(
                    arb_type=ArbType.DUTCH_BOOK,
                    description=desc,
                    legs=legs,
                    expected_cost_cents=total_expected_cost,
                    expected_payout_cents=total_expected_payout,
                    profit_cents=total_net_profit,
                    roi_pct=roi_pct,
                    timestamp=time.time()
                )
            )

        return opportunities

    def scan_all(self, exclusive_sets: Dict[str, List[MarketQuote]],
                 max_contracts: int = 1) -> List[ArbitrageOpportunity]:
        all_opps = []
        for event_ticker, markets in exclusive_sets.items():
            opps = self.scan_event_set(event_ticker, markets, max_contracts=max_contracts)
            all_opps.extend(opps)
        return all_opps
