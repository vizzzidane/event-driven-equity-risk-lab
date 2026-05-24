from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


RESULTS_DIR = Path("results")
FIGURES_DIR = RESULTS_DIR / "figures"

HOLDING_PERIOD_PATH = RESULTS_DIR / "holding_period_sensitivity.csv"
COST_SENSITIVITY_PATH = RESULTS_DIR / "cost_sensitivity.csv"
THRESHOLD_SENSITIVITY_PATH = RESULTS_DIR / "threshold_sensitivity.csv"
WF_OPT_SUMMARY_PATH = RESULTS_DIR / "walk_forward_optimized_summary.csv"
WF_OPT_PORTFOLIO_PATH = RESULTS_DIR / "walk_forward_optimized_portfolio_returns.csv"
WF_OPT_PARAM_SELECTION_PATH = RESULTS_DIR / "walk_forward_optimized_param_selection.csv"


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


def plot_holding_period_sensitivity() -> None:
    """Plot Sharpe and total abnormal return by holding period."""
    df = require_csv(HOLDING_PERIOD_PATH)

    fig, ax1 = plt.subplots(figsize=(9, 5))

    ax1.plot(
        df["hold_days"],
        df["annualized_abnormal_sharpe"],
        marker="o",
        label="Annualized abnormal Sharpe",
    )
    ax1.set_xlabel("Holding period, trading days")
    ax1.set_ylabel("Annualized abnormal Sharpe")
    ax1.set_title("Holding Period Sensitivity")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(
        df["hold_days"],
        df["total_abnormal_return"],
        marker="s",
        linestyle="--",
        label="Total abnormal return",
    )
    ax2.set_ylabel("Total abnormal return")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="best")

    save_current_figure(FIGURES_DIR / "holding_period_sensitivity.png")


def plot_cost_sensitivity() -> None:
    """Plot Sharpe and total abnormal return by transaction cost."""
    df = require_csv(COST_SENSITIVITY_PATH)

    fig, ax1 = plt.subplots(figsize=(9, 5))

    ax1.plot(
        df["transaction_cost_bps_per_side"],
        df["annualized_abnormal_sharpe"],
        marker="o",
        label="Annualized abnormal Sharpe",
    )
    ax1.axhline(0, linestyle="--", linewidth=1)
    ax1.set_xlabel("Transaction cost, bps per side")
    ax1.set_ylabel("Annualized abnormal Sharpe")
    ax1.set_title("Transaction Cost Sensitivity")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(
        df["transaction_cost_bps_per_side"],
        df["total_abnormal_return"],
        marker="s",
        linestyle="--",
        label="Total abnormal return",
    )
    ax2.set_ylabel("Total abnormal return")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="best")

    save_current_figure(FIGURES_DIR / "cost_sensitivity.png")


def plot_threshold_sensitivity() -> None:
    """Plot threshold sensitivity by parameter setting."""
    df = require_csv(THRESHOLD_SENSITIVITY_PATH).copy()

    df["setting"] = (
        "S" + df["event_strength_threshold"].astype(str)
        + " / V" + df["volume_shock_threshold"].astype(str)
    )

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.bar(df["setting"], df["annualized_abnormal_sharpe"])
    ax.set_xlabel("Event strength / volume shock threshold")
    ax.set_ylabel("Annualized abnormal Sharpe")
    ax.set_title("Threshold Sensitivity")
    ax.grid(True, axis="y", alpha=0.3)

    save_current_figure(FIGURES_DIR / "threshold_sensitivity.png")


def plot_optimized_walk_forward_returns() -> None:
    """Plot optimized walk-forward yearly abnormal returns."""
    df = require_csv(WF_OPT_SUMMARY_PATH).copy()
    df = df[df["test_year"].astype(str).str.startswith("FULL") == False].copy()

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.bar(df["test_year"].astype(str), df["year_abnormal_return"])
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_xlabel("Test year")
    ax.set_ylabel("Year abnormal return")
    ax.set_title("Optimized Walk-Forward Yearly Abnormal Returns")
    ax.grid(True, axis="y", alpha=0.3)

    save_current_figure(FIGURES_DIR / "optimized_walk_forward_returns.png")


def plot_optimized_equity_curve() -> None:
    """Plot optimized walk-forward abnormal equity curve."""
    df = require_csv(WF_OPT_PORTFOLIO_PATH)
    df["date"] = pd.to_datetime(df["date"])

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(df["date"], df["abnormal_equity_curve"])
    ax.set_xlabel("Date")
    ax.set_ylabel("Abnormal equity curve")
    ax.set_title("Optimized Walk-Forward Abnormal Equity Curve")
    ax.grid(True, alpha=0.3)

    save_current_figure(FIGURES_DIR / "optimized_equity_curve.png")


def plot_optimized_drawdown() -> None:
    """Plot optimized walk-forward drawdown."""
    df = require_csv(WF_OPT_PORTFOLIO_PATH)
    df["date"] = pd.to_datetime(df["date"])

    df["running_peak"] = df["abnormal_equity_curve"].cummax()
    df["drawdown"] = df["abnormal_equity_curve"] / df["running_peak"] - 1

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(df["date"], df["drawdown"])
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.set_title("Optimized Walk-Forward Drawdown")
    ax.grid(True, alpha=0.3)

    save_current_figure(FIGURES_DIR / "optimized_drawdown.png")


def plot_parameter_selection() -> None:
    """Plot parameter choices across optimized walk-forward years."""
    df = require_csv(WF_OPT_PARAM_SELECTION_PATH)

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        df["test_year"],
        df["event_strength_threshold"],
        marker="o",
        label="Event strength threshold",
    )
    ax.plot(
        df["test_year"],
        df["volume_shock_threshold"],
        marker="s",
        label="Volume shock threshold",
    )
    ax.plot(
        df["test_year"],
        df["hold_days"] / 10,
        marker="^",
        label="Hold days / 10",
    )

    ax.set_xlabel("Test year")
    ax.set_ylabel("Selected parameter value")
    ax.set_title("Optimized Walk-Forward Parameter Selection")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")

    save_current_figure(FIGURES_DIR / "optimized_parameter_selection.png")


def run_figures() -> None:
    """Generate all project figures."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    plot_holding_period_sensitivity()
    plot_cost_sensitivity()
    plot_threshold_sensitivity()
    plot_optimized_walk_forward_returns()
    plot_optimized_equity_curve()
    plot_optimized_drawdown()
    plot_parameter_selection()

    print(f"Saved figures to: {FIGURES_DIR}")
    print()
    print("Generated figures:")
    for path in sorted(FIGURES_DIR.glob("*.png")):
        print(f"- {path}")


if __name__ == "__main__":
    run_figures()