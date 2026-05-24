from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


EVENT_PANEL_PATH = Path("results/event_panel.csv")
EVENT_TYPE_ANALYSIS_PATH = Path("results/event_type_analysis.csv")
STRATEGY_CANDIDATE_PATH = Path("results/strategy_candidates.csv")

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

    events["event_sign"] = np.where(events["event_direction"] == "positive", 1.0, -1.0)

    return events.sort_values(["date", "ticker"]).reset_index(drop=True)


def add_strategy_returns(events: pd.DataFrame) -> pd.DataFrame:
    """
    Add candidate strategy return columns.

    Strategy interpretation:
    - all_event_drift: trade in event direction for all events
    - all_event_reversal: trade opposite event direction for all events
    - positive_event_drift: only positive events, long after event
    - negative_event_reversal: only negative events, long after negative event reversal
    """
    out = events.copy()

    for col in FORWARD_RETURN_COLS:
        horizon = col.replace("future_", "").replace("_abnormal_return", "")

        out[f"{horizon}_all_event_drift"] = out["event_sign"] * out[col]
        out[f"{horizon}_all_event_reversal"] = -out["event_sign"] * out[col]

        out[f"{horizon}_positive_event_drift"] = np.where(
            out["event_direction"] == "positive",
            out[col],
            np.nan,
        )

        out[f"{horizon}_negative_event_reversal"] = np.where(
            out["event_direction"] == "negative",
            out[col],
            np.nan,
        )

    return out


def safe_t_stat(values: pd.Series) -> float:
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    return float(stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit").statistic)


def safe_p_value(values: pd.Series) -> float:
    clean = values.dropna()

    if len(clean) < 2:
        return np.nan

    return float(stats.ttest_1samp(clean, popmean=0.0, nan_policy="omit").pvalue)


def summarize_strategy(
    data: pd.DataFrame,
    strategy_name: str,
    return_col: str,
) -> dict[str, float | int | str]:
    """Summarize one strategy candidate and holding horizon."""
    values = data[return_col].dropna()

    horizon = return_col.split("_")[0]

    return {
        "strategy": strategy_name,
        "horizon": horizon,
        "n_events": len(values),
        "mean_return": values.mean(),
        "median_return": values.median(),
        "hit_rate": (values > 0).mean(),
        "t_stat": safe_t_stat(values),
        "p_value": safe_p_value(values),
        "return_std": values.std(ddof=1),
        "avg_return_per_event_bps": values.mean() * 10_000,
    }


def build_strategy_candidate_table(events: pd.DataFrame) -> pd.DataFrame:
    """Build candidate strategy table across strategy types and horizons."""
    strategy_cols = {
        "all_event_drift": "All Event Drift",
        "all_event_reversal": "All Event Reversal",
        "positive_event_drift": "Positive Event Drift",
        "negative_event_reversal": "Negative Event Reversal",
    }

    rows = []

    for horizon in ["5d", "10d", "20d"]:
        for suffix, strategy_name in strategy_cols.items():
            col = f"{horizon}_{suffix}"
            rows.append(summarize_strategy(events, strategy_name, col))

    table = pd.DataFrame(rows)
    table = table.sort_values(["horizon", "mean_return"], ascending=[True, False])

    return table


def build_event_type_table(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize raw future abnormal returns by positive/negative event type."""
    rows = []

    for direction, group_df in events.groupby("event_direction"):
        row = {
            "event_direction": direction,
            "n_events": len(group_df),
            "n_tickers": group_df["ticker"].nunique(),
            "avg_abs_event_strength": group_df["event_strength"].abs().mean(),
            "avg_volume_shock": group_df["volume_shock"].mean(),
        }

        for col in FORWARD_RETURN_COLS:
            horizon = col.replace("future_", "").replace("_abnormal_return", "")
            values = group_df[col].dropna()

            row[f"{horizon}_mean"] = values.mean()
            row[f"{horizon}_hit_rate"] = (values > 0).mean()
            row[f"{horizon}_t_stat"] = safe_t_stat(values)

        rows.append(row)

    return pd.DataFrame(rows)


def print_strategy_candidates(candidates: pd.DataFrame) -> None:
    """Print compact candidate table."""
    display_cols = [
        "strategy",
        "horizon",
        "n_events",
        "mean_return",
        "avg_return_per_event_bps",
        "hit_rate",
        "t_stat",
        "p_value",
    ]

    print()
    print("Strategy candidate table")
    print("------------------------")
    print(candidates[display_cols].to_string(index=False))


def print_best_by_horizon(candidates: pd.DataFrame) -> None:
    """Print best strategy for each horizon by mean return."""
    best = (
        candidates.sort_values("mean_return", ascending=False)
        .groupby("horizon", as_index=False)
        .head(1)
        .sort_values("horizon")
    )

    print()
    print("Best candidate by horizon")
    print("-------------------------")
    print(
        best[
            [
                "horizon",
                "strategy",
                "n_events",
                "mean_return",
                "avg_return_per_event_bps",
                "hit_rate",
                "t_stat",
            ]
        ].to_string(index=False)
    )


def run_event_type_analysis() -> None:
    """Run event-type and strategy-candidate analysis."""
    events = load_event_panel()
    strategy_events = add_strategy_returns(events)

    EVENT_TYPE_ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)

    event_type_table = build_event_type_table(strategy_events)
    event_type_table.to_csv(EVENT_TYPE_ANALYSIS_PATH, index=False)

    candidates = build_strategy_candidate_table(strategy_events)
    candidates.to_csv(STRATEGY_CANDIDATE_PATH, index=False)

    print(f"Saved event type analysis to: {EVENT_TYPE_ANALYSIS_PATH}")
    print(f"Saved strategy candidates to: {STRATEGY_CANDIDATE_PATH}")

    print_strategy_candidates(candidates)
    print_best_by_horizon(candidates)


if __name__ == "__main__":
    run_event_type_analysis()