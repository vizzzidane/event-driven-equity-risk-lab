from __future__ import annotations


MARKET_TICKER = "SPY"

# Initial MVP universe used in the first research pass.
MVP_STOCK_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "JPM",
    "XOM",
    "JNJ",
    "HD",
]

# Expanded liquid US large-cap universe.
#
# This is intentionally not the full S&P 500 yet.
# The goal is to increase statistical breadth while keeping data download,
# debugging, and result interpretation manageable.
EXPANDED_STOCK_TICKERS = [
    # Mega-cap technology / communication services
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "AVGO",
    "ORCL",
    "ADBE",
    "CRM",
    "AMD",
    "INTC",
    "CSCO",
    "QCOM",
    "TXN",
    "NFLX",
    "UBER",
    "NOW",
    "IBM",

    # Financials
    "JPM",
    "BAC",
    "WFC",
    "GS",
    "MS",
    "C",
    "AXP",
    "BLK",
    "SCHW",
    "SPGI",

    # Healthcare
    "JNJ",
    "UNH",
    "LLY",
    "ABBV",
    "MRK",
    "PFE",
    "TMO",
    "ABT",
    "DHR",
    "BMY",

    # Consumer discretionary / staples
    "HD",
    "LOW",
    "NKE",
    "MCD",
    "SBUX",
    "TGT",
    "WMT",
    "COST",
    "PG",
    "KO",
    "PEP",
    "PM",

    # Industrials
    "CAT",
    "DE",
    "GE",
    "HON",
    "UPS",
    "RTX",
    "LMT",
    "BA",
    "UNP",
    "ETN",

    # Energy / materials
    "XOM",
    "CVX",
    "COP",
    "SLB",
    "EOG",
    "LIN",
    "APD",
    "SHW",
    "FCX",
    "NEM",

    # Semiconductors / hardware-heavy names
    "AMAT",
    "LRCX",
    "KLAC",
    "MU",
    "ADI",
    "MRVL",

    # Other large liquid names
    "V",
    "MA",
    "PYPL",
    "DIS",
    "CMCSA",
    "T",
    "VZ",
    "NEE",
    "SO",
    "DUK",
]

# Active universe for the current project run.
#
# Change this single variable to switch between the original MVP universe
# and the expanded universe.
ACTIVE_STOCK_TICKERS = EXPANDED_STOCK_TICKERS

ALL_DOWNLOAD_TICKERS = ACTIVE_STOCK_TICKERS + [MARKET_TICKER]