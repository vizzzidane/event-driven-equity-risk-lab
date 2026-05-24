from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")

THRESHOLD_SENSITIVITY_PATH = Path("results/threshold_sensitivity.csv")

STRATEGY_NAME = "negative_event_reversal_30d_abnormal"

HOLD_DAYS = 30
MAX_CONCURRENT_POSITIONS = 5
TRANSACTION_COST_BPS_PER_SIDE = 5.0

THRESHOLD_GRID = [
    {"event_strength_threshold": 1.5, "volume_shock_threshold": 1.0},
    {"event_strength_threshold": 2.0, "volume_shock_threshold": 1.2},
    {"event_strength_threshold": 2.5, "volume_shock_threshold": 1.5},
    {"event_strength_threshold": 3.0, "volume_shock_threshold": 2.0},
    {"event_strength_threshold": 3.5, "volume_shock_threshold": 2.5},
]

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


@dataclass(frozen=True)
class Trade:
    trade_id: int
    ticker: str
    event_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    gross_stock_return: float
    gross_abnormal_return: float
    net_abnormal_return: float
    holding_days: int
    event_strength: float
    volume_shock: float
    transaction_cost_bps_round_trip: float


def load_prices(path: Path = PROCESSED_DATA_PATH) -> pd.DataFrame:
    """Load processed stock and benchmark data."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing processed data file: {path}. Run `python src/data.py` first."
        )

    prices = pd.read_csv(path, parse_dates=["date"])

    required = {"date", "ticker", "adj_close", "return", "volume", "dollar_volume"}
    missing = required - set(prices.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)

    market_returns = prices.loc[
        prices["ticker"] == MARKET_TICKER,
        ["date", "return"],
    ].rename(columns={"return": "market_return"})

    if market_returns.empty:
        raise ValueError(f"Market ticker {MARKET_TICKER} not found.")

    prices = prices.merge(market_returns, on="date", how="left")
    prices["abnormal_return"] = prices["return"] - prices["market_return"]

    prices = prices[
        prices["ticker"].isin(STOCK_TICKERS + [MARKET_TICKER])
    ].copy()

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_event_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Rebuild event features from processed price data.

    This avoids depending on a fixed event_panel.csv and lets us test
    multiple event thresholds fairly.
    """
    out = prices.copy()
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    stock_rows = out[out["ticker"].isin(STOCK_TICKERS)].copy()

    grouped = stock_rows.groupby("ticker", group_keys=False)

    stock_rows["rolling_20d_abnormal_vol"] = grouped["abnormal_return"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).std()
    )

    stock_rows["avg_20d_volume"] = grouped["volume"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).mean()
    )

    stock_rows["volume_shock"] = stock_rows["volume"] / stock_rows["avg_20d_volume"]

    stock_rows["avg_20d_dollar_volume"] = grouped["dollar_volume"].transform(
        lambda s: s.shift(1).rolling(window=20, min_periods=20).mean()
    )

    stock_rows["event_strength"] = (
        stock_rows["abnormal_return"] / stock_rows["rolling_20d_abnormal_vol"]
    )

    return stock_rows.sort_values(["ticker", "date"]).reset_index(drop=True)


