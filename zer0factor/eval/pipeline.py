from __future__ import annotations

import io
import warnings
from collections.abc import Callable
from contextlib import contextmanager, redirect_stdout
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
    load_index_daily,
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
    log_info: Callable[[str], None] | None = None,
) -> FactorEvaluationResult:
    if factor_name not in config.factor_names:
        raise ValueError("factor_name must be included in config.factor_names")

    factor_data = load_stored_factor(
        storage,
        factor_name,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    if factor_data.empty:
        raise ValueError(f"{factor_name}: no factor data")
    _log(
        log_info,
        f"evaluation_factor_load_finished factor={factor_name} rows={len(factor_data)}",
    )

    factor = factor_long_to_alphalens_series(factor_data)
    factor = filter_factor_by_universe(factor, universe_panel)
    if factor.empty:
        raise ValueError(f"{factor_name}: no factor data after universe filtering")

    if price_data is None:
        price_end_date = config.end_date or _max_factor_trade_date(factor_data)
        price_data = load_price_data(
            pro,
            start_date=config.start_date,
            end_date=price_end_date,
            periods=config.periods,
        )
    prices = build_price_matrix(price_data, config.return_type)

    _log(log_info, f"evaluation_clean_factor_started factor={factor_name}")
    clean_factor_data = _get_clean_factor_and_forward_returns(
        factor,
        prices,
        quantiles=config.quantiles,
        periods=config.periods,
        max_loss=config.max_loss,
    )
    if clean_factor_data.empty:
        raise ValueError(f"{factor_name}: no clean factor data")
    _log(
        log_info,
        f"evaluation_clean_factor_finished factor={factor_name} rows={len(clean_factor_data)}",
    )

    daily_ic = calculate_daily_ic(clean_factor_data)
    quantile_returns = calculate_quantile_returns(clean_factor_data)
    if quantile_returns.empty or len(quantile_returns.columns) == 0:
        raise ValueError(f"{factor_name}: no quantile return periods")
    _log(
        log_info,
        f"evaluation_metrics_finished factor={factor_name} periods={len(quantile_returns.columns)}",
    )

    index_returns = None
    if config.benchmark_index:
        index_returns = load_index_daily(
            pro,
            ts_code=config.benchmark_index,
            start_date=config.start_date,
            end_date=config.end_date,
        )

    summary = build_summary(
        factor_name=factor_name,
        return_type=config.return_type,
        clean_factor_data_sample_count=len(clean_factor_data),
        clean_factor_data_start=clean_factor_data.index.get_level_values("date").min(),
        clean_factor_data_end=clean_factor_data.index.get_level_values("date").max(),
        quantiles=config.quantiles,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        clean_factor_data=clean_factor_data,
        index_returns=index_returns,
        period_sample_counts=_calculate_period_sample_counts(
            factor,
            prices,
            quantiles=config.quantiles,
            periods=config.periods,
            max_loss=config.max_loss,
        ),
    )

    factor_dir = Path(run_dir) / "factors" / factor_name
    write_factor_artifacts(
        factor_dir=factor_dir,
        clean_factor_data=clean_factor_data,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )
    figure_paths = _write_factor_figures(
        factor_name=factor_name,
        factor_dir=factor_dir,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        rolling_ic_window=config.rolling_ic_window,
    )
    _log(
        log_info,
        f"evaluation_artifacts_written factor={factor_name} output_dir={factor_dir}",
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
    log_info: Callable[[str], None] | None = None,
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
        benchmark_index=config.benchmark_index,
    )
    run_id, run_dir = create_run_directory(resolved_config, run_id=run_id)
    _log(
        log_info,
        "evaluation_run_started "
        f"factors={len(resolved_config.factor_names)} "
        f"start_date={resolved_config.start_date} "
        f"end_date={resolved_config.end_date or 'latest'} "
        f"periods={','.join(str(period) for period in resolved_config.periods)} "
        f"return_type={resolved_config.return_type}",
    )
    price_end_date = resolved_config.end_date or _max_stored_factor_trade_date(
        storage,
        resolved_config.factor_names,
        start_date=resolved_config.start_date,
    )
    _log(
        log_info,
        "evaluation_price_load_started "
        f"start_date={resolved_config.start_date} end_date={price_end_date}",
    )
    price_data = load_price_data(
        pro,
        start_date=resolved_config.start_date,
        end_date=price_end_date,
        periods=resolved_config.periods,
    )
    _log(log_info, f"evaluation_price_load_finished rows={len(price_data)}")
    universe_panel = load_universe_panel(
        pro,
        universe_name=resolved_config.universe,
        start_date=resolved_config.start_date,
        end_date=resolved_config.end_date,
    )

    factor_results = []
    with _suppress_known_evaluation_warnings():
        for factor_name in resolved_config.factor_names:
            _log(log_info, f"evaluation_factor_started factor={factor_name}")
            factor_results.append(
                evaluate_factor(
                    factor_name=factor_name,
                    storage=storage,
                    pro=pro,
                    config=resolved_config,
                    run_dir=run_dir,
                    price_data=price_data,
                    universe_panel=universe_panel,
                    log_info=log_info,
                )
            )
    factor_results = tuple(factor_results)
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
    _log(
        log_info,
        "evaluation_run_finished "
        f"run_id={run_id} output_dir={run_dir} factors={len(factor_results)}",
    )

    return EvaluationRunResult(
        run_id=run_id,
        output_dir=run_dir,
        factor_results=factor_results,
        summary=summary,
        metadata_path=run_paths["metadata"],
    )


def _log(log_info: Callable[[str], None] | None, message: str) -> None:
    if log_info is not None:
        log_info(message)


def _get_clean_factor_and_forward_returns(
    factor: pd.Series,
    prices: pd.DataFrame,
    *,
    quantiles: int,
    periods: tuple[int, ...],
    max_loss: float,
) -> pd.DataFrame:
    with _suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
        return get_clean_factor_and_forward_returns(
            factor,
            prices,
            quantiles=quantiles,
            periods=periods,
            max_loss=max_loss,
        )


@contextmanager
def _suppress_known_evaluation_warnings():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=(
                "The default fill_method='pad' in DataFrame.pct_change "
                "is deprecated.*"
            ),
            category=FutureWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Series.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="DataFrame.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Downcasting object dtype arrays on \\.fillna.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Non-vectorized DateOffset being applied.*",
            category=pd.errors.PerformanceWarning,
            module=r"alphalens\.utils",
        )
        yield


