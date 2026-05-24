from __future__ import annotations

from pathlib import Path

import pandas as pd


ABNORMAL_TRADE_LEDGER_PATH = Path("results/abnormal_trade_ledger.csv")
ABNORMAL_PORTFOLIO_RETURNS_PATH = Path("results/abnormal_portfolio_returns.csv")

VALIDATION_BY_TICKER_PATH = Path("results/backtest_validation_by_ticker.csv")
VALIDATION_BY_YEAR_PATH = Path("results/backtest_validation_by_year.csv")
WORST_TRADES_PATH = Path("results/backtest_worst_trades.csv")
BEST_TRADES_PATH = Path("results/backtest_best_trades.csv")
DRAWDOWN_PATH = Path("results/backtest_drawdowns.csv")


def load_trades(path: Path = ABNORMAL_TRADE_LEDGER_PATH) -> pd.DataFrame:
    """Load abnormal-return trade ledger."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing trade ledger: {path}. Run `python src/backtest_abnormal.py` first."
        )

    trades = pd.read_csv(
        path,
        parse_dates=["event_date", "entry_date", "exit_date"],
    )

    required = {
        "ticker",
        "event_date",
        "entry_date",
        "exit_date",
        "gross_stock_return",
        "gross_abnormal_return",
        "net_abnormal_return",
    }

    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    trades["entry_year"] = trades["entry_date"].dt.year

    return trades.sort_values(["entry_date", "ticker"]).reset_index(drop=True)


def load_portfolio(path: Path = ABNORMAL_PORTFOLIO_RETURNS_PATH) -> pd.DataFrame:
    """Load abnormal-return portfolio returns."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing portfolio returns: {path}. Run `python src/backtest_abnormal.py` first."
        )

    portfolio = pd.read_csv(path, parse_dates=["date"])

    required = {
        "date",
        "net_portfolio_abnormal_return",
        "abnormal_equity_curve",
        "active_positions",
        "gross_exposure",
    }

    missing = required - set(portfolio.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return portfolio.sort_values("date").reset_index(drop=True)


def summarize_trades_by_group(trades: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Summarize abnormal trade returns by ticker or year."""
    rows = []

    for group_value, group_df in trades.groupby(group_col):
        returns = group_df["net_abnormal_return"]

        rows.append(
            {
                group_col: group_value,
                "n_trades": len(group_df),
                "win_rate": (returns > 0).mean(),
                "avg_net_abnormal_return": returns.mean(),
                "median_net_abnormal_return": returns.median(),
                "best_trade": returns.max(),
                "worst_trade": returns.min(),
                "total_trade_return_sum": returns.sum(),
            }
        )

    return pd.DataFrame(rows)


def add_drawdown_columns(portfolio: pd.DataFrame) -> pd.DataFrame:
    """Add drawdown diagnostics to portfolio returns."""
    out = portfolio.copy()

    out["running_peak"] = out["abnormal_equity_curve"].cummax()
    out["drawdown"] = out["abnormal_equity_curve"] / out["running_peak"] - 1

    return out


def print_by_ticker(by_ticker: pd.DataFrame) -> None:
    """Print ticker-level validation."""
    print()
    print("Backtest validation by ticker")
    print("-----------------------------")
    print(
        by_ticker[
            [
                "ticker",
                "n_trades",
                "win_rate",
                "avg_net_abnormal_return",
                "median_net_abnormal_return",
                "best_trade",
                "worst_trade",
                "total_trade_return_sum",
            ]
        ].to_string(index=False)
    )


def print_by_year(by_year: pd.DataFrame) -> None:
    """Print year-level validation."""
    print()
    print("Backtest validation by year")
    print("---------------------------")
    print(
        by_year[
            [
                "entry_year",
                "n_trades",
                "win_rate",
                "avg_net_abnormal_return",
                "median_net_abnormal_return",
                "best_trade",
                "worst_trade",
                "total_trade_return_sum",
            ]
        ].to_string(index=False)
    )


def print_extreme_trades(best_trades: pd.DataFrame, worst_trades: pd.DataFrame) -> None:
    """Print best and worst trades."""
    display_cols = [
        "ticker",
        "event_date",
        "entry_date",
        "exit_date",
        "gross_stock_return",
        "gross_abnormal_return",
        "net_abnormal_return",
    ]

    print()
    print("Worst 10 abnormal-return trades")
    print("-------------------------------")
    print(worst_trades[display_cols].to_string(index=False))

    print()
    print("Best 10 abnormal-return trades")
    print("------------------------------")
    print(best_trades[display_cols].to_string(index=False))


def print_drawdown_summary(drawdowns: pd.DataFrame) -> None:
    """Print drawdown summary."""
    worst_drawdown_row = drawdowns.loc[drawdowns["drawdown"].idxmin()]

    print()
    print("Drawdown summary")
    print("----------------")
    print(f"Worst drawdown date: {worst_drawdown_row['date'].date()}")
    print(f"Worst drawdown: {worst_drawdown_row['drawdown']:.2%}")
    print(f"Equity curve at worst drawdown: {worst_drawdown_row['abnormal_equity_curve']:.4f}")


def run_backtest_validation() -> None:
    """Run validation on abnormal-return backtest outputs."""
    trades = load_trades()
    portfolio = load_portfolio()

    by_ticker = summarize_trades_by_group(trades, "ticker").sort_values(
        "total_trade_return_sum",
        ascending=False,
    )
    by_ticker.to_csv(VALIDATION_BY_TICKER_PATH, index=False)

    by_year = summarize_trades_by_group(trades, "entry_year").sort_values("entry_year")
    by_year.to_csv(VALIDATION_BY_YEAR_PATH, index=False)

    worst_trades = trades.sort_values("net_abnormal_return").head(10)
    best_trades = trades.sort_values("net_abnormal_return", ascending=False).head(10)

    worst_trades.to_csv(WORST_TRADES_PATH, index=False)
    best_trades.to_csv(BEST_TRADES_PATH, index=False)

    drawdowns = add_drawdown_columns(portfolio)
    drawdowns.to_csv(DRAWDOWN_PATH, index=False)

    print(f"Saved ticker validation to: {VALIDATION_BY_TICKER_PATH}")
    print(f"Saved year validation to: {VALIDATION_BY_YEAR_PATH}")
    print(f"Saved worst trades to: {WORST_TRADES_PATH}")
    print(f"Saved best trades to: {BEST_TRADES_PATH}")
    print(f"Saved drawdowns to: {DRAWDOWN_PATH}")

    print_by_ticker(by_ticker)
    print_by_year(by_year)
    print_extreme_trades(best_trades, worst_trades)
    print_drawdown_summary(drawdowns)


if __name__ == "__main__":
    run_backtest_validation()