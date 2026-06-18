"""Run factor evaluations through the evaluation workflow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from zer0factor.eval.domain import EvaluationRequest, EvaluationWorkflowResult
from zer0factor.eval.workflow import EvaluationWorkflow

LogFn = Callable[[str], None]


class EvaluationWorkflowLike(Protocol):
    def run(
        self,
        request: EvaluationRequest,
        *,
        run_id: str | None = None,
    ) -> EvaluationWorkflowResult: ...


class EvaluationService:
    def __init__(
        self,
        workflow: EvaluationWorkflowLike,
    ) -> None:
        self._workflow = workflow

    @classmethod
    def from_dependencies(
        cls,
        storage,
        pro,
        *,
        log_info: LogFn | None = None,
        notifier=None,
    ):
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
    ) -> EvaluationWorkflowResult:
        if not isinstance(request, EvaluationRequest):
            raise TypeError(
                "EvaluationService.run expects an EvaluationRequest"
            )
        if workers is not None:
            raise TypeError(
                "workers is part of EvaluationRequest; pass workers on the "
                "request instead"
            )
        return self._workflow.run(request, run_id=run_id)
