from __future__ import annotations

from pathlib import Path

from zer0factor.eval.plots import (
    plot_cumulative_ic,
    plot_quantile_returns,
    plot_rolling_ic,
)


class FactorFigureWriter:
    def write(self, result, *, rolling_ic_window: int) -> tuple[Path, ...]:
        if result.daily_ic is None:
            raise ValueError("daily_ic is required to write figures")
        if result.quantile_returns is None:
            raise ValueError("quantile_returns is required to write figures")
        if result.quantile_returns.empty or len(result.quantile_returns.columns) == 0:
            raise ValueError(f"{result.factor_name}: no quantile return periods")
        figures_dir = result.output_dir / "figures"
        quantile_return_paths = tuple(
            plot_quantile_returns(
                result.quantile_returns,
                period=str(period),
                output_path=figures_dir / f"quantile_returns_{period}.png",
            )
            for period in result.quantile_returns.columns
        )
        return quantile_return_paths + (
            plot_cumulative_ic(
                result.daily_ic,
                output_path=figures_dir / "cumulative_ic.png",
            ),
            plot_rolling_ic(
                result.daily_ic,
                window=rolling_ic_window,
                output_path=figures_dir / f"rolling_ic_{rolling_ic_window}.png",
            ),
        )
