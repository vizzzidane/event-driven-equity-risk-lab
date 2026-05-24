from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")

WALK_FORWARD_SUMMARY_PATH = Path("results/walk_forward_summary.csv")
WALK_FORWARD_TRADES_PATH = Path("results/walk_forward_trades.csv")
WALK_FORWARD_PORTFOLIO_PATH = Path("results/walk_forward_portfolio_returns.csv")

STRATEGY_NAME = "negative_event_reversal_30d_fixed_walk_forward"

EVENT_STRENGTH_THRESHOLD = 2.0
VOLUME_SHOCK_THRESHOLD = 1.2
MIN_AVG_DOLLAR_VOLUME = 50_000_000

HOLD_DAYS = 30
MAX_CONCURRENT_POSITIONS = 5
TRANSACTION_COST_BPS_PER_SIDE = 5.0

TEST_YEARS = list(range(2016, 2026))

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

    prices["year"] = prices["date"].dt.year

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def add_event_features(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Build event features without lookahead.

    Rolling volatility and average volume are shifted by one day,
    so the event-day return/volume is not used in the pre-event baseline.
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


def detect_negative_events(features: pd.DataFrame) -> pd.DataFrame:
    """
    Detect negative abnormal price-volume events using fixed parameters.
    """
    events = features[
        features["event_strength"].le(-EVENT_STRENGTH_THRESHOLD)
        & features["volume_shock"].ge(VOLUME_SHOCK_THRESHOLD)
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
    hold_days: int = HOLD_DAYS,
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


def build_all_trades(
    prices: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Build all candidate trades across all test years."""
    price_map = get_ticker_price_map(prices)
    trades: list[Trade] = []

    round_trip_cost = 2 * TRANSACTION_COST_BPS_PER_SIDE / 10_000

    trade_id = 1

    for _, event in events.iterrows():
        ticker = event["ticker"]
        event_date = pd.Timestamp(event["date"])
        test_year = int(event_date.year)

        if test_year not in TEST_YEARS:
            continue

        if ticker not in price_map:
            continue

        entry_exit = find_entry_exit(
            ticker_prices=price_map[ticker],
            event_date=event_date,
            hold_days=HOLD_DAYS,
        )

        if entry_exit is None:
            continue

        entry_date, exit_date, entry_price, exit_price, gross_abnormal_return = entry_exit

        gross_stock_return = exit_price / entry_price - 1
        net_abnormal_return = gross_abnormal_return - round_trip_cost

        trades.append(
            Trade(
                trade_id=trade_id,
                test_year=test_year,
                ticker=ticker,
                event_date=event_date,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_stock_return=gross_stock_return,
                gross_abnormal_return=gross_abnormal_return,
                net_abnormal_return=net_abnormal_return,
                holding_days=HOLD_DAYS,
                event_strength=float(event["event_strength"]),
                volume_shock=float(event["volume_shock"]),
                transaction_cost_bps_round_trip=2 * TRANSACTION_COST_BPS_PER_SIDE,
            )
        )

        trade_id += 1

    if not trades:
        raise RuntimeError("No walk-forward trades generated.")

    return pd.DataFrame([trade.__dict__ for trade in trades])


def apply_concurrency_cap_by_year(
    trades: pd.DataFrame,
    max_concurrent_positions: int = MAX_CONCURRENT_POSITIONS,
) -> pd.DataFrame:
    """
    Apply concurrency cap independently within each test year.

    This keeps yearly test slices comparable and prevents active trades in one
    test year from blocking trades in the next.
    """
    accepted_all = []

    for test_year, year_trades in trades.groupby("test_year"):
        year_trades = year_trades.sort_values(["entry_date", "ticker"]).reset_index(drop=True)

        accepted_rows = []

        for _, trade in year_trades.iterrows():
            entry_date = pd.Timestamp(trade["entry_date"])

            active_count = 0

            for accepted in accepted_rows:
                accepted_entry = pd.Timestamp(accepted["entry_date"])
                accepted_exit = pd.Timestamp(accepted["exit_date"])

                if accepted_entry <= entry_date < accepted_exit:
                    active_count += 1

            if active_count < max_concurrent_positions:
                accepted_rows.append(trade.to_dict())

        accepted_all.extend(accepted_rows)

    accepted = pd.DataFrame(accepted_all)

    if accepted.empty:
        raise RuntimeError("No walk-forward trades survived concurrency cap.")

    accepted = accepted.sort_values(["entry_date", "ticker"]).reset_index(drop=True)
    accepted["accepted_trade_id"] = np.arange(1, len(accepted) + 1)

    return accepted


def build_daily_abnormal_portfolio_returns(
    prices: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build daily abnormal portfolio returns.

    For walk-forward reporting, returns are calculated across the full test-year
    period from 2016 to 2025.
    """
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
    """Summarize one test year."""
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
        "event_strength_threshold": EVENT_STRENGTH_THRESHOLD,
        "volume_shock_threshold": VOLUME_SHOCK_THRESHOLD,
        "hold_days": HOLD_DAYS,
        "transaction_cost_bps_per_side": TRANSACTION_COST_BPS_PER_SIDE,
        "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
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
    """Summarize full walk-forward test period."""
    daily_returns = portfolio["net_portfolio_abnormal_return"]
    equity = portfolio["abnormal_equity_curve"]

    active_days = (portfolio["active_positions"] > 0).sum()
    total_days = len(portfolio)

    return {
        "strategy": STRATEGY_NAME,
        "test_year": "FULL_2016_2025",
        "event_strength_threshold": EVENT_STRENGTH_THRESHOLD,
        "volume_shock_threshold": VOLUME_SHOCK_THRESHOLD,
        "hold_days": HOLD_DAYS,
        "transaction_cost_bps_per_side": TRANSACTION_COST_BPS_PER_SIDE,
        "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
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


def run_walk_forward() -> None:
    """Run fixed-rule walk-forward yearly validation."""
    prices = load_prices()
    features = add_event_features(prices)
    events = detect_negative_events(features)

    candidate_trades = build_all_trades(
        prices=prices,
        events=events,
    )
    trades = apply_concurrency_cap_by_year(candidate_trades)

    portfolio = build_daily_abnormal_portfolio_returns(
        prices=prices,
        trades=trades,
    )

    rows = [
        summarize_year(
            test_year=year,
            trades=trades,
            portfolio=portfolio,
        )
        for year in TEST_YEARS
    ]

    rows.append(summarize_full_period(trades, portfolio))

    summary = pd.DataFrame(rows)

    WALK_FORWARD_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(WALK_FORWARD_SUMMARY_PATH, index=False)
    trades.to_csv(WALK_FORWARD_TRADES_PATH, index=False)
    portfolio.to_csv(WALK_FORWARD_PORTFOLIO_PATH, index=False)

    print(f"Saved walk-forward summary to: {WALK_FORWARD_SUMMARY_PATH}")
    print(f"Saved walk-forward trades to: {WALK_FORWARD_TRADES_PATH}")
    print(f"Saved walk-forward portfolio returns to: {WALK_FORWARD_PORTFOLIO_PATH}")

    print()
    print("Walk-forward yearly summary")
    print("---------------------------")
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
    run_walk_forward()