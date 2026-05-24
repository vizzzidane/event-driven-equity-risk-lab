from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")
EVENT_PANEL_PATH = Path("results/event_panel.csv")

MATCHED_PLACEBO_EVENTS_PATH = Path("results/matched_placebo_events.csv")
MATCHED_PLACEBO_COMPARISON_PATH = Path("results/matched_placebo_comparison.csv")
MATCHED_PLACEBO_DIFF_PATH = Path("results/matched_placebo_differences.csv")

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
RANDOM_SEED = 42
EXCLUSION_WINDOW_DAYS = 20


def load_prices(path: Path = PROCESSED_DATA_PATH) -> pd.DataFrame:
    """Load processed price data."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing processed data file: {path}. Run `python src/data.py` first."
        )

    prices = pd.read_csv(path, parse_dates=["date"])

    required = {"date", "ticker", "adj_close", "return", "volume", "dollar_volume"}
    missing = required - set(prices.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def load_real_events(path: Path = EVENT_PANEL_PATH) -> pd.DataFrame:
    """Load real detected events."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing event panel: {path}. Run `python src/events.py` first."
        )

    events = pd.read_csv(path, parse_dates=["date"])

    required = {
        "ticker",
        "date",
        "event_direction",
        "future_5d_abnormal_return",
        "future_10d_abnormal_return",
        "future_20d_abnormal_return",
    }
    missing = required - set(events.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    events["year"] = events["date"].dt.year

    return events.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_forward_abnormal_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Add future stock returns, future market returns, and future abnormal returns.
    """
    out = prices.copy().sort_values(["ticker", "date"]).reset_index(drop=True)

    grouped = out.groupby("ticker", group_keys=False)

    out["future_5d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(-5) / s - 1
    )
    out["future_10d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(-10) / s - 1
    )
    out["future_20d_return"] = grouped["adj_close"].transform(
        lambda s: s.shift(-20) / s - 1
    )

    market = out.loc[out["ticker"] == MARKET_TICKER, ["date", "adj_close"]].copy()
    market = market.sort_values("date")

    market["future_5d_market_return"] = market["adj_close"].shift(-5) / market["adj_close"] - 1
    market["future_10d_market_return"] = market["adj_close"].shift(-10) / market["adj_close"] - 1
    market["future_20d_market_return"] = market["adj_close"].shift(-20) / market["adj_close"] - 1

    market_forward = market[
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

    out["year"] = out["date"].dt.year

    return out


def mark_event_neighborhoods(
    prices: pd.DataFrame,
    real_events: pd.DataFrame,
    exclusion_window_days: int = EXCLUSION_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Mark rows that are too close to real events.

    For each ticker, exclude dates within +/- exclusion_window_days calendar days
    of any detected real event. This prevents placebo dates from being event-adjacent.
    """
    out = prices.copy()
    out["near_real_event"] = False

    for ticker, ticker_events in real_events.groupby("ticker"):
        event_dates = ticker_events["date"].sort_values().to_numpy()

        ticker_mask = out["ticker"] == ticker

        for event_date in event_dates:
            start = pd.Timestamp(event_date) - pd.Timedelta(days=exclusion_window_days)
            end = pd.Timestamp(event_date) + pd.Timedelta(days=exclusion_window_days)

            window_mask = ticker_mask & out["date"].between(start, end)
            out.loc[window_mask, "near_real_event"] = True

    return out


def sample_matched_placebos(
    prices: pd.DataFrame,
    real_events: pd.DataFrame,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    For each real event, sample one placebo from:
    - same ticker
    - same year
    - not near a real event
    - has valid forward abnormal returns

    The placebo inherits the real event's direction so strategy comparison is fair.
    """
    rng = np.random.default_rng(seed)

    eligible = prices[
        prices["ticker"].isin(STOCK_TICKERS)
        & prices["future_5d_abnormal_return"].notna()
        & prices["future_10d_abnormal_return"].notna()
        & prices["future_20d_abnormal_return"].notna()
        & (~prices["near_real_event"])
    ].copy()

    sampled_rows = []
    skipped = []

    for idx, event in real_events.iterrows():
        ticker = event["ticker"]
        year = event["year"]

        candidates = eligible[
            (eligible["ticker"] == ticker)
            & (eligible["year"] == year)
        ]

        if candidates.empty:
            skipped.append((ticker, event["date"]))
            continue

        selected_idx = rng.choice(candidates.index.to_numpy(), size=1)[0]
        selected = candidates.loc[selected_idx].copy()

        selected["matched_real_ticker"] = ticker
        selected["matched_real_date"] = event["date"]
        selected["event_type"] = "matched_placebo"
        selected["event_direction"] = event["event_direction"]

        sampled_rows.append(selected)

    if not sampled_rows:
        raise RuntimeError("No matched placebo events could be sampled.")

    placebo = pd.DataFrame(sampled_rows)
    placebo = placebo.sort_values(["matched_real_date", "matched_real_ticker"]).reset_index(drop=True)

    if skipped:
        print(f"WARNING: skipped {len(skipped)} real events with no matched placebo candidate.")

    return placebo


def add_strategy_returns(events: pd.DataFrame) -> pd.DataFrame:
    """
    Add strategy-style return columns.
    """
    out = events.copy()
    out["event_sign"] = np.where(out["event_direction"] == "positive", 1.0, -1.0)

    for horizon in ["5d", "10d", "20d"]:
        col = f"future_{horizon}_abnormal_return"

        out[f"{horizon}_positive_event_drift"] = np.where(
            out["event_direction"] == "positive",
            out[col],
            np.nan,
        )

        out[f"{horizon}_negative_event_reversal"] = np.where(
            out["event_direction"] == "negative",
            out[col],
            np.nan,
        )

        out[f"{horizon}_all_event_drift"] = out["event_sign"] * out[col]
        out[f"{horizon}_all_event_reversal"] = -out["event_sign"] * out[col]

    return out


def safe_t_stat(values: pd.Series) -> float:
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    return float(stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit").statistic)


def safe_p_value(values: pd.Series) -> float:
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    return float(stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit").pvalue)


def summarize_strategy_set(events: pd.DataFrame, label: str) -> pd.DataFrame:
    """Summarize strategy returns for real or matched placebo events."""
    strategy_cols = {
        "positive_event_drift": "Positive Event Drift",
        "negative_event_reversal": "Negative Event Reversal",
        "all_event_drift": "All Event Drift",
        "all_event_reversal": "All Event Reversal",
    }

    rows = []

    for horizon in ["5d", "10d", "20d"]:
        for suffix, strategy_name in strategy_cols.items():
            col = f"{horizon}_{suffix}"
            values = events[col].dropna()

            rows.append(
                {
                    "sample": label,
                    "strategy": strategy_name,
                    "horizon": horizon,
                    "n_events": len(values),
                    "mean_return": values.mean(),
                    "avg_return_bps": values.mean() * 10_000,
                    "hit_rate": (values > 0).mean(),
                    "t_stat": safe_t_stat(values),
                    "p_value": safe_p_value(values),
                }
            )

    return pd.DataFrame(rows)


def build_difference_table(comparison: pd.DataFrame) -> pd.DataFrame:
    """
    Build real minus matched-placebo differences by strategy/horizon.
    """
    real = comparison[comparison["sample"] == "real_events"].copy()
    placebo = comparison[comparison["sample"] == "matched_placebo"].copy()

    merged = real.merge(
        placebo,
        on=["strategy", "horizon"],
        suffixes=("_real", "_placebo"),
    )

    rows = []

    for _, row in merged.iterrows():
        rows.append(
            {
                "strategy": row["strategy"],
                "horizon": row["horizon"],
                "n_events_real": row["n_events_real"],
                "n_events_placebo": row["n_events_placebo"],
                "mean_return_real": row["mean_return_real"],
                "mean_return_placebo": row["mean_return_placebo"],
                "mean_return_diff": row["mean_return_real"] - row["mean_return_placebo"],
                "avg_bps_diff": (row["mean_return_real"] - row["mean_return_placebo"]) * 10_000,
                "hit_rate_real": row["hit_rate_real"],
                "hit_rate_placebo": row["hit_rate_placebo"],
                "hit_rate_diff": row["hit_rate_real"] - row["hit_rate_placebo"],
            }
        )

    return pd.DataFrame(rows)


def run_matched_placebo_test() -> None:
    """Run matched placebo test."""
    prices = load_prices()
    real_events = load_real_events()

    prices = add_forward_abnormal_returns(prices)
    prices = mark_event_neighborhoods(prices, real_events)

    placebo = sample_matched_placebos(prices, real_events)

    real_strategy = add_strategy_returns(real_events)
    placebo_strategy = add_strategy_returns(placebo)

    MATCHED_PLACEBO_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    placebo_out_cols = [
        "ticker",
        "date",
        "matched_real_ticker",
        "matched_real_date",
        "event_type",
        "event_direction",
        "future_5d_abnormal_return",
        "future_10d_abnormal_return",
        "future_20d_abnormal_return",
    ]

    placebo[placebo_out_cols].to_csv(MATCHED_PLACEBO_EVENTS_PATH, index=False)

    real_summary = summarize_strategy_set(real_strategy, "real_events")
    placebo_summary = summarize_strategy_set(placebo_strategy, "matched_placebo")

    comparison = pd.concat([real_summary, placebo_summary], ignore_index=True)
    comparison.to_csv(MATCHED_PLACEBO_COMPARISON_PATH, index=False)

    differences = build_difference_table(comparison)
    differences.to_csv(MATCHED_PLACEBO_DIFF_PATH, index=False)

    print(f"Saved matched placebo events to: {MATCHED_PLACEBO_EVENTS_PATH}")
    print(f"Saved matched placebo comparison to: {MATCHED_PLACEBO_COMPARISON_PATH}")
    print(f"Saved matched placebo differences to: {MATCHED_PLACEBO_DIFF_PATH}")

    print()
    print("Matched placebo comparison")
    print("--------------------------")
    print(
        comparison[
            [
                "sample",
                "strategy",
                "horizon",
                "n_events",
                "mean_return",
                "avg_return_bps",
                "hit_rate",
                "t_stat",
                "p_value",
            ]
        ].to_string(index=False)
    )

    print()
    print("Real minus matched-placebo differences")
    print("--------------------------------------")
    print(
        differences[
            [
                "strategy",
                "horizon",
                "mean_return_real",
                "mean_return_placebo",
                "mean_return_diff",
                "avg_bps_diff",
                "hit_rate_diff",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    run_matched_placebo_test()