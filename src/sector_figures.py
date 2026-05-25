from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


SECTOR_ATTRIBUTION_PATH = Path(
    "results/sector_attribution.csv"
)

FIGURES_DIR = Path(
    "results/figures"
)

SECTOR_TOTAL_RETURN_FIGURE = Path(
    "results/figures/sector_total_return.png"
)

SECTOR_WIN_RATE_FIGURE = Path(
    "results/figures/sector_win_rate.png"
)

DOCS_FIGURES_DIR = Path(
    "docs/figures"
)


def load_sector_attribution() -> pd.DataFrame:
    """Load sector attribution results."""
    if not SECTOR_ATTRIBUTION_PATH.exists():
        raise FileNotFoundError(
            f"Missing sector attribution file: "
            f"{SECTOR_ATTRIBUTION_PATH}"
        )

    return pd.read_csv(SECTOR_ATTRIBUTION_PATH)


def create_total_return_figure(
    attribution: pd.DataFrame,
) -> None:
    """Create sector total-return figure."""
    sorted_df = attribution.sort_values(
        "total_return",
        ascending=False,
    )

    plt.figure(figsize=(12, 6))

    plt.bar(
        sorted_df["sector"],
        sorted_df["total_return"],
    )

    plt.xticks(rotation=30, ha="right")

    plt.ylabel("Total Net Abnormal Return")

    plt.title(
        "Sector Attribution: Total Net Abnormal Return"
    )

    plt.tight_layout()

    plt.savefig(
        SECTOR_TOTAL_RETURN_FIGURE,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()


def create_win_rate_figure(
    attribution: pd.DataFrame,
) -> None:
    """Create sector win-rate figure."""
    sorted_df = attribution.sort_values(
        "win_rate",
        ascending=False,
    )

    plt.figure(figsize=(12, 6))

    plt.bar(
        sorted_df["sector"],
        sorted_df["win_rate"],
    )

    plt.xticks(rotation=30, ha="right")

    plt.ylabel("Win Rate")

    plt.title(
        "Sector Attribution: Trade Win Rate"
    )

    plt.tight_layout()

    plt.savefig(
        SECTOR_WIN_RATE_FIGURE,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()


def copy_figures_to_docs() -> None:
    """Copy figures into docs directory."""
    DOCS_FIGURES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for figure_path in [
        SECTOR_TOTAL_RETURN_FIGURE,
        SECTOR_WIN_RATE_FIGURE,
    ]:
        destination = (
            DOCS_FIGURES_DIR / figure_path.name
        )

        destination.write_bytes(
            figure_path.read_bytes()
        )


def main() -> None:
    attribution = load_sector_attribution()

    FIGURES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    create_total_return_figure(attribution)

    create_win_rate_figure(attribution)

    copy_figures_to_docs()

    print()
    print("Generated figures:")
    print(f"- {SECTOR_TOTAL_RETURN_FIGURE}")
    print(f"- {SECTOR_WIN_RATE_FIGURE}")

    print()
    print("Copied figures into docs/figures")


if __name__ == "__main__":
    main()