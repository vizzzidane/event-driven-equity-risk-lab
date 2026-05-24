from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


EVENT_PANEL_PATH = Path("results/event_panel.csv")
EVENT_SUMMARY_PATH = Path("results/event_summary.csv")

FORWARD_RETURN_COLS = [
    "future_5d_abnormal_return",
    "future_10d_abnormal_return",
    "future_20d_abnormal_return",
]


def load_event_panel(path: Path = EVENT_PANEL_PATH) -> pd.DataFrame:
    """Load the event panel created by src/events.py."""
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


def _safe_t_stat(values: pd.Series) -> float:
    """Return one-sample t-stat against zero."""
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    result = stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit")
    return float(result.statistic)


def _safe_p_value(values: pd.Series) -> float:
    """Return one-sample p-value against zero."""
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    result = stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit")
    return float(result.pvalue)


def summarize_group(events: pd.DataFrame, group_name: str) -> dict[str, float | str | int]:
    """
    Summarize one event subset.

    For each forward abnormal return horizon, calculate:
    - mean
    - median
    - hit rate
    - t-stat
    - p-value
    """
    row: dict[str, float | str | int] = {
        "group": group_name,
        "n_events": len(events),
        "n_tickers": events["ticker"].nunique(),
        "start_date": events["date"].min().date().isoformat() if len(events) else "",
        "end_date": events["date"].max().date().isoformat() if len(events) else "",
        "avg_event_strength": events["event_strength"].mean(),
        "avg_volume_shock": events["volume_shock"].mean(),
    }

    for col in FORWARD_RETURN_COLS:
        horizon = col.replace("future_", "").replace("_abnormal_return", "")

        values = events[col].dropna()

        row[f"{horizon}_mean"] = values.mean()
        row[f"{horizon}_median"] = values.median()
        row[f"{horizon}_hit_rate"] = (values > 0).mean()
        row[f"{horizon}_t_stat"] = _safe_t_stat(values)
        row[f"{horizon}_p_value"] = _safe_p_value(values)

    return row


def build_event_summary(events: pd.DataFrame) -> pd.DataFrame:
    """Build summary table for all events and event-direction groups."""
    groups: list[tuple[str, pd.DataFrame]] = [
        ("all_events", events),
        ("positive_events", events[events["event_direction"] == "positive"]),
        ("negative_events", events[events["event_direction"] == "negative"]),
    ]

    rows = [summarize_group(group_df, group_name) for group_name, group_df in groups]
    summary = pd.DataFrame(rows)

    return summary


def print_summary(summary: pd.DataFrame) -> None:
    """Print the most important summary columns in a readable way."""
    display_cols = [
        "group",
        "n_events",
        "n_tickers",
        "5d_mean",
        "5d_hit_rate",
        "5d_t_stat",
        "10d_mean",
        "10d_hit_rate",
        "10d_t_stat",
        "20d_mean",
        "20d_hit_rate",
        "20d_t_stat",
    ]

    print()
    print("Event-study summary")
    print("-------------------")
    print(summary[display_cols].to_string(index=False))


def run_analysis() -> pd.DataFrame:
    """Load event panel, build event summary, save results."""
    events = load_event_panel()
    summary = build_event_summary(events)

    EVENT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(EVENT_SUMMARY_PATH, index=False)

    print(f"Saved event summary to: {EVENT_SUMMARY_PATH}")
    print_summary(summary)

    return summary


if __name__ == "__main__":
    run_analysis()