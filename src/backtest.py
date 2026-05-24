from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")
EVENT_PANEL_PATH = Path("results/event_panel.csv")

TRADE_LEDGER_PATH = Path("results/trade_ledger.csv")
PORTFOLIO_RETURNS_PATH = Path("results/portfolio_returns.csv")
BACKTEST_SUMMARY_PATH = Path("results/backtest_summary.csv")

STRATEGY_NAME = "negative_event_reversal_20d"

HOLD_DAYS = 20
MAX_CONCURRENT_POSITIONS = 5
TRANSACTION_COST_BPS_PER_SIDE = 5.0
INITIAL_CAPITAL = 1.0

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


@dataclass(frozen=True)
class Trade:
    trade_id: int
    ticker: str
    event_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    holding_days: int
    transaction_cost_bps_round_trip: float


def load_prices(path: Path = PROCESSED_DATA_PATH) -> pd.DataFrame:
    """Load processed price data."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing processed data file: {path}. Run `python src/data.py` first."
        )

    prices = pd.read_csv(path, parse_dates=["date"])

    required = {"date", "ticker", "adj_close", "return"}
    missing = required - set(prices.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    prices = prices[prices["ticker"].isin(STOCK_TICKERS)].copy()
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)

    return prices


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

    events = events.sort_values(["date", "ticker"]).reset_index(drop=True)

    return events


def get_ticker_price_map(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Create ticker -> daily price DataFrame map."""
    price_map = {}

    for ticker, ticker_prices in prices.groupby("ticker"):
        ticker_prices = ticker_prices.sort_values("date").reset_index(drop=True)
        price_map[ticker] = ticker_prices

    return price_map


def find_entry_exit(
    ticker_prices: pd.DataFrame,
    event_date: pd.Timestamp,
    hold_days: int = HOLD_DAYS,
) -> tuple[pd.Timestamp, pd.Timestamp, float, float] | None:
    """
    Enter on the next available trading day after event_date.
    Exit after hold_days trading days from entry.
    """
    after_event = ticker_prices[ticker_prices["date"] > event_date]

    if len(after_event) <= hold_days:
        return None

    entry_row = after_event.iloc[0]
    exit_row = after_event.iloc[hold_days]

    entry_date = pd.Timestamp(entry_row["date"])
    exit_date = pd.Timestamp(exit_row["date"])
    entry_price = float(entry_row["adj_close"])
    exit_price = float(exit_row["adj_close"])

    if entry_price <= 0 or exit_price <= 0:
        return None

    return entry_date, exit_date, entry_price, exit_price


def build_candidate_trades(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    hold_days: int = HOLD_DAYS,
    transaction_cost_bps_per_side: float = TRANSACTION_COST_BPS_PER_SIDE,
) -> pd.DataFrame:
    """
    Build candidate trades for the negative-event reversal strategy.

    Rule:
    - If event_direction == negative, go long next trading day.
    - Exit after hold_days trading days.
    """
    price_map = get_ticker_price_map(prices)

    negative_events = events[
        (events["event_direction"] == "negative")
        & (events["ticker"].isin(price_map.keys()))
    ].copy()

    trades: list[Trade] = []
    round_trip_cost = 2 * transaction_cost_bps_per_side / 10_000

    trade_id = 1

    for _, event in negative_events.iterrows():
        ticker = event["ticker"]
        event_date = pd.Timestamp(event["date"])

        ticker_prices = price_map[ticker]
        entry_exit = find_entry_exit(ticker_prices, event_date, hold_days)

        if entry_exit is None:
            continue

        entry_date, exit_date, entry_price, exit_price = entry_exit

        gross_return = exit_price / entry_price - 1
        net_return = gross_return - round_trip_cost

        trades.append(
            Trade(
                trade_id=trade_id,
                ticker=ticker,
                event_date=event_date,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_return=gross_return,
                net_return=net_return,
                holding_days=hold_days,
                transaction_cost_bps_round_trip=2 * transaction_cost_bps_per_side,
            )
        )

        trade_id += 1

    if not trades:
        raise RuntimeError("No candidate trades were generated.")

    return pd.DataFrame([trade.__dict__ for trade in trades])


def apply_concurrency_cap(
    trades: pd.DataFrame,
    max_concurrent_positions: int = MAX_CONCURRENT_POSITIONS,
) -> pd.DataFrame:
    """
    Apply a simple concurrency cap.

    Trades are processed chronologically.
    A new trade is accepted only if fewer than max_concurrent_positions
    accepted trades are active on its entry date.
    """
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
        raise RuntimeError("No trades survived the concurrency cap.")

    accepted_trades = accepted_trades.reset_index(drop=True)
    accepted_trades["accepted_trade_id"] = np.arange(1, len(accepted_trades) + 1)

    return accepted_trades


