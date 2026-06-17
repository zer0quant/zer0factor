from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import (
    MetricsCalculator,
    suppress_known_evaluation_warnings,
)
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import (
    EvaluationRun,
    FactorEvaluationResult,
)
from zer0factor.eval.evaluator import EvaluationSharedData, FactorEvaluator
from zer0factor.eval.figures import FactorFigureWriter

FactorCompletedCallback = Callable[[int, int], None]


class EvaluationExecutor(Protocol):
    def execute(self, run: EvaluationRun) -> tuple[FactorEvaluationResult, ...]:
        ...


@dataclass
class SerialEvaluationExecutor:
    evaluator: object
    data_loader: object | None
    log_info: Callable[[str], None] | None = None
    on_factor_completed: FactorCompletedCallback | None = None

    def execute(self, run: EvaluationRun) -> tuple[FactorEvaluationResult, ...]:
        shared_data = self._load_shared_data(run)
        results: list[FactorEvaluationResult] = []
        with suppress_known_evaluation_warnings():
            for factor_name in run.config.factor_names:
                _log(self.log_info, f"evaluation_factor_started factor={factor_name}")
                results.append(
                    self.evaluator.evaluate(
                        factor_name,
                        run,
                        shared_data=shared_data,
                    )
                )
                done = len(results)
                if self.on_factor_completed is not None:
                    self.on_factor_completed(done, len(run.config.factor_names))
        return tuple(results)

    def _load_shared_data(self, run: EvaluationRun) -> EvaluationSharedData | None:
        if self.data_loader is None:
            return None

        config = run.config
        price_end_date = config.end_date or self.data_loader.max_factor_trade_date(
            config.factor_names,
            start_date=config.start_date,
        )
        _log(
            self.log_info,
            "evaluation_price_load_started "
            f"start_date={config.start_date} end_date={price_end_date}",
        )
        price_data = self.data_loader.load_prices(
            start_date=config.start_date,
            end_date=price_end_date,
            periods=config.periods,
        )
        _log(self.log_info, f"evaluation_price_load_finished rows={len(price_data)}")
        universe_panel = self.data_loader.load_universe(
            universe_name=config.universe,
            start_date=config.start_date,
            end_date=config.end_date,
        )
        return EvaluationSharedData(
            price_data=price_data,
            universe_panel=universe_panel,
        )


@dataclass
class ProcessPoolEvaluationExecutor:
    storage: object
    pro: object
    data_loader: object
    workers: int
    log_info: Callable[[str], None] | None = None
    on_factor_completed: FactorCompletedCallback | None = None

    def execute(self, run: EvaluationRun) -> tuple[FactorEvaluationResult, ...]:
        shared_data = self._load_shared_data(run)
        context = _EvaluationWorkerContext(
            storage=self.storage,
            pro=self.pro,
            run=run,
            price_data=shared_data.price_data,
            universe_panel=shared_data.universe_panel,
        )
        summaries: dict[str, pd.DataFrame] = {}
        ctx = multiprocessing.get_context("spawn")
        max_workers = min(self.workers, len(run.config.factor_names))
        with ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=ctx,
            initializer=_init_evaluation_worker,
            initargs=(context,),
        ) as pool:
            for factor_name, summary in pool.map(
                _evaluate_factor_task,
                run.config.factor_names,
            ):
                _log(self.log_info, f"evaluation_factor_finished factor={factor_name}")
                summaries[factor_name] = summary
                done = len(summaries)
                if self.on_factor_completed is not None:
                    self.on_factor_completed(done, len(run.config.factor_names))

        empty = pd.DataFrame()
        return tuple(
            FactorEvaluationResult(
                factor_name=factor_name,
                clean_factor_data=empty,
                summary=summaries[factor_name],
                daily_ic=empty,
                quantile_returns=empty,
                output_dir=run.factor_dir(factor_name),
            )
            for factor_name in run.config.factor_names
        )

    def _load_shared_data(self, run: EvaluationRun) -> EvaluationSharedData:
        config = run.config
        price_end_date = config.end_date or self.data_loader.max_factor_trade_date(
            config.factor_names,
            start_date=config.start_date,
        )
        _log(
            self.log_info,
            "evaluation_price_load_started "
            f"start_date={config.start_date} end_date={price_end_date}",
        )
        price_data = self.data_loader.load_prices(
            start_date=config.start_date,
            end_date=price_end_date,
            periods=config.periods,
        )
        _log(self.log_info, f"evaluation_price_load_finished rows={len(price_data)}")
        universe_panel = self.data_loader.load_universe(
            universe_name=config.universe,
            start_date=config.start_date,
            end_date=config.end_date,
        )
        return EvaluationSharedData(
            price_data=price_data,
            universe_panel=universe_panel,
        )


@dataclass(frozen=True)
class _EvaluationWorkerContext:
    storage: object
    pro: object
    run: EvaluationRun
    price_data: pd.DataFrame | None
    universe_panel: pd.DataFrame | None


_WORKER_EVAL_CONTEXT: _EvaluationWorkerContext | None = None


def _init_evaluation_worker(context: _EvaluationWorkerContext) -> None:
    global _WORKER_EVAL_CONTEXT
    _WORKER_EVAL_CONTEXT = context


def _evaluate_factor_task(factor_name: str) -> tuple[str, pd.DataFrame]:
    context = _WORKER_EVAL_CONTEXT
    if context is None:
        raise RuntimeError("evaluation worker is not initialized")

    evaluator = FactorEvaluator(
        data_loader=EvaluationDataLoader(context.storage, context.pro),
        metric_calculator=MetricsCalculator(),
        artifact_store=EvaluationArtifactStore(),
        figure_writer=FactorFigureWriter(),
    )
    with suppress_known_evaluation_warnings():
        result = evaluator.evaluate(
            factor_name,
            context.run,
            shared_data=EvaluationSharedData(
                price_data=context.price_data,
                universe_panel=context.universe_panel,
            ),
        )
    return factor_name, result.summary


def _log(log_info: Callable[[str], None] | None, message: str) -> None:
    if log_info is not None:
        log_info(message)
