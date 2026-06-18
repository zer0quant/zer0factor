"""Run factor evaluations through the evaluation workflow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, overload

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

        # Temporary compatibility path for old EvaluationConfig callers.
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

    @overload
    def run(
        self,
        request: EvaluationRequest,
        *,
        run_id: str | None = None,
    ): ...

    @overload
    def run(
        self,
        request: EvaluationConfig,
        *,
        run_id: str | None = None,
        workers: int | None = None,
    ) -> EvaluationRunResult: ...

    def run(
        self,
        request: EvaluationRequest | EvaluationConfig,
        *,
        run_id: str | None = None,
        workers: int | None = None,
    ):
        if isinstance(request, EvaluationRequest):
            if workers is not None:
                raise TypeError(
                    "workers is part of EvaluationRequest; pass workers on the "
                    "request instead"
                )
            if self._workflow is None:
                raise TypeError(
                    "EvaluationRequest requires a workflow-backed "
                    "EvaluationService; use from_dependencies(...)"
                )
            return self._workflow.run(request, run_id=run_id)

        return self._run_legacy_config(
            request,
            workers=1 if workers is None else workers,
        )

    def _run_legacy_config(
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
