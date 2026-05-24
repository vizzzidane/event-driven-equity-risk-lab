from __future__ import annotations

from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("results")

EVENT_SUMMARY_PATH = RESULTS_DIR / "event_summary.csv"
MATCHED_PLACEBO_DIFF_PATH = RESULTS_DIR / "matched_placebo_differences.csv"
COST_SENSITIVITY_PATH = RESULTS_DIR / "cost_sensitivity.csv"
HOLDING_PERIOD_SENSITIVITY_PATH = RESULTS_DIR / "holding_period_sensitivity.csv"
THRESHOLD_SENSITIVITY_PATH = RESULTS_DIR / "threshold_sensitivity.csv"
RISK_FILTER_ANALYSIS_PATH = RESULTS_DIR / "risk_filter_analysis.csv"
WALK_FORWARD_SUMMARY_PATH = RESULTS_DIR / "walk_forward_summary.csv"
WF_OPT_SUMMARY_PATH = RESULTS_DIR / "walk_forward_optimized_summary.csv"
WF_OPT_PARAM_SELECTION_PATH = RESULTS_DIR / "walk_forward_optimized_param_selection.csv"
BACKTEST_VALIDATION_BY_TICKER_PATH = RESULTS_DIR / "backtest_validation_by_ticker.csv"
BACKTEST_VALIDATION_BY_YEAR_PATH = RESULTS_DIR / "backtest_validation_by_year.csv"

FINAL_RESEARCH_SUMMARY_PATH = RESULTS_DIR / "final_research_summary.csv"
FINAL_README_NOTES_PATH = RESULTS_DIR / "final_readme_notes.md"


def require_csv(path: Path) -> pd.DataFrame:
    """Load a required CSV result file."""
    if not path.exists():
        raise FileNotFoundError(
            f"Missing required result file: {path}. "
            "Run the earlier analysis/backtest scripts first."
        )

    return pd.read_csv(path)


def pct(value: float) -> str:
    """Format decimal return as percentage string."""
    if pd.isna(value):
        return "NA"
    return f"{value:.2%}"


def bps(value: float) -> str:
    """Format decimal return as basis points."""
    if pd.isna(value):
        return "NA"
    return f"{value * 10_000:.1f} bps"


def num(value: float) -> str:
    """Format decimal number."""
    if pd.isna(value):
        return "NA"
    return f"{value:.2f}"


