from __future__ import annotations


class NullNotifier:
    def notify_start(self, stage: str, details: dict[str, str] | None = None) -> None:
        pass

    def notify_done(self, stage: str, rows: dict[str, int], elapsed: float) -> None:
        pass

    def notify_eval_done(
        self, stage: str, run_id: str, factor_count: int, elapsed: float
    ) -> None:
        pass

    def notify_progress(self, stage: str, done: int, total: int) -> None:
        pass

    def notify_error(self, stage: str, exc: Exception) -> None:
        pass
