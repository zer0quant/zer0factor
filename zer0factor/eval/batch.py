from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from zer0factor.eval.config import ReturnType
from zer0factor.eval.report import ReportThresholds


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
    report_thresholds: ReportThresholds = ReportThresholds()


def load_batch_evaluation_config(path: Path | str) -> BatchEvaluationConfig:
    resolved_path = Path(path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"batch evaluation config not found: {resolved_path}")

    with open(resolved_path, "rb") as file:
        raw = tomllib.load(file)

    evaluation = raw.get("evaluation", {})
    factors = evaluation.get("factors", ())
    if isinstance(factors, (str, bytes)):
        raise ValueError("batch config [evaluation].factors must be a list of names")
    factor_names = tuple(factors)
    if not factor_names:
        raise ValueError("batch config [evaluation].factors must not be empty")

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
        report_thresholds=_load_report_thresholds(raw.get("report", {})),
    )


def _optional_string(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


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
