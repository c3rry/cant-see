"""
Pre-Trade Risk Engine.
Enforces balance constraints, category exposure limits, fat-finger boundaries,
and drawdown circuit breakers.
"""

import logging
from typing import Tuple, Dict
from config import (
    MAX_POSITION_SIZE_CENTS,
    MIN_ORDER_PRICE_CENTS,
    MAX_ORDER_PRICE_CENTS,
    MAX_CATEGORY_EXPOSURE_PCT,
    MAX_DRAWDOWN_HALT_PCT
)
from core.types import ArbitrageOpportunity
from simulation.ledger import VirtualLedger

logger = logging.getLogger("RiskEngine")


class RiskEngine:
    """Pre-trade risk validator."""

    def __init__(self, ledger: VirtualLedger):
        self.ledger = ledger

    def validate_opportunity(self, opp: ArbitrageOpportunity,
                             category: str = "General") -> Tuple[bool, str]:
        """
        Runs comprehensive pre-trade risk checks.
        Returns (is_approved, rejection_reason).
        """
        # Check 1: Drawdown killswitch
        current_dd = self.ledger.drawdown_pct
        if current_dd >= (MAX_DRAWDOWN_HALT_PCT * 100.0):
            return False, f"CIRCUIT BREAKER TRIGGERED: Portfolio drawdown is {current_dd:.1f}% (Max: {MAX_DRAWDOWN_HALT_PCT*100}%)."

        # Check 2: Sufficient free cash
        if not self.ledger.can_afford(opp.expected_cost_cents):
            return False, f"Insufficient free cash ({self.ledger.free_cash_cents}¢ available, {opp.expected_cost_cents}¢ needed)."

        # Check 3: Max position size limit
        if opp.expected_cost_cents > MAX_POSITION_SIZE_CENTS:
            return False, f"Order cost ({opp.expected_cost_cents}¢) exceeds single position cap ({MAX_POSITION_SIZE_CENTS}¢)."

        # Check 4: Fat-finger & extreme price bounds
        for leg in opp.legs:
            if leg.price_cents < MIN_ORDER_PRICE_CENTS:
                return False, f"Price {leg.price_cents}¢ for {leg.ticker} below minimum threshold ({MIN_ORDER_PRICE_CENTS}¢)."
            if leg.price_cents > MAX_ORDER_PRICE_CENTS:
                return False, f"Price {leg.price_cents}¢ for {leg.ticker} above maximum threshold ({MAX_ORDER_PRICE_CENTS}¢)."

        # Check 5: Category concentration limit
        total_equity = self.ledger.total_equity_cents
        if total_equity > 0:
            current_category_exposure = 0
            for pos in self.ledger.positions.values():
                # Rough category check
                current_category_exposure += pos.collateral_locked_cents

            new_category_exposure = current_category_exposure + opp.expected_cost_cents
            if (new_category_exposure / total_equity) > MAX_CATEGORY_EXPOSURE_PCT:
                return False, f"Category exposure ({new_category_exposure/total_equity:.1%}) exceeds cap ({MAX_CATEGORY_EXPOSURE_PCT:.1%})."

        # Check 6: Non-zero positive expected profit
        if opp.profit_cents <= 0:
            return False, f"Expected profit {opp.profit_cents}¢ is not positive."

        return True, "Approved"
