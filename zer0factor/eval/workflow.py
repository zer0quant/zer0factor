from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from zer0factor.eval.analysis import EvaluationAnalysisRunner
from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import (
    EvaluationRequest,
    EvaluationRun,
    EvaluationRunConfig,
    EvaluationWorkflowResult,
)
from zer0factor.eval.evaluator import FactorEvaluator
from zer0factor.eval.execution import (
    ProcessPoolEvaluationExecutor,
    SerialEvaluationExecutor,
)
from zer0factor.eval.figures import FactorFigureWriter
from zer0factor.eval.reporting import (
    EvaluationReporter,
    MarkdownReportRenderer,
    QuantileMonotonicityLoader,
    SummaryRanker,
)
from zer0factor.eval.selection import FactorSelector
from zer0factor.notify.null import NullNotifier


@dataclass(frozen=True)
class EvaluationRunFactory:
    def create(
        self,
        config: EvaluationRunConfig,
        run_id: str | None = None,
    ) -> EvaluationRun:
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run = EvaluationRun(
            run_id=run_id,
            run_dir=config.output_dir / run_id,
            config=config,
        )
        run.run_dir.mkdir(parents=True, exist_ok=False)
        return run


class DefaultReporterFactory:
    def __call__(self, thresholds) -> EvaluationReporter:
        return EvaluationReporter(
            ranker=SummaryRanker(thresholds),
            monotonicity_loader=QuantileMonotonicityLoader(),
            renderer=MarkdownReportRenderer(),
        )


class EvaluationWorkflow:
    def __init__(
        self,
        *,
        selector,
        run_factory,
        data_loader,
        artifact_store,
        metric_calculator,
        figure_writer,
        reporter_factory,
        analysis_runner=None,
        notifier=None,
        log_info: Callable[[str], None] | None = None,
    ) -> None:
        self.selector = selector
        self.run_factory = run_factory
        self.data_loader = data_loader
        self.artifact_store = artifact_store
        self.metric_calculator = metric_calculator
        self.figure_writer = figure_writer
        self.reporter_factory = reporter_factory
        self.analysis_runner = analysis_runner
        self.notifier = notifier or NullNotifier()
        self.log_info = log_info

    @classmethod
    def from_dependencies(
        cls,
        *,
        storage,
        pro,
        notifier=None,
        log_info: Callable[[str], None] | None = None,
    ) -> EvaluationWorkflow:
        return cls(
            selector=FactorSelector(),
            run_factory=EvaluationRunFactory(),
            data_loader=EvaluationDataLoader(storage, pro),
            artifact_store=EvaluationArtifactStore(),
            metric_calculator=MetricsCalculator(),
            figure_writer=FactorFigureWriter(),
            reporter_factory=DefaultReporterFactory(),
            analysis_runner=EvaluationAnalysisRunner(),
            notifier=notifier,
            log_info=log_info,
        )

    def run(
        self,
        request: EvaluationRequest,
        *,
        run_id: str | None = None,
    ) -> EvaluationWorkflowResult:
        if request.start_date is None:
            raise ValueError("start_date is required")

        factor_names = self.selector.resolve(request)
        config = EvaluationRunConfig(
            factor_names=factor_names,
            start_date=request.start_date,
            end_date=request.end_date,
            periods=request.periods,
            quantiles=request.quantiles,
            return_type=request.return_type,
            max_loss=request.max_loss,
            universe=request.universe,
            output_dir=request.output_dir,
            rolling_ic_window=request.rolling_ic_window,
            benchmark_index=request.benchmark_index,
            transaction_cost_bps=request.transaction_cost_bps,
            workers=request.workers,
            report_thresholds=request.report_thresholds,
            analysis_family=request.analysis_family,
        )
        if _requires_process_pool(config):
            self._ensure_process_pool_supported()
        run = self.run_factory.create(config, run_id=run_id)

        self.notifier.notify_start(
            "evaluate",
            details={
                "因子数": str(len(factor_names)),
                "workers": str(config.workers),
            },
        )
        _log(
            self.log_info,
            "evaluation_run_started "
            f"factors={len(factor_names)} "
            f"start_date={config.start_date} "
            f"end_date={config.end_date or 'latest'} "
            f"periods={','.join(str(period) for period in config.periods)} "
            f"return_type={config.return_type}",
        )

        milestones = {
            int(len(factor_names) * pct)
            for pct in (0.25, 0.50, 0.75)
        } - {0, len(factor_names)}
        on_factor_completed = _build_progress_callback(
            notifier=self.notifier,
            milestones=milestones,
        )
        executor = self._build_executor(
            run,
            on_factor_completed=on_factor_completed,
        )
        t0 = time.monotonic()
        factor_results = executor.execute(run)
        summary = pd.concat(
            [factor_result.summary for factor_result in factor_results],
            ignore_index=True,
        )
        self.artifact_store.write_run_summary(run, summary)

        report = None
        if request.generate_report:
            report = self.reporter_factory(config.report_thresholds).generate(
                run,
                summary,
            )

        analysis = None
        if config.analysis_family and self.analysis_runner is not None:
            analysis = self.analysis_runner.run(
                run,
                family_name=config.analysis_family,
            )

        finished_run = run.finish()
        _log(
            self.log_info,
            "evaluation_run_finished "
            f"run_id={finished_run.run_id} output_dir={finished_run.run_dir} "
            f"factors={len(factor_results)}",
        )
        self.notifier.notify_eval_done(
            "evaluate",
            finished_run.run_id,
            len(factor_results),
            time.monotonic() - t0,
        )
        return EvaluationWorkflowResult(
            run=finished_run,
            factor_results=factor_results,
            summary=summary,
            report=report,
            analysis=analysis,
        )

    def _build_executor(
        self,
        run: EvaluationRun,
        *,
        on_factor_completed: Callable[[int, int], None],
    ):
        if _requires_process_pool(run.config):
            self._ensure_process_pool_supported()
            return ProcessPoolEvaluationExecutor(
                storage=self.data_loader.storage,
                pro=self.data_loader.pro,
                data_loader=self.data_loader,
                workers=run.config.workers,
                log_info=self.log_info,
                on_factor_completed=on_factor_completed,
            )

        evaluator = FactorEvaluator(
            data_loader=self.data_loader,
            metric_calculator=self.metric_calculator,
            artifact_store=self.artifact_store,
            figure_writer=self.figure_writer,
            log_info=self.log_info,
        )
        return SerialEvaluationExecutor(
            evaluator=evaluator,
            data_loader=self.data_loader,
            log_info=self.log_info,
            on_factor_completed=on_factor_completed,
        )

    def _ensure_process_pool_supported(self) -> None:
        if (
            type(self.data_loader) is EvaluationDataLoader
            and type(self.metric_calculator) is MetricsCalculator
            and type(self.artifact_store) is EvaluationArtifactStore
            and type(self.figure_writer) is FactorFigureWriter
        ):
            return

        raise ValueError(
            "custom workflow components are not supported with process-pool "
            "execution yet; use workers=1 or construct the workflow with "
            "from_dependencies"
        )


def _log(log_info: Callable[[str], None] | None, message: str) -> None:
    if log_info is not None:
        log_info(message)


def _requires_process_pool(config: EvaluationRunConfig) -> bool:
    return config.workers > 1 and len(config.factor_names) > 1


def _build_progress_callback(
    *,
    notifier: NullNotifier,
    milestones: set[int],
) -> Callable[[int, int], None]:
    def on_factor_completed(done: int, total: int) -> None:
        if done in milestones:
            notifier.notify_progress("evaluate", done, total)

    return on_factor_completed
