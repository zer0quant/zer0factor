from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

ReturnType = Literal["open_t1", "close_t0"]


def _normalize_period(period: object) -> int:
    if isinstance(period, bool):
        raise ValueError("periods must be positive integers")
    if isinstance(period, int):
        return period
    if isinstance(period, str):
        try:
            normalized = int(period)
        except ValueError as exc:
            raise ValueError("periods must be positive integers") from exc
        if str(normalized) == period:
            return normalized
    raise ValueError("periods must be positive integers")


@dataclass(frozen=True)
class EvaluationConfig:
    factor_names: tuple[str, ...]
    start_date: str
    end_date: str | None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    max_loss: float = 0.35
    universe: str | None = None
    output_dir: Path = Path("data/evaluations")
    rolling_ic_window: int = 63
    benchmark_index: str | None = None
    transaction_cost_bps: float = 10.0

    def __post_init__(self) -> None:
        if isinstance(self.factor_names, (str, bytes)):
            raise ValueError("factor_names must be a sequence of names")

        factor_names = tuple(self.factor_names)
        periods = tuple(_normalize_period(period) for period in self.periods)
        output_dir = Path(self.output_dir)

        if not factor_names:
            raise ValueError("factor_names must not be empty")
        if any(not name for name in factor_names):
            raise ValueError("factor_names must not contain empty names")
        if not periods or any(period <= 0 for period in periods):
            raise ValueError("periods must be positive integers")
        if self.quantiles < 2:
            raise ValueError("quantiles must be >= 2")
        if self.return_type not in {"open_t1", "close_t0"}:
            raise ValueError("return_type must be one of: open_t1, close_t0")
        if not 0 <= self.max_loss < 1:
            raise ValueError("max_loss must satisfy 0 <= max_loss < 1")
        if self.rolling_ic_window < 2:
            raise ValueError("rolling_ic_window must be >= 2")
        if self.transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be >= 0")

        object.__setattr__(self, "factor_names", factor_names)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "output_dir", output_dir)


@dataclass(frozen=True)
class FactorEvaluationResult:
    factor_name: str
    clean_factor_data: pd.DataFrame
    summary: pd.DataFrame
    daily_ic: pd.DataFrame
    quantile_returns: pd.DataFrame
    figure_paths: tuple[Path, ...] = field(default_factory=tuple)
    output_dir: Path | None = None


@dataclass(frozen=True)
class EvaluationRunResult:
    run_id: str
    output_dir: Path
    factor_results: tuple[FactorEvaluationResult, ...]
    summary: pd.DataFrame
    metadata_path: Path
