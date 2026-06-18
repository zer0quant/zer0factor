"""Run factor evaluations through the evaluation workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from zer0factor.eval import EvaluationConfig, EvaluationRunResult, evaluate_factors
from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.workflow import EvaluationWorkflow
from zer0factor.notify.null import NullNotifier

LogFn = Callable[[str], None]


class EvaluationService:
    def __init__(
        self,
        workflow: EvaluationWorkflow,
        pro: Any | None = None,
        *,
        log_info: LogFn | None = None,
        notifier: NullNotifier | None = None,
    ) -> None:
        if pro is None:
            self._workflow = workflow
            self._legacy_storage = None
            self._legacy_pro = None
            self._legacy_log = None
            self._legacy_notifier = None
            return

        self._workflow = None
        self._legacy_storage = workflow
        self._legacy_pro = pro
        self._legacy_log: LogFn = log_info or (lambda message: None)
        self._legacy_notifier = notifier

    @classmethod
    def from_dependencies(cls, storage, pro, *, log_info=None, notifier=None):
        return cls(
            EvaluationWorkflow.from_dependencies(
                storage=storage,
                pro=pro,
                log_info=log_info,
                notifier=notifier,
            )
        )

    def run(
        self,
        request: EvaluationRequest,
        *,
        run_id: str | None = None,
        workers: int | None = None,
    ):
        if self._workflow is not None:
            if workers is not None:
                request = replace(request, workers=workers)
            return self._workflow.run(request, run_id=run_id)

        return self._run_legacy(request, workers=1 if workers is None else workers)

    def _run_legacy(
        self,
        config: EvaluationConfig,
        *,
        workers: int = 1,
    ) -> EvaluationRunResult:
        return evaluate_factors(
            factor_names=config.factor_names,
            storage=self._legacy_storage,
            pro=self._legacy_pro,
            config=config,
            log_info=self._legacy_log,
            workers=workers,
            notifier=self._legacy_notifier,
        )
