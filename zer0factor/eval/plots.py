from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def plot_quantile_returns(
    quantile_returns: pd.DataFrame, *, period: str, output_path: str | Path
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    try:
        quantile_returns[period].plot(kind="bar", ax=ax)
        ax.set_xlabel("Quantile")
        ax.set_ylabel("Mean Return")
        ax.set_title(f"Quantile Returns ({period})")
        fig.tight_layout()
        fig.savefig(output_path)
    finally:
        plt.close(fig)
    return output_path


def plot_cumulative_ic(daily_ic: pd.DataFrame, *, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    try:
        daily_ic.cumsum().plot(ax=ax)
        ax.set_xlabel("Date")
        ax.set_ylabel("Cumulative IC")
        ax.set_title("Cumulative Information Coefficient")
        fig.tight_layout()
        fig.savefig(output_path)
    finally:
        plt.close(fig)
    return output_path


def plot_rolling_ic(
    daily_ic: pd.DataFrame, *, window: int, output_path: str | Path
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    try:
        daily_ic.rolling(window=window).mean().plot(ax=ax)
        ax.set_xlabel("Date")
        ax.set_ylabel("Rolling IC")
        ax.set_title(f"Rolling Information Coefficient ({window})")
        fig.tight_layout()
        fig.savefig(output_path)
    finally:
        plt.close(fig)
    return output_path
