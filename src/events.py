from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")
EVENT_PANEL_PATH = Path("results/event_panel.csv")

STOCK_TICKERS = [
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

MARKET_TICKER = "SPY"


def load_prices(path: Path = PROCESSED_DATA_PATH) -> pd.DataFrame:
    """Load processed price/return data."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing processed data file: {path}. Run `python src/data.py` first."
        )

    prices = pd.read_csv(path, parse_dates=["date"])

    required = {"date", "ticker", "adj_close", "volume", "return", "dollar_volume"}
    missing = required - set(prices.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_market_returns(
    prices: pd.DataFrame,
    market_ticker: str = MARKET_TICKER,
) -> pd.DataFrame:
    """
    Add market return column using SPY.
    """
    market = prices.loc[
        prices["ticker"] == market_ticker,
        ["date", "return"],
    ].rename(columns={"return": "market_return"})

    if market.empty:
        raise ValueError(f"Market ticker {market_ticker} not found in data.")

    out = prices.merge(market, on="date", how="left")
    return out


def add_event_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Add rolling volatility, abnormal return, volume shock, and pre-event momentum.

    This uses only information available up to the event date.
    """
    out = prices.copy()
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    out["abnormal_return"] = out["return"] - out["market_return"]

    grouped = out.groupby("ticker", group_keys=False)

    # Rolling volatility of abnormal returns.
    # Shift by 1 so event-day return is not included in the pre-event volatility estimate.
    out["rolling_20d_abnormal_vol"] = grouped["abnormal_return"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).std()
    )

    # Volume shock = current volume / trailing average volume.
    # Shift by 1 to avoid using event-day volume in the trailing average.
    out["avg_20d_volume"] = grouped["volume"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).mean()
    )
    out["volume_shock"] = out["volume"] / out["avg_20d_volume"]

    # Pre-event momentum: previous 20 trading days, excluding event day.
    out["pre_20d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(1) / s.shift(21) - 1
    )

    # Pre-event dollar volume for liquidity checks.
    out["avg_20d_dollar_volume"] = grouped["dollar_volume"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).mean()
    )

    # Future returns after event date.
    out["future_5d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(-5) / s - 1
    )
    out["future_10d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(-10) / s - 1
    )
    out["future_20d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(-20) / s - 1
    )

    # Future market returns for abnormal forward return calculations.
    market_prices = out.loc[out["ticker"] == MARKET_TICKER, ["date", "adj_close"]].copy()
    market_prices = market_prices.sort_values("date")

    market_prices["future_5d_market_return"] = (
        market_prices["adj_close"].shift(-5) / market_prices["adj_close"] - 1
    )
    market_prices["future_10d_market_return"] = (
        market_prices["adj_close"].shift(-10) / market_prices["adj_close"] - 1
    )
    market_prices["future_20d_market_return"] = (
        market_prices["adj_close"].shift(-20) / market_prices["adj_close"] - 1
    )

    market_forward = market_prices[
        [
            "date",
            "future_5d_market_return",
            "future_10d_market_return",
            "future_20d_market_return",
        ]
    ]

    out = out.merge(market_forward, on="date", how="left")

    out["future_5d_abnormal_return"] = (
        out["future_5d_return"] - out["future_5d_market_return"]
    )
    out["future_10d_abnormal_return"] = (
        out["future_10d_return"] - out["future_10d_market_return"]
    )
    out["future_20d_abnormal_return"] = (
        out["future_20d_return"] - out["future_20d_market_return"]
    )

    return out


def detect_events(
    features: pd.DataFrame,
    stock_tickers: list[str] = STOCK_TICKERS,
    abnormal_return_sigma_threshold: float = 2.0,
    min_volume_shock: float = 1.2,
    min_avg_dollar_volume: float = 50_000_000,
) -> pd.DataFrame:
    """
    Detect large abnormal price/volume events.

    Event definition:
    - stock ticker only, excluding SPY and VIX
    - absolute abnormal return exceeds threshold * trailing 20d abnormal vol
    - volume is at least min_volume_shock times trailing 20d average
    - trailing dollar volume passes liquidity threshold
    """
    out = features.copy()

    out = out[out["ticker"].isin(stock_tickers)].copy()

    out["event_strength"] = (
        out["abnormal_return"] / out["rolling_20d_abnormal_vol"]
    )

    conditions = (
        out["event_strength"].abs().ge(abnormal_return_sigma_threshold)
        & out["volume_shock"].ge(min_volume_shock)
        & out["avg_20d_dollar_volume"].ge(min_avg_dollar_volume)
    )

    events = out.loc[conditions].copy()

    events["event_direction"] = np.where(
        events["abnormal_return"] > 0,
        "positive",
        "negative",
    )

    events["event_type"] = "abnormal_price_volume"

    keep_cols = [
        "ticker",
        "date",
        "event_type",
        "event_direction",
        "return",
        "market_return",
        "abnormal_return",
        "event_strength",
        "rolling_20d_abnormal_vol",
        "volume",
        "volume_shock",
        "pre_20d_return",
        "avg_20d_dollar_volume",
        "future_5d_return",
        "future_10d_return",
        "future_20d_return",
        "future_5d_abnormal_return",
        "future_10d_abnormal_return",
        "future_20d_abnormal_return",
    ]

    events = events[keep_cols]
    events = events.dropna().sort_values(["date", "ticker"]).reset_index(drop=True)

    return events


def summarize_events(events: pd.DataFrame) -> None:
    """Print a simple summary of the event panel."""
    print()
    print("Event panel summary")
    print("-------------------")
    print(f"Events: {len(events):,}")
    print(f"Tickers: {events['ticker'].nunique()}")

    if len(events) == 0:
        return

    print(f"Date range: {events['date'].min().date()} to {events['date'].max().date()}")
    print()
    print("Direction counts:")
    print(events["event_direction"].value_counts().to_string())
    print()
    print("Events by ticker:")
    print(events["ticker"].value_counts().sort_index().to_string())
    print()
    print("Average future abnormal returns:")
    print(
        events[
            [
                "future_5d_abnormal_return",
                "future_10d_abnormal_return",
                "future_20d_abnormal_return",
            ]
        ]
        .mean()
        .to_string()
    )


def build_event_panel() -> pd.DataFrame:
    """Build and save the first event panel."""
    prices = load_prices()
    prices = add_market_returns(prices)
    features = add_event_features(prices)
    events = detect_events(features)

    EVENT_PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(EVENT_PANEL_PATH, index=False)

    print(f"Saved event panel to: {EVENT_PANEL_PATH}")
    summarize_events(events)

    return events


if __name__ == "__main__":
    build_event_panel()