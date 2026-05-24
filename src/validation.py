from __future__ import annotations

from pathlib import Path

import pandas as pd


EVENT_PANEL_PATH = Path("results/event_panel.csv")

TICKER_VALIDATION_PATH = Path("results/validation_by_ticker.csv")
YEAR_VALIDATION_PATH = Path("results/validation_by_year.csv")
DIRECTION_YEAR_VALIDATION_PATH = Path("results/validation_by_direction_year.csv")
STRENGTH_BUCKET_VALIDATION_PATH = Path("results/validation_by_strength_bucket.csv")
VOLUME_BUCKET_VALIDATION_PATH = Path("results/validation_by_volume_bucket.csv")

FORWARD_COLS = [
    "future_5d_abnormal_return",
    "future_10d_abnormal_return",
    "future_20d_abnormal_return",
]


def load_event_panel(path: Path = EVENT_PANEL_PATH) -> pd.DataFrame:
    """Load event panel from results/event_panel.csv."""
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
        *FORWARD_COLS,
    }

    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    events["year"] = events["date"].dt.year
    events["abs_event_strength"] = events["event_strength"].abs()

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def summarize_grouped(events: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """
    Summarize event outcomes by group.

    Reports:
    - event count
    - mean future abnormal returns
    - hit rates
    - average event strength
    - average volume shock
    """
    rows = []

    for group_key, group_df in events.groupby(group_cols):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)

        row = {
            col: value for col, value in zip(group_cols, group_key, strict=True)
        }

        row["n_events"] = len(group_df)
        row["avg_abs_event_strength"] = group_df["abs_event_strength"].mean()
        row["avg_volume_shock"] = group_df["volume_shock"].mean()

        for col in FORWARD_COLS:
            horizon = col.replace("future_", "").replace("_abnormal_return", "")
            values = group_df[col].dropna()

            row[f"{horizon}_mean"] = values.mean()
            row[f"{horizon}_hit_rate"] = (values > 0).mean()

        rows.append(row)

    return pd.DataFrame(rows)


def add_quantile_bucket(
    events: pd.DataFrame,
    source_col: str,
    bucket_col: str,
    n_buckets: int = 5,
) -> pd.DataFrame:
    """
    Add quantile buckets for a column.

    Uses duplicates='drop' so it does not fail if many values are repeated.
    """
    out = events.copy()

    out[bucket_col] = pd.qcut(
        out[source_col],
        q=n_buckets,
        labels=[f"Q{i}" for i in range(1, n_buckets + 1)],
        duplicates="drop",
    )

    return out


def run_validation() -> None:
    """Run concentration and robustness validation tables."""
    events = load_event_panel()

    TICKER_VALIDATION_PATH.parent.mkdir(parents=True, exist_ok=True)

    by_ticker = summarize_grouped(events, ["ticker"]).sort_values(
        "20d_mean", ascending=False
    )
    by_ticker.to_csv(TICKER_VALIDATION_PATH, index=False)

    by_year = summarize_grouped(events, ["year"]).sort_values("year")
    by_year.to_csv(YEAR_VALIDATION_PATH, index=False)

    by_direction_year = summarize_grouped(
        events, ["event_direction", "year"]
    ).sort_values(["event_direction", "year"])
    by_direction_year.to_csv(DIRECTION_YEAR_VALIDATION_PATH, index=False)

    strength_events = add_quantile_bucket(
        events=events,
        source_col="abs_event_strength",
        bucket_col="strength_bucket",
        n_buckets=5,
    )
    by_strength_bucket = summarize_grouped(
        strength_events, ["strength_bucket"]
    ).sort_values("strength_bucket")
    by_strength_bucket.to_csv(STRENGTH_BUCKET_VALIDATION_PATH, index=False)

    volume_events = add_quantile_bucket(
        events=events,
        source_col="volume_shock",
        bucket_col="volume_bucket",
        n_buckets=5,
    )
    by_volume_bucket = summarize_grouped(
        volume_events, ["volume_bucket"]
    ).sort_values("volume_bucket")
    by_volume_bucket.to_csv(VOLUME_BUCKET_VALIDATION_PATH, index=False)

    print("Saved validation outputs:")
    print(f"- {TICKER_VALIDATION_PATH}")
    print(f"- {YEAR_VALIDATION_PATH}")
    print(f"- {DIRECTION_YEAR_VALIDATION_PATH}")
    print(f"- {STRENGTH_BUCKET_VALIDATION_PATH}")
    print(f"- {VOLUME_BUCKET_VALIDATION_PATH}")

    print()
    print("20d abnormal return by ticker")
    print("-----------------------------")
    print(
        by_ticker[
            [
                "ticker",
                "n_events",
                "20d_mean",
                "20d_hit_rate",
                "avg_abs_event_strength",
                "avg_volume_shock",
            ]
        ].to_string(index=False)
    )

    print()
    print("20d abnormal return by year")
    print("---------------------------")
    print(
        by_year[
            [
                "year",
                "n_events",
                "20d_mean",
                "20d_hit_rate",
                "avg_abs_event_strength",
                "avg_volume_shock",
            ]
        ].to_string(index=False)
    )

    print()
    print("20d abnormal return by event strength bucket")
    print("--------------------------------------------")
    print(
        by_strength_bucket[
            [
                "strength_bucket",
                "n_events",
                "20d_mean",
                "20d_hit_rate",
                "avg_abs_event_strength",
                "avg_volume_shock",
            ]
        ].to_string(index=False)
    )

    print()
    print("20d abnormal return by volume shock bucket")
    print("-----------------------------------------")
    print(
        by_volume_bucket[
            [
                "volume_bucket",
                "n_events",
                "20d_mean",
                "20d_hit_rate",
                "avg_abs_event_strength",
                "avg_volume_shock",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    run_validation()