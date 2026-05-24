from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


EVENT_PANEL_PATH = Path("results/event_panel.csv")
DIRECTIONAL_SUMMARY_PATH = Path("results/directional_summary.csv")
DIRECTIONAL_BY_TICKER_PATH = Path("results/directional_by_ticker.csv")
DIRECTIONAL_BY_YEAR_PATH = Path("results/directional_by_year.csv")

FORWARD_RETURN_COLS = [
    "future_5d_abnormal_return",
    "future_10d_abnormal_return",
    "future_20d_abnormal_return",
]


def load_event_panel(path: Path = EVENT_PANEL_PATH) -> pd.DataFrame:
    """Load event panel created by src/events.py."""
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
        *FORWARD_RETURN_COLS,
    }

    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def add_directional_returns(events: pd.DataFrame) -> pd.DataFrame:
    """
    Add directional drift and reversal targets.

    For drift:
    - positive event: future abnormal return is good
    - negative event: negative future abnormal return is good

    For reversal:
    - positive event: negative future abnormal return is good
    - negative event: future abnormal return is good
    """
    out = events.copy()

    out["event_sign"] = np.where(out["event_direction"] == "positive", 1.0, -1.0)

    for col in FORWARD_RETURN_COLS:
        horizon = col.replace("future_", "").replace("_abnormal_return", "")

        out[f"{horizon}_directional_drift_return"] = out["event_sign"] * out[col]
        out[f"{horizon}_directional_reversal_return"] = -out["event_sign"] * out[col]

    return out


def _safe_t_stat(values: pd.Series) -> float:
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    result = stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit")
    return float(result.statistic)


def _safe_p_value(values: pd.Series) -> float:
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    result = stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit")
    return float(result.pvalue)


def summarize_directional_group(
    events: pd.DataFrame,
    group_name: str,
) -> dict[str, float | int | str]:
    """Summarize drift/reversal directional returns for one event subset."""
    row: dict[str, float | int | str] = {
        "group": group_name,
        "n_events": len(events),
        "n_tickers": events["ticker"].nunique(),
        "start_date": events["date"].min().date().isoformat() if len(events) else "",
        "end_date": events["date"].max().date().isoformat() if len(events) else "",
        "avg_abs_event_strength": events["event_strength"].abs().mean(),
        "avg_volume_shock": events["volume_shock"].mean(),
    }

    for horizon in ["5d", "10d", "20d"]:
        drift_col = f"{horizon}_directional_drift_return"
        reversal_col = f"{horizon}_directional_reversal_return"

        drift_values = events[drift_col].dropna()
        reversal_values = events[reversal_col].dropna()

        row[f"{horizon}_drift_mean"] = drift_values.mean()
        row[f"{horizon}_drift_hit_rate"] = (drift_values > 0).mean()
        row[f"{horizon}_drift_t_stat"] = _safe_t_stat(drift_values)
        row[f"{horizon}_drift_p_value"] = _safe_p_value(drift_values)

        row[f"{horizon}_reversal_mean"] = reversal_values.mean()
        row[f"{horizon}_reversal_hit_rate"] = (reversal_values > 0).mean()
        row[f"{horizon}_reversal_t_stat"] = _safe_t_stat(reversal_values)
        row[f"{horizon}_reversal_p_value"] = _safe_p_value(reversal_values)

    return row


def build_directional_summary(events: pd.DataFrame) -> pd.DataFrame:
    """Build all-events and positive/negative event directional summary."""
    groups = [
        ("all_events", events),
        ("positive_events", events[events["event_direction"] == "positive"]),
        ("negative_events", events[events["event_direction"] == "negative"]),
    ]

    rows = [
        summarize_directional_group(group_df, group_name)
        for group_name, group_df in groups
    ]

    return pd.DataFrame(rows)


def summarize_by_group(events: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Summarize 20d directional drift/reversal returns by group."""
    rows = []

    for group_key, group_df in events.groupby(group_cols):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)

        row = {
            col: value for col, value in zip(group_cols, group_key, strict=True)
        }

        row["n_events"] = len(group_df)
        row["avg_abs_event_strength"] = group_df["event_strength"].abs().mean()
        row["avg_volume_shock"] = group_df["volume_shock"].mean()

        drift = group_df["20d_directional_drift_return"].dropna()
        reversal = group_df["20d_directional_reversal_return"].dropna()

        row["20d_drift_mean"] = drift.mean()
        row["20d_drift_hit_rate"] = (drift > 0).mean()
        row["20d_reversal_mean"] = reversal.mean()
        row["20d_reversal_hit_rate"] = (reversal > 0).mean()

        rows.append(row)

    return pd.DataFrame(rows)


def print_directional_summary(summary: pd.DataFrame) -> None:
    """Print compact directional summary."""
    display_cols = [
        "group",
        "n_events",
        "5d_drift_mean",
        "5d_drift_hit_rate",
        "5d_drift_t_stat",
        "10d_drift_mean",
        "10d_drift_hit_rate",
        "10d_drift_t_stat",
        "20d_drift_mean",
        "20d_drift_hit_rate",
        "20d_drift_t_stat",
        "20d_reversal_mean",
        "20d_reversal_hit_rate",
        "20d_reversal_t_stat",
    ]

    print()
    print("Directional drift/reversal summary")
    print("----------------------------------")
    print(summary[display_cols].to_string(index=False))


def run_directional_analysis() -> None:
    """Run directional drift/reversal analysis."""
    events = load_event_panel()
    directional = add_directional_returns(events)
    directional["year"] = directional["date"].dt.year

    DIRECTIONAL_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    summary = build_directional_summary(directional)
    summary.to_csv(DIRECTIONAL_SUMMARY_PATH, index=False)

    by_ticker = summarize_by_group(directional, ["ticker"]).sort_values(
        "20d_drift_mean",
        ascending=False,
    )
    by_ticker.to_csv(DIRECTIONAL_BY_TICKER_PATH, index=False)

    by_year = summarize_by_group(directional, ["year"]).sort_values("year")
    by_year.to_csv(DIRECTIONAL_BY_YEAR_PATH, index=False)

    print(f"Saved directional summary to: {DIRECTIONAL_SUMMARY_PATH}")
    print(f"Saved directional by ticker to: {DIRECTIONAL_BY_TICKER_PATH}")
    print(f"Saved directional by year to: {DIRECTIONAL_BY_YEAR_PATH}")

    print_directional_summary(summary)

    print()
    print("20d directional drift by ticker")
    print("-------------------------------")
    print(
        by_ticker[
            [
                "ticker",
                "n_events",
                "20d_drift_mean",
                "20d_drift_hit_rate",
                "20d_reversal_mean",
                "20d_reversal_hit_rate",
            ]
        ].to_string(index=False)
    )

    print()
    print("20d directional drift by year")
    print("-----------------------------")
    print(
        by_year[
            [
                "year",
                "n_events",
                "20d_drift_mean",
                "20d_drift_hit_rate",
                "20d_reversal_mean",
                "20d_reversal_hit_rate",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    run_directional_analysis()