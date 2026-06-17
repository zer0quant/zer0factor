from __future__ import annotations

import io
import multiprocessing
import time
import warnings
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

import pandas as pd
from alphalens.utils import get_clean_factor_and_forward_returns

from zer0factor.eval.artifacts import (
    EvaluationArtifactStore,
    create_run_directory,
    write_run_summary,
)
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.config import (
    EvaluationConfig,
    EvaluationRunResult,
    FactorEvaluationResult,
)
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig
from zer0factor.eval.evaluator import EvaluationSharedData, FactorEvaluator
from zer0factor.eval.figures import FactorFigureWriter
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
from zer0factor.notify.null import NullNotifier


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
    run_config = EvaluationRunConfig(
        factor_names=config.factor_names,
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
        transaction_cost_bps=config.transaction_cost_bps,
    )
    run_dir = Path(run_dir)
    run = EvaluationRun(
        run_id=run_dir.name,
        run_dir=run_dir,
        config=run_config,
    )
    evaluator = FactorEvaluator(
        data_loader=EvaluationDataLoader(storage, pro),
        metric_calculator=_PipelineCompatibilityMetricsCalculator(),
        artifact_store=EvaluationArtifactStore(),
        figure_writer=FactorFigureWriter(),
        log_info=log_info,
    )
    result = evaluator.evaluate(
        factor_name,
        run,
        shared_data=EvaluationSharedData(
            price_data=price_data,
            universe_panel=universe_panel,
        ),
    )
    return FactorEvaluationResult(
        factor_name=result.factor_name,
        clean_factor_data=result.clean_factor_data,
        summary=result.summary,
        daily_ic=result.daily_ic,
        quantile_returns=result.quantile_returns,
        figure_paths=result.figure_paths,
        output_dir=result.output_dir,
    )


class _PipelineCompatibilityMetricsCalculator(MetricsCalculator):
    def clean_factor_and_forward_returns(
        self,
        factor: pd.Series,
        prices: pd.DataFrame,
        *,
        quantiles: int,
        periods: tuple[int, ...],
        max_loss: float,
    ) -> pd.DataFrame:
        return _get_clean_factor_and_forward_returns(
            factor,
            prices,
            quantiles=quantiles,
            periods=periods,
            max_loss=max_loss,
        )

    def calculate_daily_ic(self, clean_factor_data: pd.DataFrame) -> pd.DataFrame:
        with _suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return calculate_daily_ic(clean_factor_data)

    def calculate_quantile_returns(self, clean_factor_data: pd.DataFrame) -> pd.DataFrame:
        with _suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return calculate_quantile_returns(clean_factor_data)

    def build_factor_summary(self, **kwargs) -> pd.DataFrame:
        with _suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return build_summary(**kwargs)

    def calculate_period_sample_counts(
        self,
        factor: pd.Series,
        prices: pd.DataFrame,
        *,
        quantiles: int,
        periods: tuple[int, ...],
        max_loss: float,
    ) -> dict[str, int]:
        return _calculate_period_sample_counts(
            factor,
            prices,
            quantiles=quantiles,
            periods=periods,
            max_loss=max_loss,
        )


def evaluate_factors(
    *,
    factor_names: tuple[str, ...] | list[str],
    storage,
    pro,
    config: EvaluationConfig,
    run_id: str | None = None,
    log_info: Callable[[str], None] | None = None,
    workers: int = 1,
    notifier: NullNotifier | None = None,
) -> EvaluationRunResult:
    """Evaluate stored factors and write run artifacts.

    With ``workers > 1`` factors are evaluated in parallel spawn processes;
    ``storage`` and ``pro`` must then be picklable. Disk artifacts are identical
    to the serial run, but the returned ``factor_results`` carry only the
    summary frames — ``clean_factor_data``, ``daily_ic`` and ``quantile_returns``
    are empty placeholders (read them from ``output_dir`` if needed).
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
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
        transaction_cost_bps=config.transaction_cost_bps,
    )
    run_id, run_dir = create_run_directory(resolved_config, run_id=run_id)
    _notifier = notifier or NullNotifier()
    _t0 = time.monotonic()
    _milestones = {
        int(len(resolved_config.factor_names) * pct)
        for pct in (0.25, 0.50, 0.75)
    } - {0, len(resolved_config.factor_names)}
    _notifier.notify_start(
        "evaluate",
        details={
            "因子数": str(len(resolved_config.factor_names)),
            "workers": str(workers),
        },
    )
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

    if workers > 1 and len(resolved_config.factor_names) > 1:
        factor_results = _evaluate_factors_parallel(
            resolved_config,
            storage=storage,
            pro=pro,
            run_dir=run_dir,
            price_data=price_data,
            universe_panel=universe_panel,
            workers=workers,
            log_info=log_info,
            notifier=_notifier,
            milestones=_milestones,
        )
    else:
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
                _done = len(factor_results)
                if _done in _milestones:
                    _notifier.notify_progress("evaluate", _done, len(resolved_config.factor_names))
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

    _notifier.notify_eval_done(
        "evaluate", run_id, len(factor_results), time.monotonic() - _t0
    )
    return EvaluationRunResult(
        run_id=run_id,
        output_dir=run_dir,
        factor_results=factor_results,
        summary=summary,
        metadata_path=run_paths["metadata"],
    )


_WORKER_EVAL_CONTEXT: dict | None = None


def _init_evaluation_worker(context: dict) -> None:
    global _WORKER_EVAL_CONTEXT
    _WORKER_EVAL_CONTEXT = context


def _evaluate_factor_task(factor_name: str) -> tuple[str, pd.DataFrame]:
    context = _WORKER_EVAL_CONTEXT
    if context is None:
        raise RuntimeError("evaluation worker is not initialized")
    with _suppress_known_evaluation_warnings():
        result = evaluate_factor(
            factor_name=factor_name,
            storage=context["storage"],
            pro=context["pro"],
            config=context["config"],
            run_dir=context["run_dir"],
            price_data=context["price_data"],
            universe_panel=context["universe_panel"],
        )
    return factor_name, result.summary


def _evaluate_factors_parallel(
    config: EvaluationConfig,
    *,
    storage,
    pro,
    run_dir: str | Path,
    price_data: pd.DataFrame,
    universe_panel: pd.DataFrame | None,
    workers: int,
    log_info: Callable[[str], None] | None,
    notifier: NullNotifier | None = None,
    milestones: set[int] | None = None,
) -> tuple[FactorEvaluationResult, ...]:
    context = {
        "storage": storage,
        "pro": pro,
        "config": config,
        "run_dir": run_dir,
        "price_data": price_data,
        "universe_panel": universe_panel,
    }
    summaries: dict[str, pd.DataFrame] = {}
    ctx = multiprocessing.get_context("spawn")
    max_workers = min(workers, len(config.factor_names))
    with ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=ctx,
        initializer=_init_evaluation_worker,
        initargs=(context,),
    ) as pool:
        for factor_name, summary in pool.map(
            _evaluate_factor_task, config.factor_names
        ):
            _log(log_info, f"evaluation_factor_finished factor={factor_name}")
            summaries[factor_name] = summary
            _done = len(summaries)
            if milestones and notifier and _done in milestones:
                notifier.notify_progress("evaluate", _done, len(config.factor_names))

    empty = pd.DataFrame()
    return tuple(
        FactorEvaluationResult(
            factor_name=factor_name,
            clean_factor_data=empty,
            summary=summaries[factor_name],
            daily_ic=empty,
            quantile_returns=empty,
            output_dir=Path(run_dir) / "factors" / factor_name,
        )
        for factor_name in config.factor_names
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