def build_key_findings() -> pd.DataFrame:
    """Build consolidated key findings table."""
    event_summary = require_csv(EVENT_SUMMARY_PATH)
    matched_diff = require_csv(MATCHED_PLACEBO_DIFF_PATH)
    cost = require_csv(COST_SENSITIVITY_PATH)
    holding = require_csv(HOLDING_PERIOD_SENSITIVITY_PATH)
    threshold = require_csv(THRESHOLD_SENSITIVITY_PATH)
    risk_filters = require_csv(RISK_FILTER_ANALYSIS_PATH)
    wf_fixed = require_csv(WALK_FORWARD_SUMMARY_PATH)
    wf_opt = require_csv(WF_OPT_SUMMARY_PATH)
    ticker_validation = require_csv(BACKTEST_VALIDATION_BY_TICKER_PATH)
    year_validation = require_csv(BACKTEST_VALIDATION_BY_YEAR_PATH)

    rows: list[dict[str, str]] = []

    all_events = event_summary[event_summary["group"] == "all_events"].iloc[0]
    positive_events = event_summary[event_summary["group"] == "positive_events"].iloc[0]
    negative_events = event_summary[event_summary["group"] == "negative_events"].iloc[0]

    rows.append(
        {
            "section": "Event study",
            "finding": "All detected abnormal price-volume events showed positive 20d average abnormal returns.",
            "evidence": (
                f"n={int(all_events['n_events'])}, "
                f"20d mean={pct(all_events['20d_mean'])}, "
                f"20d t-stat={num(all_events['20d_t_stat'])}"
            ),
            "interpretation": "Raw event effect exists, but this alone does not prove alpha.",
        }
    )

    rows.append(
        {
            "section": "Event asymmetry",
            "finding": "Positive events showed 20d continuation while negative events showed 20d rebound/reversal.",
            "evidence": (
                f"positive 20d mean={pct(positive_events['20d_mean'])}; "
                f"negative 20d mean={pct(negative_events['20d_mean'])}"
            ),
            "interpretation": "The event effect is asymmetric rather than a universal drift signal.",
        }
    )

    neg_reversal_20d = matched_diff[
        (matched_diff["strategy"] == "Negative Event Reversal")
        & (matched_diff["horizon"] == "20d")
    ].iloc[0]

    rows.append(
        {
            "section": "Matched placebo",
            "finding": "Negative-event reversal beat same-stock, same-year matched non-event baselines.",
            "evidence": (
                f"real={pct(neg_reversal_20d['mean_return_real'])}, "
                f"placebo={pct(neg_reversal_20d['mean_return_placebo'])}, "
                f"difference={bps(neg_reversal_20d['mean_return_diff'])}"
            ),
            "interpretation": "The negative-event reversal effect appears stronger than a matched non-event baseline.",
        }
    )

    best_hold = holding.sort_values("annualized_abnormal_sharpe", ascending=False).iloc[0]

    rows.append(
        {
            "section": "Holding-period sensitivity",
            "finding": "The 30-trading-day holding window produced the strongest risk-adjusted result.",
            "evidence": (
                f"hold={int(best_hold['hold_days'])}d, "
                f"avg trade={pct(best_hold['avg_trade_net_abnormal_return'])}, "
                f"Sharpe={num(best_hold['annualized_abnormal_sharpe'])}, "
                f"max DD={pct(best_hold['max_abnormal_drawdown'])}"
            ),
            "interpretation": "The reversal effect appears medium-term rather than a quick 5-day bounce.",
        }
    )

    best_threshold = threshold.sort_values("annualized_abnormal_sharpe", ascending=False).iloc[0]

    rows.append(
        {
            "section": "Threshold sensitivity",
            "finding": "The balanced threshold setting performed best.",
            "evidence": (
                f"event_strength<={-best_threshold['event_strength_threshold']:.1f}, "
                f"volume_shock>={best_threshold['volume_shock_threshold']:.1f}, "
                f"Sharpe={num(best_threshold['annualized_abnormal_sharpe'])}, "
                f"total abnormal return={pct(best_threshold['total_abnormal_return'])}"
            ),
            "interpretation": "Too-loose events dilute the signal, while too-extreme events may represent genuine repricing.",
        }
    )

    base_cost = cost[cost["transaction_cost_bps_per_side"] == 5.0].iloc[0]
    high_cost = cost[cost["transaction_cost_bps_per_side"] == 50.0].iloc[0]

    rows.append(
        {
            "section": "Cost sensitivity",
            "finding": "The strategy survived moderate costs but failed under very high slippage.",
            "evidence": (
                f"5 bps/side Sharpe={num(base_cost['annualized_abnormal_sharpe'])}, "
                f"50 bps/side Sharpe={num(high_cost['annualized_abnormal_sharpe'])}"
            ),
            "interpretation": "The edge is not purely frictionless, but it is not large enough for very high-cost execution.",
        }
    )

    baseline_filter = risk_filters[risk_filters["filter_name"] == "baseline"].iloc[0]
    best_filter = risk_filters.sort_values("annualized_abnormal_sharpe", ascending=False).iloc[0]

    rows.append(
        {
            "section": "Risk filters",
            "finding": "Simple risk filters did not clearly beat the baseline.",
            "evidence": (
                f"baseline Sharpe={num(baseline_filter['annualized_abnormal_sharpe'])}, "
                f"best filter={best_filter['filter_name']}, "
                f"best Sharpe={num(best_filter['annualized_abnormal_sharpe'])}"
            ),
            "interpretation": "Avoid overfitting. Current baseline remains the cleanest rule.",
        }
    )

    fixed_full = wf_fixed[wf_fixed["test_year"] == "FULL_2016_2025"].iloc[0]

    rows.append(
        {
            "section": "Fixed walk-forward",
            "finding": "The fixed-rule strategy was positive across yearly test slices from 2016 to 2025.",
            "evidence": (
                f"full return={pct(fixed_full['year_abnormal_return'])}, "
                f"Sharpe={num(fixed_full['annualized_abnormal_sharpe'])}, "
                f"max DD={pct(fixed_full['max_abnormal_drawdown'])}, "
                f"n_trades={int(fixed_full['n_trades'])}"
            ),
            "interpretation": "The result is not obviously driven by a single lucky full-period backtest.",
        }
    )

    opt_full = wf_opt[wf_opt["test_year"] == "FULL_2018_2025"].iloc[0]

    rows.append(
        {
            "section": "Optimized walk-forward",
            "finding": "Train-selected parameters remained profitable out of sample from 2018 to 2025.",
            "evidence": (
                f"full return={pct(opt_full['year_abnormal_return'])}, "
                f"Sharpe={num(opt_full['annualized_abnormal_sharpe'])}, "
                f"max DD={pct(opt_full['max_abnormal_drawdown'])}, "
                f"n_trades={int(opt_full['n_trades'])}"
            ),
            "interpretation": "This is the strongest current evidence that the strategy is not purely in-sample overfit.",
        }
    )

    best_ticker = ticker_validation.sort_values("total_trade_return_sum", ascending=False).iloc[0]
    worst_ticker = ticker_validation.sort_values("total_trade_return_sum", ascending=True).iloc[0]

    rows.append(
        {
            "section": "Ticker concentration",
            "finding": "Performance is uneven across names.",
            "evidence": (
                f"best ticker={best_ticker['ticker']} "
                f"sum={pct(best_ticker['total_trade_return_sum'])}; "
                f"worst ticker={worst_ticker['ticker']} "
                f"sum={pct(worst_ticker['total_trade_return_sum'])}"
            ),
            "interpretation": "The strategy should be presented with ticker-level heterogeneity, not as a universal stock effect.",
        }
    )

    weak_year = year_validation.sort_values("total_trade_return_sum", ascending=True).iloc[0]
    strong_year = year_validation.sort_values("total_trade_return_sum", ascending=False).iloc[0]

    rows.append(
        {
            "section": "Year concentration",
            "finding": "Performance is weaker during some repricing/stress years.",
            "evidence": (
                f"weakest year={int(weak_year['entry_year'])} "
                f"sum={pct(weak_year['total_trade_return_sum'])}; "
                f"strongest year={int(strong_year['entry_year'])} "
                f"sum={pct(strong_year['total_trade_return_sum'])}"
            ),
            "interpretation": "Failure modes should discuss periods where negative events are genuine repricing, not temporary overreaction.",
        }
    )

    return pd.DataFrame(rows)


