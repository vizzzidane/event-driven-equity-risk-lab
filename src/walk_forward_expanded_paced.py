from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from src.universe import ACTIVE_STOCK_TICKERS, MARKET_TICKER
except ModuleNotFoundError:
    from universe import ACTIVE_STOCK_TICKERS, MARKET_TICKER


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")
EVENT_PANEL_PATH = Path("results/event_panel.csv")

WALK_FORWARD_SUMMARY_PATH = Path("results/walk_forward_expanded_paced_summary.csv")
WALK_FORWARD_TRADES_PATH = Path("results/walk_forward_expanded_paced_trades.csv")
WALK_FORWARD_PORTFOLIO_PATH = Path("results/walk_forward_expanded_paced_portfolio_returns.csv")

STRATEGY_NAME = "negative_event_reversal_30d_expanded_global_pacing"

EVENT_STRENGTH_THRESHOLD = -2.0
VOLUME_SHOCK_THRESHOLD = 1.2
HOLD_DAYS = 30
MAX_CONCURRENT_POSITIONS = 5
TRANSACTION_COST_BPS_PER_SIDE = 5.0
MIN_DAYS_BETWEEN_NEW_TRADES = 10

TEST_YEARS = list(range(2016, 2026))


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

    required = {"date", "ticker", "adj_close", "return"}
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

    prices = prices[prices["ticker"].isin(ACTIVE_STOCK_TICKERS)].copy()

    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def load_events(path: Path = EVENT_PANEL_PATH) -> pd.DataFrame:
    """Load detected event panel."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing event panel: {path}. Run `python src/events.py` first."
        )

    events = pd.read_csv(path, parse_dates=["date"])

    required = {
        "ticker",
        "date",
        "event_direction",
        "event_strength",
        "volume_shock",
    }
    missing = required - set(events.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    events = events[
        (events["ticker"].isin(ACTIVE_STOCK_TICKERS))
        & (events["event_direction"] == "negative")
        & (events["event_strength"] <= EVENT_STRENGTH_THRESHOLD)
        & (events["volume_shock"] >= VOLUME_SHOCK_THRESHOLD)
    ].copy()

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def get_ticker_price_map(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Create ticker -> price map."""
    return {
        ticker: ticker_prices.sort_values("date").reset_index(drop=True)
        for ticker, ticker_prices in prices.groupby("ticker")
    }


