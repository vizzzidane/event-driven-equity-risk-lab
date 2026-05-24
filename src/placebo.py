from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")
EVENT_PANEL_PATH = Path("results/event_panel.csv")

PLACEBO_EVENTS_PATH = Path("results/placebo_events.csv")
PLACEBO_COMPARISON_PATH = Path("results/placebo_comparison.csv")

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

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def add_forward_abnormal_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Add future stock returns, future market returns, and future abnormal returns.

    This mirrors the forward-return logic in src/events.py.
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

    return out


def sample_placebo_events(
    prices: pd.DataFrame,
    n_events: int,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Randomly sample stock-date rows as placebo events.

    We avoid the final 20 trading days because forward returns would be missing.
    """
    rng = np.random.default_rng(seed)

    eligible = prices[
        prices["ticker"].isin(STOCK_TICKERS)
        & prices["future_20d_abnormal_return"].notna()
        & prices["future_10d_abnormal_return"].notna()
        & prices["future_5d_abnormal_return"].notna()
    ].copy()

    if len(eligible) < n_events:
        raise ValueError(
            f"Not enough eligible placebo rows. Needed {n_events}, got {len(eligible)}."
        )

    sample_indices = rng.choice(eligible.index.to_numpy(), size=n_events, replace=False)

    placebo = eligible.loc[sample_indices].copy()
    placebo = placebo.sort_values(["date", "ticker"]).reset_index(drop=True)

    # Randomly assign positive/negative event direction using real-event proportions later.
    placebo["event_type"] = "random_placebo"

    return placebo


def assign_placebo_directions(
    placebo: pd.DataFrame,
    real_events: pd.DataFrame,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Assign placebo directions using the same positive/negative proportion as real events.
    """
    rng = np.random.default_rng(seed)

    positive_share = (real_events["event_direction"] == "positive").mean()

    out = placebo.copy()
    random_values = rng.random(len(out))

    out["event_direction"] = np.where(
        random_values < positive_share,
        "positive",
        "negative",
    )

    return out


def add_directional_strategy_returns(events: pd.DataFrame) -> pd.DataFrame:
    """
    Add strategy-style returns:
    - positive_event_drift: positive events, future abnormal return
    - negative_event_reversal: negative events, future abnormal return
    - all_event_drift: trade in event direction
    - all_event_reversal: trade opposite event direction
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
    """One-sample t-stat against zero."""
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    return float(stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit").statistic)


def safe_p_value(values: pd.Series) -> float:
    """One-sample p-value against zero."""
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    return float(stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit").pvalue)


def summarize_strategy_set(
    events: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    """Summarize strategy-style returns for real or placebo events."""
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


def build_placebo_comparison() -> pd.DataFrame:
    """Build real-vs-placebo strategy comparison."""
    prices = load_prices()
    real_events = load_real_events()

    prices = add_forward_abnormal_returns(prices)

    placebo = sample_placebo_events(
        prices=prices,
        n_events=len(real_events),
        seed=RANDOM_SEED,
    )
    placebo = assign_placebo_directions(placebo, real_events, seed=RANDOM_SEED)

    real_strategy = add_directional_strategy_returns(real_events)
    placebo_strategy = add_directional_strategy_returns(placebo)

    placebo_out_cols = [
        "ticker",
        "date",
        "event_type",
        "event_direction",
        "future_5d_abnormal_return",
        "future_10d_abnormal_return",
        "future_20d_abnormal_return",
    ]
    placebo[placebo_out_cols].to_csv(PLACEBO_EVENTS_PATH, index=False)

    real_summary = summarize_strategy_set(real_strategy, "real_events")
    placebo_summary = summarize_strategy_set(placebo_strategy, "placebo_events")

    comparison = pd.concat([real_summary, placebo_summary], ignore_index=True)

    comparison.to_csv(PLACEBO_COMPARISON_PATH, index=False)

    return comparison


def print_comparison(comparison: pd.DataFrame) -> None:
    """Print compact real-vs-placebo comparison."""
    print()
    print("Real vs placebo comparison")
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

    focus = comparison[
        (comparison["strategy"].isin(["Positive Event Drift", "Negative Event Reversal"]))
        & (comparison["horizon"].isin(["10d", "20d"]))
    ].copy()

    print()
    print("Focused comparison, main candidates")
    print("-----------------------------------")
    print(
        focus[
            [
                "sample",
                "strategy",
                "horizon",
                "mean_return",
                "avg_return_bps",
                "hit_rate",
                "t_stat",
            ]
        ].to_string(index=False)
    )


def run_placebo_test() -> None:
    """Run placebo event test."""
    PLACEBO_COMPARISON_PATH.parent.mkdir(parents=True, exist_ok=True)

    comparison = build_placebo_comparison()

    print(f"Saved placebo events to: {PLACEBO_EVENTS_PATH}")
    print(f"Saved placebo comparison to: {PLACEBO_COMPARISON_PATH}")

    print_comparison(comparison)


if __name__ == "__main__":
    run_placebo_test()