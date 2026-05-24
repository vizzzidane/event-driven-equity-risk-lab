from __future__ import annotations

from pathlib import Path

import pandas as pd

from universe import ACTIVE_STOCK_TICKERS, MARKET_TICKER


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")
EVENT_PANEL_PATH = Path("results/event_panel.csv")

EVENT_STRENGTH_THRESHOLD = 2.0
VOLUME_SHOCK_THRESHOLD = 1.2
MIN_AVG_DOLLAR_VOLUME = 50_000_000

FUTURE_HORIZONS = [5, 10, 20]


def load_processed_prices(path: Path = PROCESSED_DATA_PATH) -> pd.DataFrame:
    """Load processed price panel."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing processed data file: {path}. Run `python src/data.py` first."
        )

    prices = pd.read_csv(path, parse_dates=["date"])

    required = {
        "date",
        "ticker",
        "adj_close",
        "volume",
        "return",
        "dollar_volume",
    }
    missing = required - set(prices.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_market_adjusted_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Add SPY-adjusted abnormal returns."""
    market = prices.loc[
        prices["ticker"] == MARKET_TICKER,
        ["date", "return"],
    ].rename(columns={"return": "market_return"})

    if market.empty:
        raise ValueError(f"Market benchmark {MARKET_TICKER} not found in price data.")

    stocks = prices[prices["ticker"].isin(ACTIVE_STOCK_TICKERS)].copy()
    stocks = stocks.merge(market, on="date", how="left")

    stocks["abnormal_return"] = stocks["return"] - stocks["market_return"]

    return stocks.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_event_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Add event-strength and volume-shock features.

    Rolling baselines are shifted by one day to avoid using event-day values
    in the pre-event baseline.
    """
    out = prices.copy()
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    grouped = out.groupby("ticker", group_keys=False)

    out["rolling_20d_abnormal_vol"] = grouped["abnormal_return"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).std()
    )

    out["avg_20d_volume"] = grouped["volume"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).mean()
    )

    out["avg_20d_dollar_volume"] = grouped["dollar_volume"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).mean()
    )

    out["volume_shock"] = out["volume"] / out["avg_20d_volume"]

    out["event_strength"] = (
        out["abnormal_return"] / out["rolling_20d_abnormal_vol"]
    )

    out["abs_event_strength"] = out["event_strength"].abs()

    return out


def compound_forward_return(series: pd.Series, horizon: int) -> pd.Series:
    """
    Compute compounded future return over the next `horizon` trading days.

    For date t, this uses returns from t+1 to t+horizon.
    """
    return (
        (1 + series)
        .shift(-1)
        .rolling(window=horizon, min_periods=horizon)
        .apply(lambda values: values.prod() - 1, raw=True)
        .shift(-(horizon - 1))
    )


def add_future_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Add future stock and abnormal returns for event-study horizons."""
    out = prices.copy()
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    grouped = out.groupby("ticker", group_keys=False)

    for horizon in FUTURE_HORIZONS:
        out[f"future_{horizon}d_stock_return"] = grouped["return"].transform(
            lambda s, h=horizon: compound_forward_return(s, h)
        )

        out[f"future_{horizon}d_abnormal_return"] = grouped[
            "abnormal_return"
        ].transform(lambda s, h=horizon: compound_forward_return(s, h))

    return out


def detect_events(features: pd.DataFrame) -> pd.DataFrame:
    """
    Detect abnormal price-volume events.

    Positive event:
    - event_strength >= +2.0
    - volume_shock >= 1.2

    Negative event:
    - event_strength <= -2.0
    - volume_shock >= 1.2
    """
    base_filter = (
        features["event_strength"].abs().ge(EVENT_STRENGTH_THRESHOLD)
        & features["volume_shock"].ge(VOLUME_SHOCK_THRESHOLD)
        & features["avg_20d_dollar_volume"].ge(MIN_AVG_DOLLAR_VOLUME)
    )

    events = features[base_filter].copy()

    events["event_direction"] = events["event_strength"].apply(
        lambda value: "positive" if value > 0 else "negative"
    )

    events["event_type"] = events["event_direction"].map(
        {
            "positive": "positive_abnormal_price_volume",
            "negative": "negative_abnormal_price_volume",
        }
    )

    keep_cols = [
        "date",
        "ticker",
        "event_type",
        "event_direction",
        "event_strength",
        "abs_event_strength",
        "abnormal_return",
        "volume_shock",
        "avg_20d_dollar_volume",
        "rolling_20d_abnormal_vol",
        "future_5d_stock_return",
        "future_10d_stock_return",
        "future_20d_stock_return",
        "future_5d_abnormal_return",
        "future_10d_abnormal_return",
        "future_20d_abnormal_return",
    ]

    events = events[keep_cols].copy()
    events = events.dropna(
        subset=[
            "future_5d_abnormal_return",
            "future_10d_abnormal_return",
            "future_20d_abnormal_return",
        ]
    )

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def print_event_summary(events: pd.DataFrame) -> None:
    """Print basic event-panel summary."""
    print(f"Saved event panel to: {EVENT_PANEL_PATH}")
    print()
    print("Event panel summary")
    print("-------------------")
    print(f"Events: {len(events):,}")
    print(f"Tickers: {events['ticker'].nunique()}")
    print(f"Date range: {events['date'].min().date()} to {events['date'].max().date()}")

    print()
    print("Direction counts:")
    print(events["event_direction"].value_counts().to_string())

    print()
    print("Top 20 events by ticker:")
    print(events["ticker"].value_counts().head(20).to_string())

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


def build_event_panel() -> None:
    """Build and save abnormal price-volume event panel."""
    prices = load_processed_prices()
    prices = add_market_adjusted_returns(prices)
    features = add_event_features(prices)
    features = add_future_returns(features)

    events = detect_events(features)

    EVENT_PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(EVENT_PANEL_PATH, index=False)

    print_event_summary(events)


if __name__ == "__main__":
    build_event_panel()