def _calculate_period_sample_counts(
    factor: pd.Series,
    prices: pd.DataFrame,
    *,
    quantiles: int,
    periods: tuple[int, ...],
    max_loss: float,
) -> dict[str, int]:
    counts = {}
    for period in periods:
        period_label = f"{period}D"
        clean = _get_clean_factor_and_forward_returns(
            factor,
            prices,
            quantiles=quantiles,
            periods=(period,),
            max_loss=max_loss,
        )
        counts[period_label] = int(clean[period_label].count()) if period_label in clean else 0
    return counts


def _max_stored_factor_trade_date(
    storage,
    factor_names: tuple[str, ...],
    *,
    start_date: str,
) -> str:
    max_dates = []
    for factor_name in factor_names:
        factor_data = load_stored_factor(
            storage,
            factor_name,
            start_date=start_date,
            end_date=None,
        )
        if not factor_data.empty:
            max_dates.append(_max_factor_trade_date(factor_data))
    if not max_dates:
        return start_date
    return max(max_dates)


def _max_factor_trade_date(factor_data: pd.DataFrame) -> str:
    raw_dates = factor_data["trade_date"]
    if pd.api.types.is_numeric_dtype(raw_dates):
        normalized = raw_dates.astype("Int64").astype(str)
    else:
        numeric_dates = pd.to_numeric(raw_dates, errors="coerce")
        if numeric_dates.notna().all():
            normalized = numeric_dates.astype("Int64").astype(str)
        else:
            normalized = raw_dates.astype(str)
    dates = pd.to_datetime(normalized, format="%Y%m%d")
    return dates.max().strftime("%Y%m%d")


def _write_factor_figures(
    *,
    factor_name: str,
    factor_dir: Path,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
    rolling_ic_window: int,
) -> tuple[Path, ...]:
    if quantile_returns.empty or len(quantile_returns.columns) == 0:
        raise ValueError(f"{factor_name}: no quantile return periods")

    figures_dir = factor_dir / "figures"
    quantile_return_paths = tuple(
        plot_quantile_returns(
            quantile_returns,
            period=str(period),
            output_path=figures_dir / f"quantile_returns_{period}.png",
        )
        for period in quantile_returns.columns
    )
    return quantile_return_paths + (
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
