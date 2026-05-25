from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")

WF_OPT_SUMMARY_PATH = Path("results/walk_forward_optimized_summary.csv")
WF_OPT_PARAM_SELECTION_PATH = Path("results/walk_forward_optimized_param_selection.csv")
WF_OPT_TRADES_PATH = Path("results/walk_forward_optimized_trades.csv")
WF_OPT_PORTFOLIO_PATH = Path("results/walk_forward_optimized_portfolio_returns.csv")

STRATEGY_NAME = "negative_event_reversal_optimized_walk_forward"

EVENT_STRENGTH_GRID = [1.5, 2.0, 2.5, 3.0]
VOLUME_SHOCK_GRID = [1.0, 1.2, 1.5, 2.0]
HOLD_DAYS_GRID = [10, 20, 30]

MIN_AVG_DOLLAR_VOLUME = 50_000_000
MAX_CONCURRENT_POSITIONS = 5
TRANSACTION_COST_BPS_PER_SIDE = 5.0

TRAIN_START_YEAR = 2015
TEST_YEARS = list(range(2018, 2026))

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
    test_year: int
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
    event_strength_threshold: float
    volume_shock_threshold: float
    event_strength: float
    volume_shock: float
    transaction_cost_bps_round_trip: float

def split_train_test_year(
    df: pd.DataFrame,
    test_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = df[df["date"].dt.year < test_year].copy()

    test_df = df[df["date"].dt.year == test_year].copy()

    return train_df, test_df

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

    prices["year"] = prices["date"].dt.year

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_event_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Build event features without lookahead.

    Rolling estimates are shifted by 1 day so the event day itself is not
    included in the baseline.
    """
    stock_rows = prices[prices["ticker"].isin(STOCK_TICKERS)].copy()
    stock_rows = stock_rows.sort_values(["ticker", "date"]).reset_index(drop=True)

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

    stock_rows["event_year"] = stock_rows["date"].dt.year

    return stock_rows.sort_values(["ticker", "date"]).reset_index(drop=True)


def detect_negative_events(
    features: pd.DataFrame,
    event_strength_threshold: float,
    volume_shock_threshold: float,
) -> pd.DataFrame:
    """Detect negative abnormal price-volume events."""
    events = features[
        features["event_strength"].le(-event_strength_threshold)
        & features["volume_shock"].ge(volume_shock_threshold)
        & features["avg_20d_dollar_volume"].ge(MIN_AVG_DOLLAR_VOLUME)
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
    hold_days: int,
) -> tuple[pd.Timestamp, pd.Timestamp, float, float, float] | None:
    """
    Enter next trading day after event and exit after hold_days trading days.
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


def build_trades_for_config(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    hold_days: int,
    event_strength_threshold: float,
    volume_shock_threshold: float,
    allowed_years: set[int],
    test_year_label: int,
) -> pd.DataFrame:
    """Build trades for a parameter setting and allowed event years."""
    price_map = get_ticker_price_map(prices)

    events = events[events["event_year"].isin(allowed_years)].copy()

    trades: list[Trade] = []
    round_trip_cost = 2 * TRANSACTION_COST_BPS_PER_SIDE / 10_000

    trade_id = 1

    for _, event in events.iterrows():
        ticker = event["ticker"]
        event_date = pd.Timestamp(event["date"])

        if ticker not in price_map:
            continue

        entry_exit = find_entry_exit(
            ticker_prices=price_map[ticker],
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
                test_year=test_year_label,
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
                event_strength_threshold=event_strength_threshold,
                volume_shock_threshold=volume_shock_threshold,
                event_strength=float(event["event_strength"]),
                volume_shock=float(event["volume_shock"]),
                transaction_cost_bps_round_trip=2 * TRANSACTION_COST_BPS_PER_SIDE,
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

    accepted = pd.DataFrame(accepted_rows)

    if accepted.empty:
        return accepted

    accepted = accepted.reset_index(drop=True)
    accepted["accepted_trade_id"] = np.arange(1, len(accepted) + 1)

    return accepted


def annualized_sharpe_from_trades(trades: pd.DataFrame) -> float:
    """
    Approximate selection objective using trade returns.

    This is deliberately simple for parameter selection:
    mean trade return / std trade return * sqrt(number of trades per year proxy).
    """
    if trades.empty:
        return np.nan

    returns = trades["net_abnormal_return"].dropna()

    if len(returns) < 5 or returns.std(ddof=1) == 0:
        return np.nan

    return float(returns.mean() / returns.std(ddof=1) * np.sqrt(len(returns)))


def score_training_config(trades: pd.DataFrame) -> dict[str, float | int]:
    """Score training performance for one parameter config."""
    if trades.empty:
        return {
            "train_n_trades": 0,
            "train_avg_trade_return": np.nan,
            "train_median_trade_return": np.nan,
            "train_win_rate": np.nan,
            "train_trade_score": np.nan,
        }

    returns = trades["net_abnormal_return"]

    return {
        "train_n_trades": len(trades),
        "train_avg_trade_return": returns.mean(),
        "train_median_trade_return": returns.median(),
        "train_win_rate": (returns > 0).mean(),
        "train_trade_score": annualized_sharpe_from_trades(trades),
    }


def choose_best_params_for_year(
    prices: pd.DataFrame,
    features: pd.DataFrame,
    test_year: int,
) -> dict[str, float | int]:
    """
    Choose parameters using only prior years.

    Objective:
    - maximize train_trade_score
    - require at least 30 training trades
    """
    train_years = set(range(TRAIN_START_YEAR, test_year))
    rows = []

    for event_strength_threshold in EVENT_STRENGTH_GRID:
        for volume_shock_threshold in VOLUME_SHOCK_GRID:
            events = detect_negative_events(
                features=features,
                event_strength_threshold=event_strength_threshold,
                volume_shock_threshold=volume_shock_threshold,
            )

            for hold_days in HOLD_DAYS_GRID:
                trades = build_trades_for_config(
                    prices=prices,
                    events=events,
                    hold_days=hold_days,
                    event_strength_threshold=event_strength_threshold,
                    volume_shock_threshold=volume_shock_threshold,
                    allowed_years=train_years,
                    test_year_label=test_year,
                )

                trades = apply_concurrency_cap(trades)

                score = score_training_config(trades)

                rows.append(
                    {
                        "test_year": test_year,
                        "event_strength_threshold": event_strength_threshold,
                        "volume_shock_threshold": volume_shock_threshold,
                        "hold_days": hold_days,
                        **score,
                    }
                )

    grid = pd.DataFrame(rows)

    valid = grid[
        grid["train_n_trades"].ge(30)
        & grid["train_trade_score"].notna()
    ].copy()

    if valid.empty:
        # conservative fallback
        return {
            "test_year": test_year,
            "event_strength_threshold": 2.0,
            "volume_shock_threshold": 1.2,
            "hold_days": 30,
            "train_n_trades": 0,
            "train_avg_trade_return": np.nan,
            "train_median_trade_return": np.nan,
            "train_win_rate": np.nan,
            "train_trade_score": np.nan,
            "selection_reason": "fallback_default",
        }

    best = valid.sort_values(
        ["train_trade_score", "train_avg_trade_return", "train_n_trades"],
        ascending=[False, False, False],
    ).iloc[0]

    return {
        "test_year": int(best["test_year"]),
        "event_strength_threshold": float(best["event_strength_threshold"]),
        "volume_shock_threshold": float(best["volume_shock_threshold"]),
        "hold_days": int(best["hold_days"]),
        "train_n_trades": int(best["train_n_trades"]),
        "train_avg_trade_return": float(best["train_avg_trade_return"]),
        "train_median_trade_return": float(best["train_median_trade_return"]),
        "train_win_rate": float(best["train_win_rate"]),
        "train_trade_score": float(best["train_trade_score"]),
        "selection_reason": "max_train_trade_score",
    }


def build_daily_abnormal_portfolio_returns(
    prices: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    """Build daily abnormal portfolio returns for optimized WF trades."""
    stock_prices = prices[
        prices["ticker"].isin(STOCK_TICKERS)
        & prices["year"].between(min(TEST_YEARS), max(TEST_YEARS))
    ].copy()

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
                    "test_year": int(pd.Timestamp(date).year),
                    "portfolio_abnormal_return": 0.0,
                    "active_positions": 0,
                    "gross_exposure": 0.0,
                }
            )
            continue

        active = active.head(MAX_CONCURRENT_POSITIONS)
        weight = 1.0 / MAX_CONCURRENT_POSITIONS

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
                "test_year": int(pd.Timestamp(date).year),
                "portfolio_abnormal_return": day_return,
                "active_positions": valid_positions,
                "gross_exposure": valid_positions * weight,
            }
        )

    portfolio = pd.DataFrame(rows)
    portfolio = portfolio.sort_values("date").reset_index(drop=True)

    cost_per_side = TRANSACTION_COST_BPS_PER_SIDE / 10_000
    trade_weight = 1.0 / MAX_CONCURRENT_POSITIONS

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


