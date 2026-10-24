"""
Unit and Integration Tests for Kalshi Low-Risk Paper Trading Platform.
"""

import pytest
from core.types import (
    MarketQuote,
    Side,
    Action,
    ArbType,
    TradeLeg,
    ArbitrageOpportunity,
    PaperFill
)
from models.parity_arb import ParityArbModel
from models.dutch_book import DutchBookModel
from models.monotonicity import MonotonicityModel
from simulation.ledger import VirtualLedger
from simulation.simulator import VirtualExchange
from engine.risk import RiskEngine
from client.kalshi_client import KalshiClient


def test_parity_arbitrage_detection():
    model = ParityArbModel(fee_per_contract=1)
    # YES ask = 40c, NO ask = 55c -> Total = 95c + 2c fee = 97c < 100c
    quote = MarketQuote(
        ticker="TEST-PARITY-1",
        event_ticker="EV-1",
        series_ticker="SER-1",
        category="Economics",
        title="Test Parity Market",
        yes_ask=40,
        no_ask=55,
        yes_ask_size=5
    )
    opps = model.scan_market(quote, max_contracts=2)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.arb_type == ArbType.PARITY
    # Expected cost: (40 + 55 + 2) * 2 = 194 cents
    assert opp.expected_cost_cents == 194
    # Expected payout: 100 * 2 = 200 cents
    assert opp.expected_payout_cents == 200
    assert opp.profit_cents == 6
    assert len(opp.legs) == 2


def test_parity_no_false_positive():
    model = ParityArbModel(fee_per_contract=1)
    # YES ask = 50c, NO ask = 52c -> Total = 102c + 2c fee = 104c > 100c (No arb)
    quote = MarketQuote(
        ticker="TEST-PARITY-2",
        event_ticker="EV-2",
        series_ticker="SER-2",
        category="Economics",
        title="Fair Market",
        yes_ask=50,
        no_ask=52
    )
    opps = model.scan_market(quote)
    assert len(opps) == 0


def test_dutch_book_detection():
    model = DutchBookModel(fee_per_contract=1)
    # 3 mutually exclusive brackets: 25c + 30c + 35c = 90c + 3c fee = 93c < 100c
    brackets = [
        MarketQuote(ticker="B1", event_ticker="EV-CAT", series_ticker="S", category="Politics", title="Bracket 1", yes_ask=25),
        MarketQuote(ticker="B2", event_ticker="EV-CAT", series_ticker="S", category="Politics", title="Bracket 2", yes_ask=30),
        MarketQuote(ticker="B3", event_ticker="EV-CAT", series_ticker="S", category="Politics", title="Bracket 3", yes_ask=35),
    ]
    opps = model.scan_event_set("EV-CAT", brackets, max_contracts=1)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.arb_type == ArbType.DUTCH_BOOK
    # Cost: 90 + 3 = 93 cents
    assert opp.expected_cost_cents == 93
    assert opp.expected_payout_cents == 100
    assert opp.profit_cents == 7
    assert len(opp.legs) == 3


def test_monotonicity_detection():
    model = MonotonicityModel(fee_per_contract=1)
    # Higher strike has bid of 60c, but lower strike has ask of 50c!
    ladder = [
        MarketQuote(ticker="L1", event_ticker="EV-LAD", series_ticker="S", category="Financials", title="S&P > 5000", floor_strike=5000, yes_ask=50),
        MarketQuote(ticker="L2", event_ticker="EV-LAD", series_ticker="S", category="Financials", title="S&P > 5100", floor_strike=5100, yes_bid=60),
    ]
    opps = model.scan_ladder("EV-LAD", ladder, max_contracts=1)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.arb_type == ArbType.MONOTONICITY
    # Edge: 60 - 50 - 2 = 8 cents
    assert opp.profit_cents == 8


def test_virtual_ledger_full_collateral_and_settlement():
    # Initialize ledger with $10.00 (1000 cents)
    ledger = VirtualLedger(initial_cash_cents=1000)
    assert ledger.free_cash_cents == 1000
    assert ledger.total_equity_cents == 1000

    # Fill 1: Buy 2 YES @ 40c (cost: 80c + 2c fee = 82c)
    fill = PaperFill(
        fill_id="f1",
        order_id="o1",
        ticker="MKT-1",
        side=Side.YES,
        action=Action.BUY,
        price_cents=40,
        count=2,
        fee_cents=2,
        timestamp=100.0
    )
    ledger.record_fill(fill)

    # Cash: 1000 - 82 = 918 cents. Locked collateral: 80 cents. Equity: 918 + 80 = 998 cents (minus 2c fee).
    assert ledger.cash_cents == 918
    assert ledger.locked_collateral_cents == 80
    assert ledger.total_equity_cents == 998

    # Settle market as WIN (YES won)
    # Payout: 2 * 100 = 200 cents returned to cash.
    # Collateral released: 80 cents. Net profit: 200 - 80 = 120 cents.
    ledger.settle_contract("MKT-1", winning_side=Side.YES)

    assert ledger.locked_collateral_cents == 0
    assert ledger.cash_cents == 918 + 200  # 1118 cents ($11.18)
    assert ledger.total_equity_cents == 1118
    assert ledger.realized_pnl_cents == 120 - 2  # 118 cents net profit


def test_risk_engine_blocks_over_allocation():
    ledger = VirtualLedger(initial_cash_cents=1000)
    risk = RiskEngine(ledger)

    # Opportunity costing 300 cents exceeds MAX_POSITION_SIZE_CENTS (100 cents)
    expensive_opp = ArbitrageOpportunity(
        arb_type=ArbType.PARITY,
        description="Too big",
        legs=[TradeLeg("T", Side.YES, Action.BUY, 150, 2)],
        expected_cost_cents=300,
        expected_payout_cents=350,
        profit_cents=50,
        roi_pct=16.6,
        timestamp=100.0
    )
    approved, reason = risk.validate_opportunity(expensive_opp)
    assert not approved
    assert "exceeds single position cap" in reason


def test_live_execution_guardrail():
    client = KalshiClient()
    # Attempting to call place_live_order while PAPER_MODE=True must raise PermissionError
    with pytest.raises(PermissionError) as exc_info:
        client.place_live_order(ticker="TEST", count=1)
    assert "CRITICAL GUARDRAIL: PAPER_MODE is active" in str(exc_info.value)
