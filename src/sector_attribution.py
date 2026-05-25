from __future__ import annotations

from pathlib import Path

import pandas as pd

try:
    from src.sectors import SECTOR_MAP
except ModuleNotFoundError:
    from sectors import SECTOR_MAP


TRADE_LEDGER_PATH = Path(
    "results/walk_forward_expanded_paced_trades.csv"
)

SECTOR_ATTRIBUTION_PATH = Path(
    "results/sector_attribution.csv"
)


def load_trade_ledger(
    path: Path = TRADE_LEDGER_PATH,
) -> pd.DataFrame:
    """Load expanded global-paced trade ledger."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing trade ledger: {path}"
        )

    trades = pd.read_csv(
        path,
        parse_dates=[
            "event_date",
            "entry_date",
            "exit_date",
        ],
    )

    return trades


def build_sector_attribution(
    trades: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate trade performance by sector."""
    trades = trades.copy()

    trades["sector"] = (
        trades["ticker"]
        .map(SECTOR_MAP)
        .fillna("Unknown")
    )

    grouped = (
        trades.groupby("sector")
        .agg(
            trades=("ticker", "count"),
            win_rate=(
                "net_abnormal_return",
                lambda x: (x > 0).mean(),
            ),
            avg_trade_return=(
                "net_abnormal_return",
                "mean",
            ),
            median_trade_return=(
                "net_abnormal_return",
                "median",
            ),
            total_return=(
                "net_abnormal_return",
                "sum",
            ),
        )
        .reset_index()
    )

    grouped = grouped.sort_values(
        "total_return",
        ascending=False,
    ).reset_index(drop=True)

    return grouped


def main() -> None:
    trades = load_trade_ledger()

    attribution = build_sector_attribution(trades)

    SECTOR_ATTRIBUTION_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    attribution.to_csv(
        SECTOR_ATTRIBUTION_PATH,
        index=False,
    )

    print()
    print("Sector attribution summary")
    print("--------------------------")
    print(attribution.to_string(index=False))

    print()
    print("Unknown sector tickers")
    print("----------------------")

    trades_with_sector = trades.copy()

    trades_with_sector["sector"] = (
        trades_with_sector["ticker"]
        .map(SECTOR_MAP)
        .fillna("Unknown")
    )

    unknown_counts = (
        trades_with_sector[
            trades_with_sector["sector"] == "Unknown"
        ]["ticker"]
        .value_counts()
    )

    if unknown_counts.empty:
        print("None")
    else:
        print(unknown_counts.to_string())

    print()
    print(
        f"Saved sector attribution to: "
        f"{SECTOR_ATTRIBUTION_PATH}"
    )


if __name__ == "__main__":
    main()