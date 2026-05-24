from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from universe import ALL_DOWNLOAD_TICKERS, ACTIVE_STOCK_TICKERS, MARKET_TICKER


RAW_DATA_PATH = Path("data/raw/starter_prices.csv")
PROCESSED_DATA_PATH = Path("data/processed/starter_prices_with_returns.csv")

START_DATE = "2015-01-01"
END_DATE = None

MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 2.0


def normalise_ticker_for_filename(ticker: str) -> str:
    """Convert symbols like ^VIX into safer strings if needed later."""
    return ticker.replace("^", "")


def flatten_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    yfinance sometimes returns MultiIndex columns depending on version/settings.
    This function converts them into ordinary single-level columns.
    """
    out = df.copy()

    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            "_".join(str(part) for part in col if str(part) != "")
            for col in out.columns
        ]

    return out


def standardize_price_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Convert a raw yfinance download into a standardized OHLCV DataFrame.

    Output columns:
    date, ticker, open, high, low, close, adj_close, volume
    """
    if df.empty:
        raise ValueError(f"{ticker} returned an empty DataFrame.")

    out = flatten_yfinance_columns(df)
    out = out.reset_index()

    rename_map = {}

    for col in out.columns:
        lower = str(col).lower().replace(" ", "_")

        if lower in {"date", "datetime"}:
            rename_map[col] = "date"
        elif lower in {"open", f"open_{ticker.lower()}"}:
            rename_map[col] = "open"
        elif lower in {"high", f"high_{ticker.lower()}"}:
            rename_map[col] = "high"
        elif lower in {"low", f"low_{ticker.lower()}"}:
            rename_map[col] = "low"
        elif lower in {"close", f"close_{ticker.lower()}"}:
            rename_map[col] = "close"
        elif lower in {
            "adj_close",
            "adjusted_close",
            f"adj_close_{ticker.lower()}",
            f"adjusted_close_{ticker.lower()}",
        }:
            rename_map[col] = "adj_close"
        elif lower in {"volume", f"volume_{ticker.lower()}"}:
            rename_map[col] = "volume"

    out = out.rename(columns=rename_map)

    if "date" not in out.columns:
        first_col = out.columns[0]
        out = out.rename(columns={first_col: "date"})

    if "adj_close" not in out.columns and "close" in out.columns:
        out["adj_close"] = out["close"]

    required = ["date", "open", "high", "low", "close", "adj_close", "volume"]
    missing = [col for col in required if col not in out.columns]

    if missing:
        raise ValueError(f"{ticker} missing columns after download: {missing}")

    out = out[required].copy()
    out["ticker"] = ticker

    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.sort_values("date").reset_index(drop=True)

    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["date", "adj_close", "volume"])
    out = out[out["adj_close"] > 0].copy()
    out = out[out["volume"] >= 0].copy()

    return out[
        ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    ]


def download_one_ticker(
    ticker: str,
    start: str = START_DATE,
    end: str | None = END_DATE,
) -> pd.DataFrame | None:
    """Download one ticker with retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Downloading {ticker}...")

            raw = yf.download(
                tickers=ticker,
                start=start,
                end=end,
                auto_adjust=False,
                progress=False,
                threads=False,
            )

            return standardize_price_columns(raw, ticker)

        except Exception as exc:
            print(
                f"WARNING: failed to download {ticker} "
                f"(attempt {attempt}/{MAX_RETRIES}): {exc}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)

    return None


def download_prices(
    tickers: list[str],
    start: str = START_DATE,
    end: str | None = END_DATE,
) -> pd.DataFrame:
    """Download all tickers sequentially to avoid yfinance cache/database issues."""
    frames: list[pd.DataFrame] = []
    failed: list[str] = []

    for ticker in tickers:
        ticker_data = download_one_ticker(ticker=ticker, start=start, end=end)

        if ticker_data is None or ticker_data.empty:
            failed.append(ticker)
            continue

        frames.append(ticker_data)

    if not frames:
        raise RuntimeError("No valid ticker data found after download.")

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)

    if failed:
        print()
        print("WARNING: failed tickers")
        print("-----------------------")
        for ticker in failed:
            print(f"- {ticker}")

    return prices


def add_return_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Add returns and basic liquidity fields."""
    out = prices.copy()
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    out["return"] = out.groupby("ticker")["adj_close"].pct_change()
    out["dollar_volume"] = out["adj_close"] * out["volume"]

    out["log_return"] = (
        out.groupby("ticker")["adj_close"]
        .transform(lambda s: (s / s.shift(1)))
        .apply(lambda x: pd.NA if pd.isna(x) or x <= 0 else x)
    )

    out["log_return"] = pd.to_numeric(out["log_return"], errors="coerce")
    out["log_return"] = out["log_return"].apply(
        lambda x: pd.NA if pd.isna(x) else pd.NA
    )

    # Use numpy log through pandas after avoiding non-positive values.
    price_ratio = out.groupby("ticker")["adj_close"].transform(lambda s: s / s.shift(1))
    out["log_return"] = price_ratio.where(price_ratio > 0).apply(
        lambda x: pd.NA if pd.isna(x) else __import__("math").log(x)
    )

    return out


def validate_dataset(prices: pd.DataFrame) -> None:
    """Basic data-quality checks for the downloaded panel."""
    required = {
        "date",
        "ticker",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "return",
        "dollar_volume",
    }

    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"Processed dataset missing columns: {sorted(missing)}")

    tickers_found = set(prices["ticker"].unique())

    if MARKET_TICKER not in tickers_found:
        raise ValueError(f"Missing market benchmark: {MARKET_TICKER}")

    stock_tickers_found = tickers_found.intersection(set(ACTIVE_STOCK_TICKERS))

    if len(stock_tickers_found) < 10:
        raise ValueError(
            "Too few stock tickers downloaded successfully: "
            f"{len(stock_tickers_found)}"
        )


def build_initial_dataset() -> None:
    """Download and process the project price dataset."""
    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    tickers = ALL_DOWNLOAD_TICKERS

    print("Active stock universe")
    print("---------------------")
    print(f"Stocks: {len(ACTIVE_STOCK_TICKERS)}")
    print(f"Benchmark: {MARKET_TICKER}")
    print(f"Total downloads: {len(tickers)}")
    print()

    raw_prices = download_prices(
        tickers=tickers,
        start=START_DATE,
        end=END_DATE,
    )

    processed = add_return_features(raw_prices)
    validate_dataset(processed)

    raw_prices.to_csv(RAW_DATA_PATH, index=False)
    processed.to_csv(PROCESSED_DATA_PATH, index=False)

    stock_count = processed[
        processed["ticker"].isin(ACTIVE_STOCK_TICKERS)
    ]["ticker"].nunique()

    print()
    print(f"Saved raw data to: {RAW_DATA_PATH}")
    print(f"Saved processed data to: {PROCESSED_DATA_PATH}")
    print(f"Rows: {len(processed):,}")
    print(f"Stock tickers found: {stock_count}")
    print(f"Total tickers found: {processed['ticker'].nunique()}")
    print(
        "Date range: "
        f"{processed['date'].min().date()} to {processed['date'].max().date()}"
    )


if __name__ == "__main__":
    build_initial_dataset()