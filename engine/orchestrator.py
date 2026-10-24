"""
Trading Orchestrator.
Coordinates market data ingestion, catalog indexing, arbitrage scanning,
risk gatekeeping, virtual order execution, and settlement simulation.
"""

import time
import logging
from typing import Dict, List, Optional
from config import (
    INITIAL_VIRTUAL_BALANCE_CENTS,
    MAX_CONTRACTS_PER_TRADE,
    SCAN_INTERVAL_SECONDS
)
from client.kalshi_client import KalshiClient
from core.catalog import MarketCatalog
from core.types import Side, ArbitrageOpportunity
from models.parity_arb import ParityArbModel
from models.dutch_book import DutchBookModel
from models.monotonicity import MonotonicityModel
from models.convergence import ConvergenceModel
from simulation.ledger import VirtualLedger
from simulation.simulator import VirtualExchange
from engine.risk import RiskEngine

logger = logging.getLogger("TradingOrchestrator")


class TradingOrchestrator:
    """End-to-end automated paper trading orchestrator for Kalshi."""

    def __init__(self, initial_capital_cents: int = INITIAL_VIRTUAL_BALANCE_CENTS):
        self.client = KalshiClient()
        self.catalog = MarketCatalog()
        self.ledger = VirtualLedger(initial_capital_cents)
        self.exchange = VirtualExchange(self.ledger)
        self.risk = RiskEngine(self.ledger)

        # Quantitative Alpha Models
        self.parity_model = ParityArbModel()
        self.dutch_model = DutchBookModel()
        self.monotonicity_model = MonotonicityModel()
        self.convergence_model = ConvergenceModel()

        self.cycle_count = 0
        self.total_opps_detected = 0
        self.total_opps_executed = 0

    def sync_market_data(self):
        """Fetches all open events and markets across the exchange and updates catalog."""
        logger.info("Synchronizing full Kalshi exchange catalog...")
        try:
            raw_events = self.client.get_all_open_events(max_pages=10)
            self.catalog.update_events(raw_events)
        except Exception as e:
            logger.warning(f"Event fetch non-critical error: {e}")

        raw_markets = self.client.get_all_open_markets(max_pages=20)
        self.catalog.update_markets(raw_markets)

    def check_settlements(self):
        """Checks if any currently held positions have resolved on Kalshi."""
        if not self.ledger.positions:
            return

        active_tickers = list(set(pos.ticker for pos in self.ledger.positions.values()))
        for ticker in active_tickers:
            quote = self.catalog.quotes_by_ticker.get(ticker)
            # If market is no longer in open catalog, query its status directly
            if not quote or quote.status != "open":
                try:
                    data = self.client.get_market(ticker)
                    m_data = data.get("market", {})
                    status = m_data.get("status")
                    result = m_data.get("result")  # "yes" or "no"

                    if status in ("finalized", "settled") and result in ("yes", "no"):
                        winning_side = Side.YES if result == "yes" else Side.NO
                        logger.info(f"Market {ticker} finalized with result: {result.upper()}!")
                        self.ledger.settle_contract(ticker, winning_side)
                except Exception as e:
                    logger.error(f"Error checking settlement for {ticker}: {e}")

    def scan_and_execute_cycle(self) -> Dict:
        """Executes a single end-to-end scan, risk-check, execution, and mark-to-market cycle."""
        self.cycle_count += 1
        cycle_start = time.time()
        logger.info(f"=== Starting Scan Cycle #{self.cycle_count} ===")

        # 1. Refresh exchange catalog
        self.sync_market_data()

        # 2. Check settlements of open positions
        self.check_settlements()

        # 3. Mark existing positions to market
        self.ledger.mark_to_market(self.catalog.quotes_by_ticker)

        # 4. Scan all models
        found_opps: List[ArbitrageOpportunity] = []

        # Model A: Complementary Parity Arb
        parity_opps = self.parity_model.scan_all(
            self.catalog.quotes_by_ticker,
            max_contracts=MAX_CONTRACTS_PER_TRADE
        )
        found_opps.extend(parity_opps)

        # Model B: Categorical Dutch-Book Arb
        dutch_opps = self.dutch_model.scan_all(
            self.catalog.get_mutually_exclusive_event_sets(),
            max_contracts=MAX_CONTRACTS_PER_TRADE
        )
        found_opps.extend(dutch_opps)

        # Model C: Scalar Monotonicity Arb
        mono_opps = self.monotonicity_model.scan_all(
            self.catalog.get_scalar_ladders(),
            max_contracts=MAX_CONTRACTS_PER_TRADE
        )
        found_opps.extend(mono_opps)

        # Model D: Terminal Convergence Yield
        conv_opps = self.convergence_model.scan_all(
            self.catalog.quotes_by_ticker,
            max_contracts=MAX_CONTRACTS_PER_TRADE
        )
        found_opps.extend(conv_opps)

        self.total_opps_detected += len(found_opps)

        # Sort opportunities by highest ROI first
        found_opps.sort(key=lambda x: x.roi_pct, reverse=True)

        # 5. Risk-filter and execute
        cycle_executed = 0
        for opp in found_opps:
            # Determine category of primary ticker
            primary_ticker = opp.legs[0].ticker if opp.legs else ""
            primary_quote = self.catalog.quotes_by_ticker.get(primary_ticker)
            category = primary_quote.category if primary_quote else "General"

            approved, reason = self.risk.validate_opportunity(opp, category=category)
            if approved:
                fills = self.exchange.execute_arbitrage(opp, self.catalog.quotes_by_ticker)
                if fills:
                    cycle_executed += 1
                    self.total_opps_executed += 1
            else:
                logger.debug(f"Opportunity rejected by RiskEngine: {reason} | {opp.description}")

        cycle_duration = time.time() - cycle_start
        summary = self.ledger.get_summary()
        summary["cycle_count"] = self.cycle_count
        summary["cycle_duration_sec"] = round(cycle_duration, 2)
        summary["total_markets_scanned"] = len(self.catalog.quotes_by_ticker)
        summary["opps_found_this_cycle"] = len(found_opps)
        summary["opps_executed_this_cycle"] = cycle_executed

        logger.info(
            f"=== Cycle #{self.cycle_count} Complete: {len(self.catalog.quotes_by_ticker)} markets scanned | "
            f"{len(found_opps)} opps found | {cycle_executed} executed | "
            f"Equity: ${summary['equity_dollars']:.2f} (Cash: ${summary['cash_dollars']:.2f}, Locked: ${summary['locked_collateral_dollars']:.2f}) | "
            f"Duration: {cycle_duration:.2f}s ==="
        )
        return summary

    def run_continuous(self, interval_sec: int = SCAN_INTERVAL_SECONDS, max_cycles: Optional[int] = None):
        """Runs the trading loop continuously."""
        logger.info(f"Starting continuous paper trading loop (interval: {interval_sec}s)...")
        try:
            while True:
                self.scan_and_execute_cycle()
                if max_cycles and self.cycle_count >= max_cycles:
                    logger.info(f"Reached max cycles ({max_cycles}). Stopping loop.")
                    break
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            logger.info("Trading loop halted by user (SIGINT).")
