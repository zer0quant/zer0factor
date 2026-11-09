from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from zer0factor.eval.alphalens_adapter import (
    build_price_matrix,
    factor_long_to_alphalens_series,
    filter_factor_by_universe,
)
from zer0factor.eval.domain import EvaluationRun, FactorEvaluationResult
from zer0factor.eval.incremental import (
    CLEAN_FACTOR_DATA,
    chunk_start,
    evaluation_horizon,
    merge_clean,
)
from zer0factor.eval.series import build_chart_series, write_chart_series


@dataclass(frozen=True)
class EvaluationSharedData:
    price_data: pd.DataFrame | None = None
    universe_panel: pd.DataFrame | None = None


class FactorEvaluator:
    def __init__(
        self,
        *,
        data_loader,
        metric_calculator,
        artifact_store,
        figure_writer,
        log_info: Callable[[str], None] | None = None,
    ):
        self.data_loader = data_loader
        self.metric_calculator = metric_calculator
        self.artifact_store = artifact_store
        self.figure_writer = figure_writer
        self.log_info = log_info

    def evaluate(
        self,
        factor_name: str,
        run: EvaluationRun,
        shared_data: EvaluationSharedData | None = None,
    ) -> FactorEvaluationResult:
        config = run.config
        shared_data = shared_data or EvaluationSharedData()

        if factor_name not in config.factor_names:
            raise ValueError("factor_name must be included in config.factor_names")

        base_clean_path = None
        base_dir = run.base_factor_dir(factor_name)
        if base_dir is not None and (base_dir / CLEAN_FACTOR_DATA).exists():
            base_clean_path = base_dir / CLEAN_FACTOR_DATA
        elif run.load_start_date and run.load_start_date > config.start_date:
            # Not in the base run: a full evaluation, so shared data loaded from
            # the incremental start would be too short. Load our own instead.
            self._log(f"evaluation_incremental_no_base factor={factor_name} mode=full")
            shared_data = EvaluationSharedData(
                price_data=None,
                universe_panel=self.data_loader.load_universe(
                    universe_name=config.universe,
                    start_date=config.start_date,
                    end_date=config.end_date,
                ),
            )

        base_clean = None
        factor_start = config.start_date
        recompute_from = None
        if base_clean_path is not None:
            base_clean = pd.read_parquet(base_clean_path)
            recompute_from = chunk_start(base_clean, evaluation_horizon(config))
            if recompute_from is not None:
                factor_start = max(recompute_from.strftime("%Y%m%d"), config.start_date)
            self._log(
                f"evaluation_incremental factor={factor_name} base_rows={len(base_clean)} "
                f"recompute_from={factor_start}"
            )

        factor_data = self.data_loader.load_factor(
            factor_name,
            start_date=factor_start,
            end_date=config.end_date,
        )
        if factor_data.empty:
            raise ValueError(f"{factor_name}: no factor data")
        self._log(
            f"evaluation_factor_load_finished factor={factor_name} rows={len(factor_data)}"
        )

        factor = factor_long_to_alphalens_series(factor_data)
        factor = filter_factor_by_universe(factor, shared_data.universe_panel)
        if factor.empty:
            raise ValueError(f"{factor_name}: no factor data after universe filtering")

        price_data = shared_data.price_data
        if price_data is None:
            price_end_date = config.end_date or self.data_loader.max_factor_trade_date(
                (factor_name,),
                start_date=factor_start,
            )
            price_data = self.data_loader.load_prices(
                start_date=factor_start,
                end_date=price_end_date,
                periods=config.periods,
            )
        prices = build_price_matrix(price_data, config.return_type)

        self._log(f"evaluation_clean_factor_started factor={factor_name}")
        clean_factor_data = self.metric_calculator.clean_factor_and_forward_returns(
            factor,
            prices,
            quantiles=config.quantiles,
            periods=config.periods,
            # A short chunk ends in dates without forward returns, so its loss
            # ratio says nothing; the base run already passed the full-sample check.
            max_loss=1.0 if base_clean is not None else config.max_loss,
        )
        if base_clean is not None and recompute_from is not None:
            chunk_rows = len(clean_factor_data)
            clean_factor_data = merge_clean(base_clean, clean_factor_data, recompute_from)
            self._log(
                f"evaluation_incremental_merged factor={factor_name} chunk_rows={chunk_rows} "
                f"rows={len(clean_factor_data)}"
            )
        if clean_factor_data.empty:
            raise ValueError(f"{factor_name}: no clean factor data")
        self._log(
            f"evaluation_clean_factor_finished factor={factor_name} rows={len(clean_factor_data)}"
        )

        daily_ic = self.metric_calculator.calculate_daily_ic(clean_factor_data)
        quantile_returns = self.metric_calculator.calculate_quantile_returns(
            clean_factor_data
        )
        if quantile_returns.empty or len(quantile_returns.columns) == 0:
            raise ValueError(f"{factor_name}: no quantile return periods")
        self._log(
            f"evaluation_metrics_finished factor={factor_name} periods={len(quantile_returns.columns)}"
        )

        index_returns = self.data_loader.load_benchmark_returns(
            ts_code=config.benchmark_index,
            start_date=config.start_date,
            end_date=config.end_date,
        )
        period_sample_counts = self.metric_calculator.calculate_period_sample_counts(
            factor,
            prices,
            quantiles=config.quantiles,
            periods=config.periods,
            max_loss=config.max_loss,
            clean_factor_data=clean_factor_data,
        )
        portfolio_series: dict = {}
        summary = self.metric_calculator.build_factor_summary(
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
            transaction_cost_bps=config.transaction_cost_bps,
            period_sample_counts=period_sample_counts,
            portfolio_sink=portfolio_series,
        )

        result = FactorEvaluationResult(
            factor_name=factor_name,
            summary=summary,
            output_dir=run.factor_dir(factor_name),
            clean_factor_data=clean_factor_data,
            daily_ic=daily_ic,
            quantile_returns=quantile_returns,
        )
        if base_clean_path is not None and recompute_from is not None:
            # Years before the recomputed chunk are unchanged: hard-link them.
            self.artifact_store.write_factor_artifacts(
                result, link_from=base_clean_path, link_before_year=recompute_from.year
            )
        else:
            self.artifact_store.write_factor_artifacts(result)
        try:
            write_chart_series(
                result.output_dir,
                build_chart_series(clean_factor_data, summary, portfolio_series),
            )
        except Exception as exc:  # chart series must never break an evaluation
            self._log(f"evaluation_chart_series_failed factor={factor_name} error={exc!r}")
        figure_paths = self.figure_writer.write(
            result,
            rolling_ic_window=config.rolling_ic_window,
        )
        result = FactorEvaluationResult(
            factor_name=result.factor_name,
            summary=result.summary,
            output_dir=result.output_dir,
            clean_factor_data=result.clean_factor_data,
            daily_ic=result.daily_ic,
            quantile_returns=result.quantile_returns,
            figure_paths=figure_paths,
        )
        self._log(
            f"evaluation_artifacts_written factor={factor_name} output_dir={result.output_dir}"
        )
        return result

    def _log(self, message: str) -> None:
        if self.log_info is not None:
            self.log_info(message)