def build_readme_notes(summary: pd.DataFrame) -> str:
    """Build markdown notes for README drafting."""
    lines = [
        "# Final Research Notes",
        "",
        "## Current Core Finding",
        "",
        (
            "Negative abnormal price-volume events show a medium-term reversal effect. "
            "The strongest current strategy buys after negative abnormal price-volume events "
            "and holds for around 30 trading days."
        ),
        "",
        "## Key Evidence",
        "",
    ]

    for _, row in summary.iterrows():
        lines.append(f"### {row['section']}")
        lines.append("")
        lines.append(f"- **Finding:** {row['finding']}")
        lines.append(f"- **Evidence:** {row['evidence']}")
        lines.append(f"- **Interpretation:** {row['interpretation']}")
        lines.append("")

    lines.extend(
        [
            "## Current Best Strategy Candidate",
            "",
            "- Strategy: Negative Event Reversal",
            "- Event rule: event_strength <= -2.0 and volume_shock >= 1.2",
            "- Holding period: 30 trading days",
            "- Return stream: abnormal return = stock return - SPY return",
            "- Transaction costs: 5 bps per side",
            "- Positioning: event-driven equity research, not broad market regime allocation",
            "",
            "## Important Limitations",
            "",
            "- Universe is still small: 10 large-cap stocks.",
            "- Event definition is based on price/volume shocks, not yet actual earnings dates.",
            "- Strategy is active most of the time, so exposure control still needs refinement.",
            "- Results are heterogeneous across tickers and years.",
            "- Further testing is needed on a larger universe and with richer event data.",
            "",
            "## Next Research Steps",
            "",
            "1. Expand universe beyond 10 stocks.",
            "2. Add actual earnings dates and earnings surprise data.",
            "3. Add sector controls and sector-neutral attribution.",
            "4. Build charts for event-study CAR, equity curves, drawdowns, and walk-forward results.",
            "5. Add unit tests for event detection, abnormal returns, costs, and portfolio constraints.",
            "6. Write final README in research-report style.",
            "",
        ]
    )

    return "\n".join(lines)


def run_final_summary() -> None:
    """Build final consolidated research summary."""
    summary = build_key_findings()

    FINAL_RESEARCH_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    summary.to_csv(FINAL_RESEARCH_SUMMARY_PATH, index=False)

    notes = build_readme_notes(summary)
    FINAL_README_NOTES_PATH.write_text(notes, encoding="utf-8")

    print(f"Saved final research summary to: {FINAL_RESEARCH_SUMMARY_PATH}")
    print(f"Saved final README notes to: {FINAL_README_NOTES_PATH}")

    print()
    print("Final research summary")
    print("----------------------")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    run_final_summary()