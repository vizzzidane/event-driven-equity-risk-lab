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