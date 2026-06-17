from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from zer0factor.eval.report import ReportThresholds

ReturnType = Literal["open_t1", "close_t0"]
FactorSource = Literal["explicit", "registry"]
DEFAULT_EVALUATION_UNIVERSE = "univ_trade_base"


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
class EvaluationRunConfig:
    factor_names: tuple[str, ...]
    start_date: str
    end_date: str | None = None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    max_loss: float = 0.35
    universe: str | None = None
    output_dir: Path = Path("data/evaluations")
    rolling_ic_window: int = 63
    benchmark_index: str | None = None
    transaction_cost_bps: float = 10.0
    workers: int = 1
    report_thresholds: ReportThresholds = field(default_factory=ReportThresholds)
    analysis_family: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.factor_names, (str, bytes)):
            raise ValueError("factor_names must be a sequence of names")

        factor_names = tuple(self.factor_names)
        periods = tuple(_normalize_period(period) for period in self.periods)

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
        if self.workers < 1:
            raise ValueError("workers must be >= 1")

        object.__setattr__(self, "factor_names", factor_names)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(
            self,
            "universe",
            DEFAULT_EVALUATION_UNIVERSE if self.universe is None else self.universe,
        )


@dataclass(frozen=True)
class EvaluationRequest:
    factor_names: tuple[str, ...] = ()
    factor_source: FactorSource = "explicit"
    registry_path: Path = Path("config/factors.toml")
    enabled_only: bool = True
    categories: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    max_loss: float = 0.35
    universe: str | None = None
    output_dir: Path = Path("data/evaluations")
    rolling_ic_window: int = 63
    benchmark_index: str | None = None
    transaction_cost_bps: float = 10.0
    workers: int = 1
    report_thresholds: ReportThresholds = field(default_factory=ReportThresholds)
    generate_report: bool = True
    analysis_family: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor_names", tuple(self.factor_names))
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(
            self,
            "periods",
            tuple(_normalize_period(period) for period in self.periods),
        )
        object.__setattr__(self, "registry_path", Path(self.registry_path))
        object.__setattr__(self, "output_dir", Path(self.output_dir))


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    run_dir: Path
    config: EvaluationRunConfig
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_dir", Path(self.run_dir))

    @property
    def summary_csv(self) -> Path:
        return self.run_dir / "summary.csv"

    @property
    def summary_parquet(self) -> Path:
        return self.run_dir / "summary.parquet"

    @property
    def metadata_json(self) -> Path:
        return self.run_dir / "metadata.json"

    @property
    def ranked_summary_csv(self) -> Path:
        return self.run_dir / "ranked_summary.csv"

    @property
    def report_md(self) -> Path:
        return self.run_dir / "report.md"

    @property
    def analysis_dir(self) -> Path:
        return self.run_dir / "analysis"

    def factor_dir(self, factor_name: str) -> Path:
        return self.run_dir / "factors" / factor_name

    def finish(self) -> EvaluationRun:
        return EvaluationRun(
            run_id=self.run_id,
            run_dir=self.run_dir,
            config=self.config,
            started_at=self.started_at,
            finished_at=datetime.now(),
        )


@dataclass(frozen=True)
class FactorEvaluationResult:
    factor_name: str
    summary: pd.DataFrame
    output_dir: Path
    clean_factor_data: pd.DataFrame | None = None
    daily_ic: pd.DataFrame | None = None
    quantile_returns: pd.DataFrame | None = None
    figure_paths: tuple[Path, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(
            self,
            "figure_paths",
            tuple(Path(path) for path in self.figure_paths),
        )


@dataclass(frozen=True)
class EvaluationWorkflowResult:
    run: EvaluationRun
    factor_results: tuple[FactorEvaluationResult, ...]
    summary: pd.DataFrame
    report: object | None = None
    analysis: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor_results", tuple(self.factor_results))
