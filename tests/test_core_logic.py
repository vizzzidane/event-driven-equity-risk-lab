from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest_abnormal import (
    annualized_sharpe,
    max_drawdown,
    apply_concurrency_cap,
)
from src.threshold_sensitivity import detect_negative_events
from src.signals import zscore
from src.walk_forward_optimized import split_train_test_year


def test_zscore_standardizes_series() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0])

    result = zscore(series)

    assert pytest.approx(result.mean(), abs=1e-12) == 0.0
    assert pytest.approx(result.std(ddof=0), abs=1e-12) == 1.0


def test_zscore_handles_constant_series() -> None:
    series = pd.Series([5.0, 5.0, 5.0])

    result = zscore(series)

    assert result.tolist() == [0.0, 0.0, 0.0]


def test_max_drawdown_calculation() -> None:
    equity_curve = pd.Series([1.0, 1.2, 1.1, 1.3, 0.91])

    result = max_drawdown(equity_curve)

    expected = 0.91 / 1.3 - 1.0
    assert result == pytest.approx(expected)


def test_annualized_sharpe_returns_nan_for_zero_volatility() -> None:
    returns = pd.Series([0.01, 0.01, 0.01])

    result = annualized_sharpe(returns)

    assert np.isnan(result)


def test_annualized_sharpe_positive_for_positive_returns() -> None:
    returns = pd.Series([0.01, -0.005, 0.02, 0.003, -0.002])

    result = annualized_sharpe(returns)

    assert result > 0


def test_detect_negative_events_applies_thresholds() -> None:
    features = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL", "MSFT", "MSFT"],
            "date": pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"]
            ),
            "event_strength": [-2.5, -1.0, -3.0, -2.1],
            "volume_shock": [1.3, 2.0, 0.8, 1.5],
            "avg_20d_dollar_volume": [
                100_000_000,
                100_000_000,
                100_000_000,
                10_000_000,
            ],
        }
    )

    events = detect_negative_events(
        features=features,
        event_strength_threshold=2.0,
        volume_shock_threshold=1.2,
    )

    assert len(events) == 1
    assert events.iloc[0]["ticker"] == "AAPL"
    assert events.iloc[0]["event_direction"] == "negative"


def test_apply_concurrency_cap_limits_active_trades() -> None:
    trades = pd.DataFrame(
        {
            "trade_id": [1, 2, 3],
            "ticker": ["AAPL", "MSFT", "NVDA"],
            "entry_date": pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2020-01-03"]
            ),
            "exit_date": pd.to_datetime(
                ["2020-01-10", "2020-01-10", "2020-01-10"]
            ),
            "net_abnormal_return": [0.01, 0.02, 0.03],
        }
    )

    accepted = apply_concurrency_cap(trades, max_concurrent_positions=2)

    assert len(accepted) == 2
    assert accepted["trade_id"].tolist() == [1, 2]
    assert "accepted_trade_id" in accepted.columns


def test_split_train_test_year_prevents_future_leakage() -> None:
    dates = pd.date_range("2016-01-01", "2025-12-31", freq="D")

    df = pd.DataFrame(
        {
            "date": dates,
            "value": np.arange(len(dates)),
        }
    )

    train_df, test_df = split_train_test_year(
        df=df,
        test_year=2022,
    )

    train_years = train_df["date"].dt.year.unique()
    test_years = test_df["date"].dt.year.unique()

    assert max(train_years) < 2022
    assert set(test_years) == {2022}

    assert train_df["date"].max() < test_df["date"].min()

def test_global_pacing_enforces_minimum_trade_spacing() -> None:
    from src.global_pacing_sensitivity import build_candidate_trades

    prices = pd.DataFrame(
        {
            "ticker": ["AAPL"] * 80,
            "date": pd.date_range("2020-01-01", periods=80, freq="D"),
            "adj_close": np.linspace(100, 140, 80),
            "abnormal_return": np.full(80, 0.001),
        }
    )

    events = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL", "AAPL"],
            "date": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-05",
                    "2020-01-20",
                ]
            ),
            "event_strength": [-2.5, -2.5, -2.5],
            "volume_shock": [1.5, 1.5, 1.5],
        }
    )

    trades = build_candidate_trades(
        prices=prices,
        events=events,
        min_days_between_new_trades=10,
    )

    accepted_event_dates = trades["event_date"].sort_values().tolist()

    assert len(accepted_event_dates) == 2

    spacing_days = (
        accepted_event_dates[1] - accepted_event_dates[0]
    ).days

    assert spacing_days >= 10

def test_transaction_costs_reduce_returns_correctly() -> None:
    from src.global_pacing_sensitivity import (
        build_daily_abnormal_portfolio_returns,
    )

    prices = pd.DataFrame(
        {
            "ticker": ["AAPL"] * 5,
            "date": pd.date_range("2020-01-01", periods=5, freq="D"),
            "abnormal_return": [0.01, 0.01, 0.01, 0.01, 0.01],
        }
    )

    trades = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "entry_date": [pd.Timestamp("2020-01-01")],
            "exit_date": [pd.Timestamp("2020-01-04")],
        }
    )

    portfolio = build_daily_abnormal_portfolio_returns(
        prices=prices,
        trades=trades,
        max_concurrent_positions=1,
        transaction_cost_bps_per_side=5.0,
    )

    gross_total = portfolio["portfolio_abnormal_return"].sum()

    net_total = portfolio["net_portfolio_abnormal_return"].sum()

    total_cost = portfolio["transaction_cost"].sum()

    expected_cost = 2 * (5.0 / 10_000)

    assert total_cost == pytest.approx(expected_cost)

    assert net_total < gross_total

    assert gross_total - net_total == pytest.approx(expected_cost)