def build_daily_portfolio_returns(
    prices: pd.DataFrame,
    trades: pd.DataFrame,
    max_concurrent_positions: int = MAX_CONCURRENT_POSITIONS,
) -> pd.DataFrame:
    """
    Build simple equal-weight daily portfolio returns.

    On each day:
    - find active trades
    - each active trade receives equal weight up to 1 / max_concurrent_positions
    - idle capital earns 0
    """
    all_dates = (
        prices["date"]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )

    returns_wide = prices.pivot(index="date", columns="ticker", values="return").sort_index()

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
                    "portfolio_return": 0.0,
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
                ticker_return = returns_wide.loc[date, ticker]
            except KeyError:
                ticker_return = np.nan

            if pd.isna(ticker_return):
                continue

            day_return += weight * float(ticker_return)
            valid_positions += 1

        rows.append(
            {
                "date": date,
                "portfolio_return": day_return,
                "active_positions": valid_positions,
                "gross_exposure": valid_positions * weight,
            }
        )

    portfolio = pd.DataFrame(rows)
    portfolio = portfolio.sort_values("date").reset_index(drop=True)

    # Apply transaction costs at portfolio level on entry and exit dates.
    # Each accepted trade uses 1 / max_concurrent_positions capital.
    cost_per_side = TRANSACTION_COST_BPS_PER_SIDE / 10_000
    trade_weight = 1.0 / max_concurrent_positions

    portfolio["transaction_cost"] = 0.0

    for _, trade in trades.iterrows():
        entry_date = pd.Timestamp(trade["entry_date"])
        exit_date = pd.Timestamp(trade["exit_date"])

        entry_mask = portfolio["date"] == entry_date
        exit_mask = portfolio["date"] == exit_date

        portfolio.loc[entry_mask, "transaction_cost"] += trade_weight * cost_per_side
        portfolio.loc[exit_mask, "transaction_cost"] += trade_weight * cost_per_side

    portfolio["net_portfolio_return"] = (
        portfolio["portfolio_return"] - portfolio["transaction_cost"]
    )

    portfolio["equity_curve"] = (1 + portfolio["net_portfolio_return"]).cumprod()

    return portfolio


def max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate max drawdown from an equity curve."""
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    return float(drawdown.min())


def annualized_sharpe(daily_returns: pd.Series) -> float:
    """Calculate annualized Sharpe ratio using 252 trading days."""
    clean = daily_returns.dropna()

    if clean.std(ddof=1) == 0:
        return np.nan

    return float(np.sqrt(252) * clean.mean() / clean.std(ddof=1))


def summarize_backtest(
    trades: pd.DataFrame,
    portfolio: pd.DataFrame,
) -> pd.DataFrame:
    """Build one-row backtest summary."""
    daily_returns = portfolio["net_portfolio_return"]
    equity_curve = portfolio["equity_curve"]

    total_return = float(equity_curve.iloc[-1] - 1)
    sharpe = annualized_sharpe(daily_returns)
    mdd = max_drawdown(equity_curve)

    active_days = (portfolio["active_positions"] > 0).sum()
    total_days = len(portfolio)

    summary = {
        "strategy": STRATEGY_NAME,
        "hold_days": HOLD_DAYS,
        "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
        "transaction_cost_bps_per_side": TRANSACTION_COST_BPS_PER_SIDE,
        "n_trades": len(trades),
        "trade_win_rate": (trades["net_return"] > 0).mean(),
        "avg_trade_net_return": trades["net_return"].mean(),
        "median_trade_net_return": trades["net_return"].median(),
        "best_trade": trades["net_return"].max(),
        "worst_trade": trades["net_return"].min(),
        "total_return": total_return,
        "annualized_sharpe": sharpe,
        "max_drawdown": mdd,
        "active_days": int(active_days),
        "total_days": int(total_days),
        "active_day_ratio": active_days / total_days,
        "avg_active_positions": portfolio["active_positions"].mean(),
        "avg_gross_exposure": portfolio["gross_exposure"].mean(),
    }

    return pd.DataFrame([summary])


def run_backtest() -> None:
    """Run negative-event reversal 20d MVP backtest."""
    prices = load_prices()
    events = load_events()

    candidate_trades = build_candidate_trades(prices, events)
    trades = apply_concurrency_cap(candidate_trades)

    portfolio = build_daily_portfolio_returns(prices, trades)
    summary = summarize_backtest(trades, portfolio)

    TRADE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades.to_csv(TRADE_LEDGER_PATH, index=False)
    portfolio.to_csv(PORTFOLIO_RETURNS_PATH, index=False)
    summary.to_csv(BACKTEST_SUMMARY_PATH, index=False)

    print(f"Saved trade ledger to: {TRADE_LEDGER_PATH}")
    print(f"Saved portfolio returns to: {PORTFOLIO_RETURNS_PATH}")
    print(f"Saved backtest summary to: {BACKTEST_SUMMARY_PATH}")

    print()
    print("Backtest summary")
    print("----------------")
    print(summary.to_string(index=False))

    print()
    print("First 10 accepted trades")
    print("------------------------")
    print(
        trades[
            [
                "accepted_trade_id",
                "ticker",
                "event_date",
                "entry_date",
                "exit_date",
                "gross_return",
                "net_return",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    run_backtest()