def detect_negative_events(
    features: pd.DataFrame,
    event_strength_threshold: float,
    volume_shock_threshold: float,
    min_avg_dollar_volume: float = 50_000_000,
) -> pd.DataFrame:
    """
    Detect negative abnormal price-volume events under a threshold setting.

    Rule:
    - event_strength <= -event_strength_threshold
    - volume_shock >= volume_shock_threshold
    - average dollar volume >= liquidity threshold
    """
    events = features[
        features["event_strength"].le(-event_strength_threshold)
        & features["volume_shock"].ge(volume_shock_threshold)
        & features["avg_20d_dollar_volume"].ge(min_avg_dollar_volume)
    ].copy()

    events["event_direction"] = "negative"
    events["event_type"] = "negative_abnormal_price_volume"

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def get_ticker_price_map(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Create ticker -> price map."""
    stock_prices = prices[prices["ticker"].isin(STOCK_TICKERS)].copy()

    return {
        ticker: ticker_prices.sort_values("date").reset_index(drop=True)
        for ticker, ticker_prices in stock_prices.groupby("ticker")
    }


def find_entry_exit(
    ticker_prices: pd.DataFrame,
    event_date: pd.Timestamp,
    hold_days: int = HOLD_DAYS,
) -> tuple[pd.Timestamp, pd.Timestamp, float, float, float] | None:
    """
    Enter next trading day after event and exit after hold_days trading days.

    Returns:
    entry_date, exit_date, entry_price, exit_price, cumulative_abnormal_return
    """
    after_event = ticker_prices[ticker_prices["date"] > event_date].copy()

    if len(after_event) <= hold_days:
        return None

    entry_row = after_event.iloc[0]
    exit_row = after_event.iloc[hold_days]

    entry_date = pd.Timestamp(entry_row["date"])
    exit_date = pd.Timestamp(exit_row["date"])
    entry_price = float(entry_row["adj_close"])
    exit_price = float(exit_row["adj_close"])

    holding_window = after_event.iloc[0:hold_days].copy()
    cumulative_abnormal_return = (1 + holding_window["abnormal_return"]).prod() - 1

    if entry_price <= 0 or exit_price <= 0:
        return None

    return entry_date, exit_date, entry_price, exit_price, float(cumulative_abnormal_return)


def build_candidate_trades(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    hold_days: int = HOLD_DAYS,
    transaction_cost_bps_per_side: float = TRANSACTION_COST_BPS_PER_SIDE,
) -> pd.DataFrame:
    """Build candidate trades for negative-event reversal."""
    price_map = get_ticker_price_map(prices)

    trades: list[Trade] = []
    round_trip_cost = 2 * transaction_cost_bps_per_side / 10_000

    trade_id = 1

    for _, event in events.iterrows():
        ticker = event["ticker"]
        event_date = pd.Timestamp(event["date"])

        if ticker not in price_map:
            continue

        ticker_prices = price_map[ticker]
        entry_exit = find_entry_exit(
            ticker_prices=ticker_prices,
            event_date=event_date,
            hold_days=hold_days,
        )

        if entry_exit is None:
            continue

        entry_date, exit_date, entry_price, exit_price, gross_abnormal_return = entry_exit

        gross_stock_return = exit_price / entry_price - 1
        net_abnormal_return = gross_abnormal_return - round_trip_cost

        trades.append(
            Trade(
                trade_id=trade_id,
                ticker=ticker,
                event_date=event_date,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_stock_return=gross_stock_return,
                gross_abnormal_return=gross_abnormal_return,
                net_abnormal_return=net_abnormal_return,
                holding_days=hold_days,
                event_strength=float(event["event_strength"]),
                volume_shock=float(event["volume_shock"]),
                transaction_cost_bps_round_trip=2 * transaction_cost_bps_per_side,
            )
        )

        trade_id += 1

    if not trades:
        return pd.DataFrame()

    return pd.DataFrame([trade.__dict__ for trade in trades])


def apply_concurrency_cap(
    trades: pd.DataFrame,
    max_concurrent_positions: int = MAX_CONCURRENT_POSITIONS,
) -> pd.DataFrame:
    """Accept trades chronologically while enforcing max concurrent positions."""
    if trades.empty:
        return trades

    sorted_trades = trades.sort_values(["entry_date", "ticker"]).reset_index(drop=True)

    accepted_rows = []

    for _, trade in sorted_trades.iterrows():
        entry_date = pd.Timestamp(trade["entry_date"])

        active_count = 0

        for accepted in accepted_rows:
            accepted_entry = pd.Timestamp(accepted["entry_date"])
            accepted_exit = pd.Timestamp(accepted["exit_date"])

            if accepted_entry <= entry_date < accepted_exit:
                active_count += 1

        if active_count < max_concurrent_positions:
            accepted_rows.append(trade.to_dict())

    accepted_trades = pd.DataFrame(accepted_rows)

    if accepted_trades.empty:
        return accepted_trades

    accepted_trades = accepted_trades.reset_index(drop=True)
    accepted_trades["accepted_trade_id"] = np.arange(1, len(accepted_trades) + 1)

    return accepted_trades


def build_daily_abnormal_portfolio_returns(
    prices: pd.DataFrame,
    trades: pd.DataFrame,
    max_concurrent_positions: int = MAX_CONCURRENT_POSITIONS,
    transaction_cost_bps_per_side: float = TRANSACTION_COST_BPS_PER_SIDE,
) -> pd.DataFrame:
    """Build equal-weight daily abnormal portfolio returns."""
    stock_prices = prices[prices["ticker"].isin(STOCK_TICKERS)].copy()

    all_dates = stock_prices["date"].drop_duplicates().sort_values().reset_index(drop=True)

    abnormal_returns_wide = (
        stock_prices.pivot(index="date", columns="ticker", values="abnormal_return")
        .sort_index()
    )

    rows = []

    for date in all_dates:
        active = trades[
            (trades["entry_date"] <= date)
            & (date < trades["exit_date"])
        ]

        if active.empty:
            rows.append(
                {
                    "date": date,
                    "portfolio_abnormal_return": 0.0,
                    "active_positions": 0,
                    "gross_exposure": 0.0,
                }
            )
            continue

        active = active.head(max_concurrent_positions)
        weight = 1.0 / max_concurrent_positions

        day_return = 0.0
        valid_positions = 0

        for _, trade in active.iterrows():
            ticker = trade["ticker"]

            try:
                ticker_return = abnormal_returns_wide.loc[date, ticker]
            except KeyError:
                ticker_return = np.nan

            if pd.isna(ticker_return):
                continue

            day_return += weight * float(ticker_return)
            valid_positions += 1

        rows.append(
            {
                "date": date,
                "portfolio_abnormal_return": day_return,
                "active_positions": valid_positions,
                "gross_exposure": valid_positions * weight,
            }
        )

    portfolio = pd.DataFrame(rows)
    portfolio = portfolio.sort_values("date").reset_index(drop=True)

    cost_per_side = transaction_cost_bps_per_side / 10_000
    trade_weight = 1.0 / max_concurrent_positions

    portfolio["transaction_cost"] = 0.0

    for _, trade in trades.iterrows():
        entry_date = pd.Timestamp(trade["entry_date"])
        exit_date = pd.Timestamp(trade["exit_date"])

        portfolio.loc[portfolio["date"] == entry_date, "transaction_cost"] += (
            trade_weight * cost_per_side
        )
        portfolio.loc[portfolio["date"] == exit_date, "transaction_cost"] += (
            trade_weight * cost_per_side
        )

    portfolio["net_portfolio_abnormal_return"] = (
        portfolio["portfolio_abnormal_return"] - portfolio["transaction_cost"]
    )

    portfolio["abnormal_equity_curve"] = (
        1 + portfolio["net_portfolio_abnormal_return"]
    ).cumprod()

    return portfolio


def max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate max drawdown from equity curve."""
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    return float(drawdown.min())


def annualized_sharpe(daily_returns: pd.Series) -> float:
    """Calculate annualized Sharpe ratio."""
    clean = daily_returns.dropna()

    if clean.std(ddof=1) == 0:
        return np.nan

    return float(np.sqrt(252) * clean.mean() / clean.std(ddof=1))


def summarize_threshold_run(
    threshold_config: dict[str, float],
    detected_events: pd.DataFrame,
    trades: pd.DataFrame,
    portfolio: pd.DataFrame,
) -> dict[str, float | int | str]:
    """Summarize one threshold sensitivity run."""
    daily_returns = portfolio["net_portfolio_abnormal_return"]
    equity_curve = portfolio["abnormal_equity_curve"]

    active_days = (portfolio["active_positions"] > 0).sum()
    total_days = len(portfolio)

    return {
        "strategy": STRATEGY_NAME,
        "hold_days": HOLD_DAYS,
        "event_strength_threshold": threshold_config["event_strength_threshold"],
        "volume_shock_threshold": threshold_config["volume_shock_threshold"],
        "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
        "transaction_cost_bps_per_side": TRANSACTION_COST_BPS_PER_SIDE,
        "n_detected_events": len(detected_events),
        "n_trades": len(trades),
        "trade_win_rate": (trades["net_abnormal_return"] > 0).mean(),
        "avg_trade_net_abnormal_return": trades["net_abnormal_return"].mean(),
        "median_trade_net_abnormal_return": trades["net_abnormal_return"].median(),
        "best_trade_abnormal": trades["net_abnormal_return"].max(),
        "worst_trade_abnormal": trades["net_abnormal_return"].min(),
        "total_abnormal_return": float(equity_curve.iloc[-1] - 1),
        "annualized_abnormal_sharpe": annualized_sharpe(daily_returns),
        "max_abnormal_drawdown": max_drawdown(equity_curve),
        "active_days": int(active_days),
        "total_days": int(total_days),
        "active_day_ratio": active_days / total_days,
        "avg_active_positions": portfolio["active_positions"].mean(),
        "avg_gross_exposure": portfolio["gross_exposure"].mean(),
    }


def run_threshold_sensitivity() -> None:
    """Run threshold sensitivity for negative-event reversal."""
    prices = load_prices()
    features = add_event_features(prices)

    rows = []

    for config in THRESHOLD_GRID:
        strength_threshold = config["event_strength_threshold"]
        volume_threshold = config["volume_shock_threshold"]

        print(
            "Running threshold sensitivity: "
            f"event_strength <= -{strength_threshold}, "
            f"volume_shock >= {volume_threshold}..."
        )

        detected_events = detect_negative_events(
            features=features,
            event_strength_threshold=strength_threshold,
            volume_shock_threshold=volume_threshold,
        )

        trades = build_candidate_trades(
            prices=prices,
            events=detected_events,
            hold_days=HOLD_DAYS,
        )

        if trades.empty:
            rows.append(
                {
                    "strategy": STRATEGY_NAME,
                    "hold_days": HOLD_DAYS,
                    "event_strength_threshold": strength_threshold,
                    "volume_shock_threshold": volume_threshold,
                    "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
                    "transaction_cost_bps_per_side": TRANSACTION_COST_BPS_PER_SIDE,
                    "n_detected_events": len(detected_events),
                    "n_trades": 0,
                    "trade_win_rate": np.nan,
                    "avg_trade_net_abnormal_return": np.nan,
                    "median_trade_net_abnormal_return": np.nan,
                    "best_trade_abnormal": np.nan,
                    "worst_trade_abnormal": np.nan,
                    "total_abnormal_return": np.nan,
                    "annualized_abnormal_sharpe": np.nan,
                    "max_abnormal_drawdown": np.nan,
                    "active_days": 0,
                    "total_days": 0,
                    "active_day_ratio": np.nan,
                    "avg_active_positions": np.nan,
                    "avg_gross_exposure": np.nan,
                }
            )
            continue

        trades = apply_concurrency_cap(trades)

        portfolio = build_daily_abnormal_portfolio_returns(
            prices=prices,
            trades=trades,
        )

        rows.append(
            summarize_threshold_run(
                threshold_config=config,
                detected_events=detected_events,
                trades=trades,
                portfolio=portfolio,
            )
        )

    summary = pd.DataFrame(rows)

    THRESHOLD_SENSITIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(THRESHOLD_SENSITIVITY_PATH, index=False)

    print()
    print(f"Saved threshold sensitivity to: {THRESHOLD_SENSITIVITY_PATH}")

    print()
    print("Threshold sensitivity summary")
    print("-----------------------------")
    print(
        summary[
            [
                "event_strength_threshold",
                "volume_shock_threshold",
                "n_detected_events",
                "n_trades",
                "trade_win_rate",
                "avg_trade_net_abnormal_return",
                "median_trade_net_abnormal_return",
                "total_abnormal_return",
                "annualized_abnormal_sharpe",
                "max_abnormal_drawdown",
                "active_day_ratio",
                "avg_gross_exposure",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    run_threshold_sensitivity()