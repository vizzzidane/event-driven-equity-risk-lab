from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf


RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")

DEFAULT_TICKERS = [
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

BENCHMARK_TICKERS = ["SPY", "^VIX"]


def ensure_data_dirs() -> None:
    """Create raw and processed data folders if they do not exist."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _clean_single_ticker_download(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Convert one yfinance ticker download into standard long-format rows.

    Output columns:
    date, ticker, open, high, low, close, adj_close, volume
    """
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")

    out = data.copy()

    # Some yfinance versions return MultiIndex columns even for one ticker.
    # Flatten them safely.
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            col[0] if col[0] else col[-1]
            for col in out.columns.to_list()
        ]

    out = out.reset_index()

    # Normalize column names.
    normalized_cols = {}
    for col in out.columns:
        col_str = str(col).strip().lower()

        if col_str in {"date", "datetime"}:
            normalized_cols[col] = "date"
        elif col_str == "open":
            normalized_cols[col] = "open"
        elif col_str == "high":
            normalized_cols[col] = "high"
        elif col_str == "low":
            normalized_cols[col] = "low"
        elif col_str == "close":
            normalized_cols[col] = "close"
        elif col_str in {"adj close", "adj_close"}:
            normalized_cols[col] = "adj_close"
        elif col_str == "volume":
            normalized_cols[col] = "volume"

    out = out.rename(columns=normalized_cols)

    # If yfinance's index reset did not preserve the name cleanly,
    # use the first column as date.
    if "date" not in out.columns:
        first_col = out.columns[0]
        out = out.rename(columns={first_col: "date"})

    # If adjusted close is missing, fall back to close.
    if "adj_close" not in out.columns and "close" in out.columns:
        out["adj_close"] = out["close"]

    required_cols = ["date", "open", "high", "low", "close", "adj_close", "volume"]
    missing = [col for col in required_cols if col not in out.columns]

    if missing:
        raise ValueError(
            f"{ticker} missing columns after download: {missing}. "
            f"Available columns: {list(out.columns)}"
        )

    out["ticker"] = ticker

    final_cols = [
        "date",
        "ticker",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
    ]

    out = out[final_cols]
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.dropna(subset=["date", "adj_close"])
    out = out.sort_values("date").reset_index(drop=True)

    return out


def download_prices(
    tickers: list[str],
    start: str = "2015-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """
    Download daily OHLCV data from Yahoo Finance.

    This downloads tickers sequentially instead of in one large batch.
    That is slower, but more reliable and avoids yfinance cache/database lock issues.
    """
    if not tickers:
        raise ValueError("tickers must not be empty")

    frames: list[pd.DataFrame] = []
    failed: list[str] = []

    for ticker in tickers:
        print(f"Downloading {ticker}...")

        try:
            data = yf.download(
                tickers=ticker,
                start=start,
                end=end,
                auto_adjust=False,
                progress=False,
                threads=False,
            )

            ticker_df = _clean_single_ticker_download(data, ticker)
            frames.append(ticker_df)

        except Exception as exc:
            print(f"WARNING: failed to download {ticker}: {exc}")
            failed.append(ticker)

    if not frames:
        raise RuntimeError("No valid ticker data found after download.")

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)

    if failed:
        print(f"Skipped failed tickers: {failed}")

    return prices


def add_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Add adjusted-close daily returns and dollar volume.
    """
    required = {"date", "ticker", "adj_close", "volume"}
    missing = required - set(prices.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    out = prices.copy()
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    out["return"] = out.groupby("ticker")["adj_close"].pct_change()
    out["dollar_volume"] = out["adj_close"] * out["volume"]

    return out


def build_initial_dataset(
    start: str = "2015-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """
    Download starter stock, SPY, and VIX data, then save raw and processed CSVs.
    """
    ensure_data_dirs()

    tickers = DEFAULT_TICKERS + BENCHMARK_TICKERS
    prices = download_prices(tickers=tickers, start=start, end=end)

    raw_path = RAW_DATA_DIR / "starter_prices.csv"
    prices.to_csv(raw_path, index=False)

    processed = add_returns(prices)

    processed_path = PROCESSED_DATA_DIR / "starter_prices_with_returns.csv"
    processed.to_csv(processed_path, index=False)

    print()
    print(f"Saved raw data to: {raw_path}")
    print(f"Saved processed data to: {processed_path}")
    print(f"Rows: {len(processed):,}")
    print(f"Tickers: {processed['ticker'].nunique()}")
    print(f"Date range: {processed['date'].min().date()} to {processed['date'].max().date()}")

    return processed


if __name__ == "__main__":
    build_initial_dataset()