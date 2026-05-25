from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
DOCS_FIGURES_DIR = BASE_DIR / "docs" / "figures"

SUMMARY_PATH = RESULTS_DIR / "walk_forward_expanded_paced_summary.csv"
RETURNS_PATH = RESULTS_DIR / "walk_forward_expanded_paced_portfolio_returns.csv"

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
DOCS_FIGURES_DIR.mkdir(parents=True, exist_ok=True)


plt.style.use("ggplot")


SUMMARY_OUTPUT = FIGURES_DIR / "expanded_paced_yearly_returns.png"
EQUITY_OUTPUT = FIGURES_DIR / "expanded_paced_equity_curve.png"
DRAWDOWN_OUTPUT = FIGURES_DIR / "expanded_paced_drawdown.png"


DOCS_SUMMARY_OUTPUT = DOCS_FIGURES_DIR / "expanded_paced_yearly_returns.png"
DOCS_EQUITY_OUTPUT = DOCS_FIGURES_DIR / "expanded_paced_equity_curve.png"
DOCS_DRAWDOWN_OUTPUT = DOCS_FIGURES_DIR / "expanded_paced_drawdown.png"


SUMMARY_RETURN_COLUMN_CANDIDATES = [
    "period_abnormal_return",
    "abnormal_return",
    "annual_abnormal_return",
    "yearly_abnormal_return",
    "return",
    "portfolio_return",
]

RETURNS_COLUMN_CANDIDATES = [
    "net_portfolio_abnormal_return",
    "portfolio_abnormal_return",
    "portfolio_return",
    "abnormal_return",
    "daily_return",
    "strategy_return",
    "return",
]

DATE_COLUMN_CANDIDATES = [
    "date",
    "Date",
    "timestamp",
]

YEAR_COLUMN_CANDIDATES = [
    "test_period",
    "year",
    "Year",
]


def find_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for column in candidates:
        if column in df.columns:
            return column

    raise ValueError(
        f"Could not find any matching column. Tried: {candidates}. Available columns: {list(df.columns)}"
    )


summary_df = pd.read_csv(SUMMARY_PATH)
returns_df = pd.read_csv(RETURNS_PATH)


summary_return_col = find_column(summary_df, SUMMARY_RETURN_COLUMN_CANDIDATES)
year_col = find_column(summary_df, YEAR_COLUMN_CANDIDATES)

returns_col = find_column(returns_df, RETURNS_COLUMN_CANDIDATES)
date_col = find_column(returns_df, DATE_COLUMN_CANDIDATES)


returns_df[date_col] = pd.to_datetime(returns_df[date_col])
returns_df = returns_df.sort_values(date_col).reset_index(drop=True)


# Convert percentage-style returns if needed
if returns_df[returns_col].abs().max() > 5:
    returns_df[returns_col] = returns_df[returns_col] / 100

if summary_df[summary_return_col].abs().max() > 5:
    summary_df[summary_return_col] = summary_df[summary_return_col] / 100


# Equity curve
returns_df["equity_curve"] = (1 + returns_df[returns_col]).cumprod()

plt.figure(figsize=(12, 6))
plt.plot(
    returns_df[date_col],
    returns_df["equity_curve"],
    linewidth=2,
)
plt.title("Expanded Global-Paced Walk-Forward Equity Curve")
plt.xlabel("Date")
plt.ylabel("Cumulative Growth")
plt.tight_layout()
plt.savefig(EQUITY_OUTPUT, dpi=300)
plt.close()


# Drawdown
rolling_peak = returns_df["equity_curve"].cummax()
returns_df["drawdown"] = (
    returns_df["equity_curve"] - rolling_peak
) / rolling_peak

plt.figure(figsize=(12, 6))
plt.plot(
    returns_df[date_col],
    returns_df["drawdown"] * 100,
    linewidth=2,
)
plt.title("Expanded Global-Paced Walk-Forward Drawdown")
plt.xlabel("Date")
plt.ylabel("Drawdown (%)")
plt.tight_layout()
plt.savefig(DRAWDOWN_OUTPUT, dpi=300)
plt.close()


# Yearly returns
summary_df = summary_df[
    ~summary_df[year_col].astype(str).str.contains(
        "FULL",
        case=False,
    )
]

summary_df = summary_df.sort_values(year_col)

plt.figure(figsize=(12, 6))
plt.bar(
    summary_df[year_col].astype(str),
    summary_df[summary_return_col] * 100,
)
plt.axhline(0, linewidth=1)
plt.title("Expanded Global-Paced Walk-Forward Yearly Returns")
plt.xlabel("Year")
plt.ylabel("Abnormal Return (%)")
plt.tight_layout()
plt.savefig(SUMMARY_OUTPUT, dpi=300)
plt.close()


# Copy outputs into docs/figures
for source, destination in [
    (SUMMARY_OUTPUT, DOCS_SUMMARY_OUTPUT),
    (EQUITY_OUTPUT, DOCS_EQUITY_OUTPUT),
    (DRAWDOWN_OUTPUT, DOCS_DRAWDOWN_OUTPUT),
]:
    destination.write_bytes(source.read_bytes())


print("Generated figures:")
print(f"- {EQUITY_OUTPUT}")
print(f"- {SUMMARY_OUTPUT}")
print(f"- {DRAWDOWN_OUTPUT}")
print()
print("Copied figures into docs/figures")
