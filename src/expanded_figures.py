from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


RESULTS_DIR = Path("results")
FIGURES_DIR = RESULTS_DIR / "figures"

EVENT_SUMMARY_PATH = RESULTS_DIR / "event_summary.csv"
STRATEGY_CANDIDATES_PATH = RESULTS_DIR / "strategy_candidates.csv"
COOLDOWN_SENSITIVITY_PATH = RESULTS_DIR / "cooldown_sensitivity.csv"
GLOBAL_PACING_SENSITIVITY_PATH = RESULTS_DIR / "global_pacing_sensitivity.csv"
ABNORMAL_BACKTEST_SUMMARY_PATH = RESULTS_DIR / "abnormal_backtest_summary.csv"


def require_csv(path: Path) -> pd.DataFrame:
    """Load a required CSV result file."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing required result file: {path}. "
            "Run the relevant analysis script first."
        )

    return pd.read_csv(path)


def save_current_figure(path: Path) -> None:
    """Save current matplotlib figure cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()


def plot_expanded_event_study_20d() -> None:
    """Plot expanded-universe 20d event-study mean abnormal returns."""
    df = require_csv(EVENT_SUMMARY_PATH).copy()

    required = {"group", "20d_mean", "20d_t_stat"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{EVENT_SUMMARY_PATH} missing columns: {sorted(missing)}")

    fig, ax = plt.subplots(figsize=(9, 5))

    ax.bar(df["group"], df["20d_mean"])
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_xlabel("Event group")
    ax.set_ylabel("20d mean abnormal return")
    ax.set_title("Expanded Event Study: 20d Mean Abnormal Returns")
    ax.grid(True, axis="y", alpha=0.3)

    for idx, row in df.iterrows():
        ax.text(
            idx,
            row["20d_mean"],
            f"t={row['20d_t_stat']:.2f}",
            ha="center",
            va="bottom" if row["20d_mean"] >= 0 else "top",
            fontsize=9,
        )

    save_current_figure(FIGURES_DIR / "expanded_event_study_20d.png")


def plot_expanded_strategy_candidates() -> None:
    """Plot negative-event reversal candidate returns by horizon."""
    df = require_csv(STRATEGY_CANDIDATES_PATH).copy()

    required = {"strategy", "horizon", "avg_return_per_event_bps", "t_stat"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{STRATEGY_CANDIDATES_PATH} missing columns: {sorted(missing)}")

    candidate = df[df["strategy"] == "Negative Event Reversal"].copy()
    candidate["horizon_order"] = candidate["horizon"].str.replace("d", "", regex=False).astype(int)
    candidate = candidate.sort_values("horizon_order")

    fig, ax = plt.subplots(figsize=(9, 5))

    ax.bar(candidate["horizon"], candidate["avg_return_per_event_bps"])
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_xlabel("Forward horizon")
    ax.set_ylabel("Average return per event, bps")
    ax.set_title("Expanded Universe: Negative Event Reversal by Horizon")
    ax.grid(True, axis="y", alpha=0.3)

    for idx, row in enumerate(candidate.itertuples(index=False)):
        ax.text(
            idx,
            row.avg_return_per_event_bps,
            f"t={row.t_stat:.2f}",
            ha="center",
            va="bottom" if row.avg_return_per_event_bps >= 0 else "top",
            fontsize=9,
        )

    save_current_figure(FIGURES_DIR / "expanded_strategy_candidates.png")


def plot_cooldown_sensitivity() -> None:
    """Plot same-ticker cooldown sensitivity."""
    df = require_csv(COOLDOWN_SENSITIVITY_PATH).copy()

    required = {
        "cooldown_days",
        "annualized_abnormal_sharpe",
        "max_abnormal_drawdown",
        "avg_gross_exposure",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{COOLDOWN_SENSITIVITY_PATH} missing columns: {sorted(missing)}")

    fig, ax1 = plt.subplots(figsize=(9, 5))

    ax1.plot(
        df["cooldown_days"],
        df["annualized_abnormal_sharpe"],
        marker="o",
        label="Annualized abnormal Sharpe",
    )
    ax1.set_xlabel("Same-ticker cooldown, calendar days")
    ax1.set_ylabel("Annualized abnormal Sharpe")
    ax1.set_title("Same-Ticker Cooldown Sensitivity")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(
        df["cooldown_days"],
        df["max_abnormal_drawdown"],
        marker="s",
        linestyle="--",
        label="Max abnormal drawdown",
    )
    ax2.set_ylabel("Max abnormal drawdown")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="best")

    save_current_figure(FIGURES_DIR / "cooldown_sensitivity.png")


def plot_global_pacing_sensitivity() -> None:
    """Plot global pacing sensitivity."""
    df = require_csv(GLOBAL_PACING_SENSITIVITY_PATH).copy()

    required = {
        "min_days_between_new_trades",
        "annualized_abnormal_sharpe",
        "max_abnormal_drawdown",
        "avg_gross_exposure",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{GLOBAL_PACING_SENSITIVITY_PATH} missing columns: {sorted(missing)}"
        )

    fig, ax1 = plt.subplots(figsize=(9, 5))

    ax1.plot(
        df["min_days_between_new_trades"],
        df["annualized_abnormal_sharpe"],
        marker="o",
        label="Annualized abnormal Sharpe",
    )
    ax1.set_xlabel("Minimum calendar days between new trades")
    ax1.set_ylabel("Annualized abnormal Sharpe")
    ax1.set_title("Global Pacing Sensitivity")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(
        df["min_days_between_new_trades"],
        df["avg_gross_exposure"],
        marker="s",
        linestyle="--",
        label="Average gross exposure",
    )
    ax2.set_ylabel("Average gross exposure")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="best")

    save_current_figure(FIGURES_DIR / "global_pacing_sensitivity.png")


def plot_expanded_backtest_summary() -> None:
    """Plot key expanded abnormal backtest metrics."""
    df = require_csv(ABNORMAL_BACKTEST_SUMMARY_PATH).copy()

    required = {
        "total_abnormal_return",
        "annualized_abnormal_sharpe",
        "max_abnormal_drawdown",
        "avg_gross_exposure",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{ABNORMAL_BACKTEST_SUMMARY_PATH} missing columns: {sorted(missing)}"
        )

    row = df.iloc[0]

    metrics = pd.DataFrame(
        {
            "metric": [
                "Total abnormal return",
                "Annualized abnormal Sharpe",
                "Max abnormal drawdown",
                "Average gross exposure",
            ],
            "value": [
                row["total_abnormal_return"],
                row["annualized_abnormal_sharpe"],
                row["max_abnormal_drawdown"],
                row["avg_gross_exposure"],
            ],
        }
    )

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.bar(metrics["metric"], metrics["value"])
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_xlabel("Metric")
    ax.set_ylabel("Value")
    ax.set_title("Expanded Universe Abnormal Backtest Summary")
    ax.grid(True, axis="y", alpha=0.3)

    plt.xticks(rotation=20, ha="right")

    save_current_figure(FIGURES_DIR / "expanded_backtest_summary.png")


def run_expanded_figures() -> None:
    """Generate expanded-universe project figures."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    plot_expanded_event_study_20d()
    plot_expanded_strategy_candidates()
    plot_cooldown_sensitivity()
    plot_global_pacing_sensitivity()
    plot_expanded_backtest_summary()

    print(f"Saved expanded figures to: {FIGURES_DIR}")
    print()
    print("Generated expanded figures:")
    for path in sorted(FIGURES_DIR.glob("expanded_*.png")):
        print(f"- {path}")

    for path in [
        FIGURES_DIR / "cooldown_sensitivity.png",
        FIGURES_DIR / "global_pacing_sensitivity.png",
    ]:
        if path.exists():
            print(f"- {path}")


if __name__ == "__main__":
    run_expanded_figures()