def summarize_year(
    test_year: int,
    trades: pd.DataFrame,
    portfolio: pd.DataFrame,
) -> dict[str, float | int | str]:
    """Summarize one optimized test year."""
    year_trades = trades[trades["test_year"] == test_year].copy()
    year_portfolio = portfolio[portfolio["test_year"] == test_year].copy()

    if year_portfolio.empty:
        return {
            "strategy": STRATEGY_NAME,
            "test_year": test_year,
            "n_trades": 0,
            "trade_win_rate": np.nan,
            "avg_trade_net_abnormal_return": np.nan,
            "median_trade_net_abnormal_return": np.nan,
            "year_abnormal_return": np.nan,
            "annualized_abnormal_sharpe": np.nan,
            "max_abnormal_drawdown": np.nan,
            "active_day_ratio": np.nan,
            "avg_gross_exposure": np.nan,
        }

    daily_returns = year_portfolio["net_portfolio_abnormal_return"]
    year_equity = (1 + daily_returns).cumprod()

    active_days = (year_portfolio["active_positions"] > 0).sum()
    total_days = len(year_portfolio)

    return {
        "strategy": STRATEGY_NAME,
        "test_year": test_year,
        "n_trades": len(year_trades),
        "trade_win_rate": (
            (year_trades["net_abnormal_return"] > 0).mean()
            if len(year_trades)
            else np.nan
        ),
        "avg_trade_net_abnormal_return": (
            year_trades["net_abnormal_return"].mean()
            if len(year_trades)
            else np.nan
        ),
        "median_trade_net_abnormal_return": (
            year_trades["net_abnormal_return"].median()
            if len(year_trades)
            else np.nan
        ),
        "year_abnormal_return": float(year_equity.iloc[-1] - 1),
        "annualized_abnormal_sharpe": annualized_sharpe(daily_returns),
        "max_abnormal_drawdown": max_drawdown(year_equity),
        "active_day_ratio": active_days / total_days,
        "avg_gross_exposure": year_portfolio["gross_exposure"].mean(),
    }


