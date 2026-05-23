from __future__ import annotations

from pathlib import Path

import pandas as pd
from alphalens.utils import get_clean_factor_and_forward_returns

from zer0factor.eval.alphalens_adapter import (
    build_price_matrix,
    factor_long_to_alphalens_series,
    filter_factor_by_universe,
)
from zer0factor.eval.artifacts import (
    create_run_directory,
    write_factor_artifacts,
    write_run_summary,
)
from zer0factor.eval.config import (
    EvaluationConfig,
    EvaluationRunResult,
    FactorEvaluationResult,
)
from zer0factor.eval.loaders import (
    load_price_data,
    load_stored_factor,
    load_universe_panel,
)
from zer0factor.eval.metrics import (
    build_summary,
    calculate_daily_ic,
    calculate_quantile_returns,
)
from zer0factor.eval.plots import (
    plot_cumulative_ic,
    plot_quantile_returns,
    plot_rolling_ic,
)


def evaluate_factor(
    *,
    factor_name: str,
    storage,
    pro,
    config: EvaluationConfig,
    run_dir: str | Path,
    price_data: pd.DataFrame | None = None,
    universe_panel: pd.DataFrame | None = None,
) -> FactorEvaluationResult:
    factor_data = load_stored_factor(
        storage,
        factor_name,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    factor = factor_long_to_alphalens_series(factor_data)
    factor = filter_factor_by_universe(factor, universe_panel)

    if price_data is None:
        price_data = load_price_data(
            pro,
            start_date=config.start_date,
            end_date=config.end_date,
            periods=config.periods,
        )
    prices = build_price_matrix(price_data, config.return_type)

    clean_factor_data = get_clean_factor_and_forward_returns(
        factor,
        prices,
        quantiles=config.quantiles,
        periods=config.periods,
        max_loss=config.max_loss,
    )
    daily_ic = calculate_daily_ic(clean_factor_data)
    quantile_returns = calculate_quantile_returns(clean_factor_data)
    summary = build_summary(
        factor_name=factor_name,
        return_type=config.return_type,
        clean_factor_data_sample_count=len(clean_factor_data),
        clean_factor_data_start=clean_factor_data.index.get_level_values("date").min(),
        clean_factor_data_end=clean_factor_data.index.get_level_values("date").max(),
        quantiles=config.quantiles,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    factor_dir = Path(run_dir) / "factors" / factor_name
    write_factor_artifacts(
        factor_dir=factor_dir,
        clean_factor_data=clean_factor_data,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )
    figure_paths = _write_factor_figures(
        factor_dir=factor_dir,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        rolling_ic_window=config.rolling_ic_window,
    )

    return FactorEvaluationResult(
        factor_name=factor_name,
        clean_factor_data=clean_factor_data,
        summary=summary,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        figure_paths=figure_paths,
        output_dir=factor_dir,
    )


def evaluate_factors(
    *,
    factor_names: tuple[str, ...] | list[str],
    storage,
    pro,
    config: EvaluationConfig,
    run_id: str | None = None,
) -> EvaluationRunResult:
    resolved_config = EvaluationConfig(
        factor_names=tuple(factor_names),
        start_date=config.start_date,
        end_date=config.end_date,
        periods=config.periods,
        quantiles=config.quantiles,
        return_type=config.return_type,
        max_loss=config.max_loss,
        universe=config.universe,
        output_dir=config.output_dir,
        rolling_ic_window=config.rolling_ic_window,
    )
    run_id, run_dir = create_run_directory(resolved_config, run_id=run_id)
    price_data = load_price_data(
        pro,
        start_date=resolved_config.start_date,
        end_date=resolved_config.end_date,
        periods=resolved_config.periods,
    )
    universe_panel = load_universe_panel(
        pro,
        universe_name=resolved_config.universe,
        start_date=resolved_config.start_date,
        end_date=resolved_config.end_date,
    )

    factor_results = tuple(
        evaluate_factor(
            factor_name=factor_name,
            storage=storage,
            pro=pro,
            config=resolved_config,
            run_dir=run_dir,
            price_data=price_data,
            universe_panel=universe_panel,
        )
        for factor_name in resolved_config.factor_names
    )
    summary = pd.concat(
        [factor_result.summary for factor_result in factor_results],
        ignore_index=True,
    )
    run_paths = write_run_summary(
        run_dir=run_dir,
        summary=summary,
        config=resolved_config,
        run_id=run_id,
    )

    return EvaluationRunResult(
        run_id=run_id,
        output_dir=run_dir,
        factor_results=factor_results,
        summary=summary,
        metadata_path=run_paths["metadata"],
    )


def _write_factor_figures(
    *,
    factor_dir: Path,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
    rolling_ic_window: int,
) -> tuple[Path, ...]:
    figures_dir = factor_dir / "figures"
    first_period = str(quantile_returns.columns[0])
    return (
        plot_quantile_returns(
            quantile_returns,
            period=first_period,
            output_path=figures_dir / f"quantile_returns_{first_period}.png",
        ),
        plot_cumulative_ic(
            daily_ic,
            output_path=figures_dir / "cumulative_ic.png",
        ),
        plot_rolling_ic(
            daily_ic,
            window=rolling_ic_window,
            output_path=figures_dir / f"rolling_ic_{rolling_ic_window}.png",
        ),
    )