def find_entry_exit(
    ticker_prices: pd.DataFrame,
    event_date: pd.Timestamp,
    hold_days: int = HOLD_DAYS,
) -> tuple[pd.Timestamp, pd.Timestamp, float, float, float] | None:
    """
    Enter next trading day after event and exit after hold_days trading days.

    Returns:
    entry_date, exit_date, entry_price, exit_price, cumulative_abnormal_return.
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


def build_candidate_trades_for_year(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    test_year: int,
    trade_id_start: int,
) -> pd.DataFrame:
    """
    Build candidate trades for one test year.

    Fixed rule:
    - negative abnormal price-volume event
    - 30 trading-day hold
    - 5 bps per side cost
    - at least 10 calendar days between new trades globally
    """
    price_map = get_ticker_price_map(prices)

    year_events = events[events["date"].dt.year == test_year].copy()
    year_events = year_events.sort_values(["date", "ticker"]).reset_index(drop=True)

    trades: list[Trade] = []
    round_trip_cost = 2 * TRANSACTION_COST_BPS_PER_SIDE / 10_000

    last_global_event_date: pd.Timestamp | None = None
    trade_id = trade_id_start

    for _, event in year_events.iterrows():
        ticker = event["ticker"]
        event_date = pd.Timestamp(event["date"])

        if ticker not in price_map:
            continue

        if last_global_event_date is not None:
            days_since_last_trade_event = (event_date - last_global_event_date).days

            if days_since_last_trade_event < MIN_DAYS_BETWEEN_NEW_TRADES:
                continue

        ticker_prices = price_map[ticker]
        entry_exit = find_entry_exit(
            ticker_prices=ticker_prices,
            event_date=event_date,
            hold_days=HOLD_DAYS,
        )

        if entry_exit is None:
            continue

        entry_date, exit_date, entry_price, exit_price, gross_abnormal_return = entry_exit

        if entry_date.year != test_year:
            continue

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

        last_global_event_date = event_date
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
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    """Build equal-weight daily abnormal portfolio returns for a date range."""
    all_dates = (
        prices.loc[
            (prices["date"] >= start_date)
            & (prices["date"] <= end_date),
            "date",
        ]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )

    abnormal_returns_wide = (
        prices.pivot(index="date", columns="ticker", values="abnormal_return")
        .sort_index()
    )

    rows = []

    for date in all_dates:
        active = trades[(trades["entry_date"] <= date) & (date < trades["exit_date"])]

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

    if clean.empty or clean.std(ddof=1) == 0:
        return np.nan

    return float(np.sqrt(252) * clean.mean() / clean.std(ddof=1))


def summarize_period(
    label: str,
    trades: pd.DataFrame,
    portfolio: pd.DataFrame,
) -> dict[str, float | int | str]:
    """Summarize one walk-forward period."""
    if trades.empty or portfolio.empty:
        return {
            "test_period": label,
            "n_trades": 0,
            "trade_win_rate": np.nan,
            "avg_trade_net_abnormal_return": np.nan,
            "median_trade_net_abnormal_return": np.nan,
            "period_abnormal_return": np.nan,
            "annualized_abnormal_sharpe": np.nan,
            "max_abnormal_drawdown": np.nan,
            "active_day_ratio": np.nan,
            "avg_gross_exposure": np.nan,
        }

    daily_returns = portfolio["net_portfolio_abnormal_return"]
    equity_curve = portfolio["abnormal_equity_curve"]

    active_days = (portfolio["active_positions"] > 0).sum()
    total_days = len(portfolio)

    return {
        "test_period": label,
        "n_trades": len(trades),
        "trade_win_rate": (trades["net_abnormal_return"] > 0).mean(),
        "avg_trade_net_abnormal_return": trades["net_abnormal_return"].mean(),
        "median_trade_net_abnormal_return": trades["net_abnormal_return"].median(),
        "period_abnormal_return": float(equity_curve.iloc[-1] - 1),
        "annualized_abnormal_sharpe": annualized_sharpe(daily_returns),
        "max_abnormal_drawdown": max_drawdown(equity_curve),
        "active_day_ratio": active_days / total_days,
        "avg_gross_exposure": portfolio["gross_exposure"].mean(),
    }


def run_walk_forward_expanded_paced() -> None:
    """Run expanded-universe fixed-rule walk-forward with global pacing."""
    prices = load_prices()
    events = load_events()

    all_trade_frames = []
    all_portfolio_frames = []
    summary_rows = []

    next_trade_id = 1

    for test_year in TEST_YEARS:
        print(f"Running expanded paced walk-forward test year: {test_year}...")

        candidate_trades = build_candidate_trades_for_year(
            prices=prices,
            events=events,
            test_year=test_year,
            trade_id_start=next_trade_id,
        )

        accepted_trades = apply_concurrency_cap(candidate_trades)

        if not accepted_trades.empty:
            next_trade_id = int(accepted_trades["trade_id"].max()) + 1

            start_date = pd.Timestamp(f"{test_year}-01-01")
            end_date = max(
                pd.Timestamp(f"{test_year}-12-31"),
                pd.to_datetime(accepted_trades["exit_date"]).max(),
            )

            portfolio = build_daily_abnormal_portfolio_returns(
                prices=prices,
                trades=accepted_trades,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            start_date = pd.Timestamp(f"{test_year}-01-01")
            end_date = pd.Timestamp(f"{test_year}-12-31")

            portfolio = build_daily_abnormal_portfolio_returns(
                prices=prices,
                trades=accepted_trades,
                start_date=start_date,
                end_date=end_date,
            )

        accepted_trades["test_year"] = test_year
        portfolio["test_year"] = test_year

        all_trade_frames.append(accepted_trades)
        all_portfolio_frames.append(portfolio)

        summary_rows.append(
            summarize_period(
                label=str(test_year),
                trades=accepted_trades,
                portfolio=portfolio,
            )
        )

    trades = pd.concat(all_trade_frames, ignore_index=True)
    portfolio_by_year = pd.concat(all_portfolio_frames, ignore_index=True)

    full_start = pd.Timestamp(f"{TEST_YEARS[0]}-01-01")
    full_end = pd.to_datetime(trades["exit_date"]).max()

    full_portfolio = build_daily_abnormal_portfolio_returns(
        prices=prices,
        trades=trades,
        start_date=full_start,
        end_date=full_end,
    )

    summary_rows.append(
        summarize_period(
            label=f"FULL_{TEST_YEARS[0]}_{TEST_YEARS[-1]}",
            trades=trades,
            portfolio=full_portfolio,
        )
    )

    summary = pd.DataFrame(summary_rows)

    WALK_FORWARD_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(WALK_FORWARD_SUMMARY_PATH, index=False)
    trades.to_csv(WALK_FORWARD_TRADES_PATH, index=False)
    full_portfolio.to_csv(WALK_FORWARD_PORTFOLIO_PATH, index=False)

    print()
    print(f"Saved expanded paced walk-forward summary to: {WALK_FORWARD_SUMMARY_PATH}")
    print(f"Saved expanded paced walk-forward trades to: {WALK_FORWARD_TRADES_PATH}")
    print(f"Saved expanded paced walk-forward portfolio returns to: {WALK_FORWARD_PORTFOLIO_PATH}")

    print()
    print("Expanded paced walk-forward yearly summary")
    print("------------------------------------------")
    print(
        summary[
            [
                "test_period",
                "n_trades",
                "trade_win_rate",
                "avg_trade_net_abnormal_return",
                "median_trade_net_abnormal_return",
                "period_abnormal_return",
                "annualized_abnormal_sharpe",
                "max_abnormal_drawdown",
                "active_day_ratio",
                "avg_gross_exposure",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    run_walk_forward_expanded_paced()