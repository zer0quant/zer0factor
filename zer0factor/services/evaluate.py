"""Run factor evaluations against stored factors."""

from __future__ import annotations

from collections.abc import Callable

from zer0factor.eval import EvaluationConfig, EvaluationRunResult, evaluate_factors
from zer0factor.notify.null import NullNotifier
from zer0factor.storage import FactorStorage

LogFn = Callable[[str], None]


class EvaluationService:
    def __init__(
        self,
        storage: FactorStorage,
        pro,
        *,
        log_info: LogFn | None = None,
        notifier: NullNotifier | None = None,
    ) -> None:
        self._storage = storage
        self._pro = pro
        self._log: LogFn = log_info or (lambda message: None)
        self._notifier = notifier

    def run(self, config: EvaluationConfig) -> EvaluationRunResult:
        return evaluate_factors(
            factor_names=config.factor_names,
            storage=self._storage,
            pro=self._pro,
            config=config,
            log_info=self._log,
            notifier=self._notifier,
        )