def summarize_full_period(
    trades: pd.DataFrame,
    portfolio: pd.DataFrame,
) -> dict[str, float | int | str]:
    """Summarize full optimized walk-forward period."""
    daily_returns = portfolio["net_portfolio_abnormal_return"]
    equity = portfolio["abnormal_equity_curve"]

    active_days = (portfolio["active_positions"] > 0).sum()
    total_days = len(portfolio)

    return {
        "strategy": STRATEGY_NAME,
        "test_year": f"FULL_{min(TEST_YEARS)}_{max(TEST_YEARS)}",
        "n_trades": len(trades),
        "trade_win_rate": (trades["net_abnormal_return"] > 0).mean(),
        "avg_trade_net_abnormal_return": trades["net_abnormal_return"].mean(),
        "median_trade_net_abnormal_return": trades["net_abnormal_return"].median(),
        "year_abnormal_return": float(equity.iloc[-1] - 1),
        "annualized_abnormal_sharpe": annualized_sharpe(daily_returns),
        "max_abnormal_drawdown": max_drawdown(equity),
        "active_day_ratio": active_days / total_days,
        "avg_gross_exposure": portfolio["gross_exposure"].mean(),
    }


def run_optimized_walk_forward() -> None:
    """Run train-selected optimized walk-forward validation."""
    prices = load_prices()
    features = add_event_features(prices)

    param_rows = []
    test_trades = []

    for test_year in TEST_YEARS:
        print(f"Selecting parameters using data before {test_year}, testing {test_year}...")

        selected = choose_best_params_for_year(
            prices=prices,
            features=features,
            test_year=test_year,
        )

        param_rows.append(selected)

        events = detect_negative_events(
            features=features,
            event_strength_threshold=selected["event_strength_threshold"],
            volume_shock_threshold=selected["volume_shock_threshold"],
        )

        trades = build_trades_for_config(
            prices=prices,
            events=events,
            hold_days=int(selected["hold_days"]),
            event_strength_threshold=float(selected["event_strength_threshold"]),
            volume_shock_threshold=float(selected["volume_shock_threshold"]),
            allowed_years={test_year},
            test_year_label=test_year,
        )

        trades = apply_concurrency_cap(trades)

        if not trades.empty:
            test_trades.append(trades)

    if not test_trades:
        raise RuntimeError("No optimized walk-forward test trades generated.")

    all_trades = pd.concat(test_trades, ignore_index=True)
    all_trades = all_trades.sort_values(["entry_date", "ticker"]).reset_index(drop=True)
    all_trades["optimized_trade_id"] = np.arange(1, len(all_trades) + 1)

    portfolio = build_daily_abnormal_portfolio_returns(
        prices=prices,
        trades=all_trades,
    )

    rows = [
        summarize_year(
            test_year=year,
            trades=all_trades,
            portfolio=portfolio,
        )
        for year in TEST_YEARS
    ]
    rows.append(summarize_full_period(all_trades, portfolio))

    summary = pd.DataFrame(rows)
    param_selection = pd.DataFrame(param_rows)

    WF_OPT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(WF_OPT_SUMMARY_PATH, index=False)
    param_selection.to_csv(WF_OPT_PARAM_SELECTION_PATH, index=False)
    all_trades.to_csv(WF_OPT_TRADES_PATH, index=False)
    portfolio.to_csv(WF_OPT_PORTFOLIO_PATH, index=False)

    print()
    print(f"Saved optimized walk-forward summary to: {WF_OPT_SUMMARY_PATH}")
    print(f"Saved parameter selection to: {WF_OPT_PARAM_SELECTION_PATH}")
    print(f"Saved optimized walk-forward trades to: {WF_OPT_TRADES_PATH}")
    print(f"Saved optimized walk-forward portfolio returns to: {WF_OPT_PORTFOLIO_PATH}")

    print()
    print("Optimized parameter selection")
    print("-----------------------------")
    print(
        param_selection[
            [
                "test_year",
                "event_strength_threshold",
                "volume_shock_threshold",
                "hold_days",
                "train_n_trades",
                "train_avg_trade_return",
                "train_win_rate",
                "train_trade_score",
                "selection_reason",
            ]
        ].to_string(index=False)
    )

    print()
    print("Optimized walk-forward yearly summary")
    print("-------------------------------------")
    print(
        summary[
            [
                "test_year",
                "n_trades",
                "trade_win_rate",
                "avg_trade_net_abnormal_return",
                "median_trade_net_abnormal_return",
                "year_abnormal_return",
                "annualized_abnormal_sharpe",
                "max_abnormal_drawdown",
                "active_day_ratio",
                "avg_gross_exposure",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    run_optimized_walk_forward()