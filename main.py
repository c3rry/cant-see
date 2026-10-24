"""
Main entry point for Kalshi Automated Paper Trading Platform.
Monitors all active Kalshi markets, scans for low-risk structural arbitrage,
and executes against a high-fidelity $10 virtual ledger.
"""

import sys
import time
import argparse
import logging
from config import (
    PAPER_MODE,
    INITIAL_VIRTUAL_BALANCE_CENTS,
    SCAN_INTERVAL_SECONDS
)
from engine.orchestrator import TradingOrchestrator


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=format_str, datefmt="%H:%M:%S")


def print_banner():
    banner = f"""
================================================================================
          KALSHI INSTITUTIONAL-GRADE AUTOMATED TRADING PLATFORM
                       (STRICT PAPER TRADING MODE)
================================================================================
 [!] Execution Mode      : {"SIMULATED / PAPER TRADING ONLY" if PAPER_MODE else "LIVE"}
 [$] Virtual Capital     : ${INITIAL_VIRTUAL_BALANCE_CENTS / 100:.2f}
 [@] Exchange Target     : ALL ACTIVE KALSHI MARKETS (Exchange-wide)
 [*] Active Models       : 
     1. Complementary Parity Arbitrage  (P(YES) + P(NO) != 1.00)
     2. Categorical Dutch-Book Scanner  (Sum(P_i) != 1.00)
     3. Scalar Strike Monotonicity      (CDF Inversion Check)
     4. Terminal Convergence Yield      (Hazard Decay / Boundary Harvesting)
 [*] Execution Safeguards: Pre-Trade Risk Gateway, FIFO Depth, Full Collateral
================================================================================
"""
    print(banner)


def format_summary_dashboard(summary: dict, orchestrator: TradingOrchestrator):
    catalog = orchestrator.catalog
    ledger = orchestrator.ledger

    print("\n" + "="*80)
    print(f"                       PAPER PORTFOLIO TELEMETRY (Cycle #{summary.get('cycle_count', 1)})")
    print("="*80)
    print(f"  Total Portfolio Equity : ${summary['equity_dollars']:.2f}")
    print(f"  Available Free Cash    : ${summary['cash_dollars']:.2f}")
    print(f"  Locked Collateral      : ${summary['locked_collateral_dollars']:.2f}")
    print(f"  Realized PnL           : ${summary['realized_pnl_dollars']:+.2f}")
    print(f"  Unrealized MTM PnL     : ${summary['unrealized_pnl_dollars']:+.2f}")
    print(f"  Total Fees Paid        : ${summary['total_fees_dollars']:.2f}")
    print(f"  Current Drawdown       : {summary['drawdown_pct']:.2f}%")
    print(f"  Open Positions         : {summary['open_positions_count']}")
    print(f"  Total Executed Fills   : {summary['total_fills_count']}")
    print("-" * 80)
    print(f"  Active Markets Scanned : {summary['total_markets_scanned']}")
    print(f"  Categories Indexed     : {len(catalog.markets_by_category)}")
    for cat, mkts in sorted(catalog.markets_by_category.items(), key=lambda x: len(x[1]), reverse=True)[:6]:
        print(f"    - {cat:<24}: {len(mkts)} markets")
    print("-" * 80)

    if ledger.positions:
        print("  CURRENT OPEN POSITIONS:")
        for key, pos in ledger.positions.items():
            print(
                f"    * {pos.ticker} [{pos.side.value.upper()}] x {pos.count} contracts | "
                f"Avg Cost: {pos.avg_price_cents:.1f}¢ | Locked: {pos.collateral_locked_cents}¢ | "
                f"MTM Unrealized: {pos.unrealized_pnl_cents:+}¢"
            )
        print("-" * 80)

    if ledger.trade_history:
        print(f"  RECENT EXECUTIONS (Last 5 Fills):")
        for trade in ledger.trade_history[-5:]:
            print(
                f"    [{trade['fill_id']}] {trade['action'].upper()} {trade['count']}x {trade['ticker']} "
                f"({trade['side'].upper()}) @ {trade['price_cents']}¢ (Fee: {trade['fee_cents']}¢) -> "
                f"Cash: ${trade['resulting_cash']/100:.2f}"
            )
        print("-" * 80)
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Kalshi Low-Risk Automated Paper Trader")
    parser.add_argument("--once", action="store_true", help="Run a single scan & execution cycle across all markets")
    parser.add_argument("--continuous", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=SCAN_INTERVAL_SECONDS, help="Seconds between scan cycles")
    parser.add_argument("--cycles", type=int, default=None, help="Maximum number of cycles before exiting")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    print_banner()

    orchestrator = TradingOrchestrator(initial_capital_cents=INITIAL_VIRTUAL_BALANCE_CENTS)

    if args.once or (not args.continuous and args.cycles == 1):
        summary = orchestrator.scan_and_execute_cycle()
        format_summary_dashboard(summary, orchestrator)
    else:
        # Default or continuous mode
        try:
            while True:
                summary = orchestrator.scan_and_execute_cycle()
                format_summary_dashboard(summary, orchestrator)
                if args.cycles and orchestrator.cycle_count >= args.cycles:
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nShutting down paper trader gracefully...")


if __name__ == "__main__":
    main()
