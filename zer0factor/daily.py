"""Run the daily update as named steps; stop at the first failure."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[], object]


@dataclass(frozen=True)
class StepOutcome:
    name: str
    status: str  # "ok" | "failed" | "skipped"
    elapsed: float = 0.0
    error: str | None = None

    def describe(self) -> str:
        if self.status == "ok":
            return f"{self.name}：完成（{self.elapsed:.0f} 秒）"
        if self.status == "failed":
            return f"{self.name}：失败（{self.error}）"
        return f"{self.name}：未执行（前面的步骤失败）"


def run_steps(
    steps: Sequence[Step], *, log: Callable[[str], None] = lambda message: None
) -> list[StepOutcome]:
    outcomes: list[StepOutcome] = []
    failed = False
    for step in steps:
        if failed:
            outcomes.append(StepOutcome(step.name, "skipped"))
            continue
        log(f"daily_step_started step={step.name}")
        t0 = time.monotonic()
        try:
            step.run()
        except SystemExit as exc:  # click commands exit through SystemExit
            if exc.code not in (None, 0):
                failed = True
                outcomes.append(
                    StepOutcome(step.name, "failed", time.monotonic() - t0, f"exit {exc.code}")
                )
                log(f"daily_step_failed step={step.name} exit={exc.code}")
                continue
            outcomes.append(StepOutcome(step.name, "ok", time.monotonic() - t0))
        except Exception as exc:
            failed = True
            outcomes.append(
                StepOutcome(
                    step.name, "failed", time.monotonic() - t0, f"{type(exc).__name__}: {exc}"
                )
            )
            log(f"daily_step_failed step={step.name} error={type(exc).__name__}: {exc}")
            continue
        else:
            outcomes.append(StepOutcome(step.name, "ok", time.monotonic() - t0))
        log(f"daily_step_finished step={step.name}")
    return outcomes


__all__ = ["Step", "StepOutcome", "run_steps"]
