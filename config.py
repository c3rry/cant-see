"""
Global Configuration for Kalshi Automated Trading & Paper Simulator.
All live order execution is strictly disabled by default.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

# Safety Guardrail - ALWAYS TRUE for Paper Trading
PAPER_MODE = True

# Kalshi API Credentials
KALSHI_KEY_ID = os.getenv("KALSHI_KEY_ID", "")
_private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_key.txt")
KALSHI_PRIVATE_KEY_PATH = str(ROOT_DIR / _private_key_path) if not os.path.isabs(_private_key_path) else _private_key_path

# Environment & Endpoints
KALSHI_USE_PROD = os.getenv("KALSHI_USE_PROD", "true").lower() in ("true", "1", "yes")

if KALSHI_USE_PROD:
    KALSHI_API_BASE_URL = "https://api.elections.kalshi.com"
    KALSHI_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
else:
    KALSHI_API_BASE_URL = "https://demo-api.kalshi.co"
    KALSHI_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"

# Virtual Ledger Constraints (Micro-Capital Mode)
INITIAL_VIRTUAL_BALANCE_CENTS = 1000  # $10.00 starting balance

# Risk Parameters
MAX_POSITION_SIZE_CENTS = 100          # Max $1.00 (10% of portfolio) per individual contract
MAX_CONTRACTS_PER_TRADE = 2            # Micro-lot sizing for $10 portfolio
MIN_ORDER_PRICE_CENTS = 2              # Prevent extreme tail fills (< 2¢)
MAX_ORDER_PRICE_CENTS = 98             # Prevent extreme overpriced buys (> 98¢)
MAX_CATEGORY_EXPOSURE_PCT = 0.35       # No single category exceeds 35% of total capital
MAX_DRAWDOWN_HALT_PCT = 0.15           # 15% drawdown circuit breaker

# Fee Assumptions (in cents per contract)
FEE_TAKER_CENTS = 1                    # Kalshi taker fee floor ~1¢ per contract
FEE_MAKER_CENTS = 0                    # Zero maker fees / maker rebate eligibility

# Scanner & Polling Configuration
MARKET_PAGE_LIMIT = 1000               # Max page size for Kalshi /markets
SCAN_INTERVAL_SECONDS = 15             # Interval between full market scans
