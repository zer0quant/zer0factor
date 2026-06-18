from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from zer0factor.eval.config import ReturnType
from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.report import ReportThresholds
from zer0factor.registry import FactorRegistry


@dataclass(frozen=True)
class BatchEvaluationConfig:
    factor_names: tuple[str, ...]
    start_date: str | None = None
    end_date: str | None = None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    universe: str | None = None
    max_loss: float = 0.35
    output_dir: Path = Path("data/evaluations")
    transaction_cost_bps: float = 10.0
    workers: int = 1
    report_thresholds: ReportThresholds = ReportThresholds()

    def to_request(self) -> EvaluationRequest:
        return EvaluationRequest(
            factor_names=self.factor_names,
            factor_source="explicit",
            start_date=self.start_date,
            end_date=self.end_date,
            periods=self.periods,
            quantiles=self.quantiles,
            return_type=self.return_type,
            universe=self.universe,
            max_loss=self.max_loss,
            output_dir=self.output_dir,
            transaction_cost_bps=self.transaction_cost_bps,
            workers=self.workers,
            report_thresholds=self.report_thresholds,
            generate_report=True,
        )


def load_batch_evaluation_config(path: Path | str) -> BatchEvaluationConfig:
    resolved_path = Path(path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"batch evaluation config not found: {resolved_path}")

    with open(resolved_path, "rb") as file:
        raw = tomllib.load(file)

    evaluation = raw.get("evaluation", {})
    factor_source = evaluation.get("factor_source", "explicit")
    if factor_source == "registry":
        registry_path = Path(evaluation.get("registry_path", "config/factors.toml"))
        registry = FactorRegistry(registry_path)
        enabled_only = bool(evaluation.get("enabled_only", True))
        categories = set(evaluation.get("categories") or [])
        candidates = registry.filter(enabled=True if enabled_only else None)
        if categories:
            candidates = [f for f in candidates if f.category in categories]
        factor_names = tuple(f.name for f in candidates)
        if not factor_names:
            raise ValueError("no factors matched from registry with the given filters")
    elif factor_source == "explicit":
        raw_factors = evaluation.get("factors", ())
        if isinstance(raw_factors, (str, bytes)):
            raise ValueError("batch config [evaluation].factors must be a list of names")
        factor_names = tuple(raw_factors)
        if not factor_names:
            raise ValueError("batch config [evaluation].factors must not be empty")
    else:
        raise ValueError(
            f"unknown factor_source '{factor_source}': must be 'explicit' or 'registry'"
        )

    return BatchEvaluationConfig(
        factor_names=factor_names,
        start_date=_optional_string(evaluation.get("start_date")),
        end_date=_optional_string(evaluation.get("end_date")),
        periods=tuple(evaluation.get("periods", (1, 5, 10))),
        quantiles=int(evaluation.get("quantiles", 10)),
        return_type=evaluation.get("return_type", "open_t1"),
        universe=evaluation.get("universe"),
        max_loss=float(evaluation.get("max_loss", 0.35)),
        output_dir=Path(evaluation.get("output_dir", "data/evaluations")),
        transaction_cost_bps=_optional_float(evaluation.get("transaction_cost_bps"), 10.0),
        workers=int(evaluation.get("workers", 1)),
        report_thresholds=_load_report_thresholds(raw.get("report", {})),
    )


def _optional_string(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_float(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _load_report_thresholds(report: dict[str, object]) -> ReportThresholds:
    defaults = ReportThresholds()
    return ReportThresholds(
        min_ic=float(report.get("min_ic", defaults.min_ic)),
        min_icir=float(report.get("min_icir", defaults.min_icir)),
        min_win_rate=float(report.get("min_win_rate", defaults.min_win_rate)),
        min_spread_bps=float(report.get("min_spread_bps", defaults.min_spread_bps)),
        min_sample_count=int(report.get("min_sample_count", defaults.min_sample_count)),
        min_monotonicity=float(
            report.get("min_monotonicity", defaults.min_monotonicity)
        ),
    )
