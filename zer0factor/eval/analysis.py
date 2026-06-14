from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PROFILE_PREFIXES = (
    ("z_size_industry_neu_", "z_size_industry_neu"),
    ("z_industry_neu_", "z_industry_neu"),
    ("z_size_neu_", "z_size_neu"),
    ("z_", "z"),
)

ROLLING_RETURN_BASE_FACTORS = (
    "daily_return",
    "open_return",
    "intraday_return",
    "overnight_return",
)

SUMMARY_METRICS = [
    "composite_score",
    "long_exc_ann_ret",
    "long_exc_sharpe",
    "adjusted_ICIR",
    "adjusted_t-stat",
    "turnover_daily_long",
    "directional_IC>0 %",
    "monotonicity",
    "ls_ann_ret",
]


@dataclass(frozen=True)
class EvaluationAnalysisConfig:
    parse_factor_name: Callable[[str], dict[str, Any]]
    group_dimensions: list[str]
    representative_dimensions: list[str]
    display_columns: list[str]
    title: str


AnalysisConfig = EvaluationAnalysisConfig


@dataclass(frozen=True)
class AnalysisRunResult:
    report_path: Path
    output_dir: Path
    analyzed_count: int
    skipped_count: int


AnalysisResult = AnalysisRunResult


def latest_run_dir(evaluation_dir: Path = Path("data/evaluations")) -> Path:
    runs = sorted(p for p in evaluation_dir.iterdir() if (p / "summary.csv").exists())
    if not runs:
        raise FileNotFoundError(f"no evaluation summary found under {evaluation_dir}")
    return runs[-1]


def window_bucket(window: int) -> str:
    if window <= 10:
        return "short"
    if window <= 30:
        return "medium"
    return "long"


def parse_rolling_return_factor_name(factor_name: str) -> dict[str, Any]:
    preprocess = "raw"
    raw_name = factor_name
    for prefix, profile in PROFILE_PREFIXES:
        if factor_name.startswith(prefix):
            preprocess = profile
            raw_name = factor_name[len(prefix):]
            break

    base_factor = next(
        (name for name in ROLLING_RETURN_BASE_FACTORS if raw_name.startswith(name)),
        None,
    )
    if base_factor is None:
        raise ValueError(f"unknown rolling return factor name: {factor_name}")

    suffix = raw_name.removeprefix(f"{base_factor}_ma")
    if not suffix.isdigit():
        raise ValueError(f"factor name does not end with _ma<window>: {factor_name}")
    return {
        "base_factor": base_factor,
        "preprocess": preprocess,
        "window": int(suffix),
    }


def percentile_score(series: pd.Series, *, higher_is_better: bool = True) -> pd.Series:
    return series.rank(pct=True, ascending=higher_is_better)


class EvaluationAnalyzer:
    def __init__(self, summary: pd.DataFrame, config: EvaluationAnalysisConfig) -> None:
        self.summary = summary.copy()
        self.config = config
        self._enriched: pd.DataFrame | None = None
        self._skipped: pd.DataFrame | None = None

    @classmethod
    def from_summary_csv(
        cls,
        summary_path: Path,
        config: EvaluationAnalysisConfig,
    ) -> EvaluationAnalyzer:
        return cls(pd.read_csv(summary_path), config)

    def enrich(self) -> pd.DataFrame:
        if self._enriched is not None:
            return self._enriched.copy()

        enriched_rows: list[pd.Series] = []
        skipped_rows: list[pd.Series] = []
        for _, row in self.summary.iterrows():
            try:
                parsed = self.config.parse_factor_name(str(row["factor_name"]))
            except ValueError as exc:
                skipped = row.copy()
                skipped["_skip_reason"] = str(exc)
                skipped_rows.append(skipped)
                continue
            enriched = row.copy()
            for key, value in parsed.items():
                enriched[key] = value
            enriched_rows.append(enriched)

        enriched = pd.DataFrame(enriched_rows)
        skipped = pd.DataFrame(skipped_rows)
        if enriched.empty:
            enriched = pd.DataFrame(columns=list(self.summary.columns))
        if skipped.empty:
            skipped = pd.DataFrame(columns=[*self.summary.columns, "_skip_reason"])

        if not enriched.empty:
            if "window" in enriched.columns:
                enriched["window_bucket"] = enriched["window"].map(window_bucket)
            enriched["composite_score"] = self._calculate_composite_score(enriched)
        else:
            enriched["composite_score"] = pd.Series(dtype=float)

        self._enriched = enriched.reset_index(drop=True)
        self._skipped = skipped.reset_index(drop=True)
        return self._enriched.copy()

    def skipped_factors(self) -> pd.DataFrame:
        self.enrich()
        if self._skipped is None:
            return pd.DataFrame()
        return self._skipped.copy()

    def group_by(self, dimension: str) -> pd.DataFrame:
        enriched = self.enrich()
        if dimension not in enriched.columns or enriched.empty:
            return pd.DataFrame(columns=SUMMARY_METRICS)
        metrics = [column for column in SUMMARY_METRICS if column in enriched.columns]
        return (
            enriched.groupby(dimension)[metrics]
            .mean()
            .sort_values("composite_score", ascending=False)
        )

    def ranked_factors(self) -> pd.DataFrame:
        return self.enrich().sort_values("composite_score", ascending=False)

    def representative_factors(self) -> pd.DataFrame:
        ranked = self.ranked_factors()
        if ranked.empty:
            return ranked
        valid_dims = [d for d in self.config.representative_dimensions if d in ranked.columns]
        if not valid_dims:
            return ranked
        return (
            ranked.groupby(valid_dims, as_index=False)
            .head(1)
            .sort_values("composite_score", ascending=False)
        )

    def write_outputs(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        for dimension in self.config.group_dimensions:
            grouped = self.group_by(dimension)
            if not grouped.empty:
                grouped.to_csv(output_dir / f"by_{dimension}.csv")

        _select_display_columns(self.ranked_factors(), self.config).to_csv(
            output_dir / "ranked_factors.csv",
            index=False,
        )
        _select_display_columns(self.representative_factors(), self.config).to_csv(
            output_dir / "representative_factors.csv",
            index=False,
        )
        self.skipped_factors().to_csv(output_dir / "skipped_factors.csv", index=False)

        report_path = output_dir / "analysis_report.md"
        report_path.write_text(self.render_report(), encoding="utf-8")
        return report_path

    def render_report(self) -> str:
        enriched = self.enrich()
        representatives = self.representative_factors()
        skipped = self.skipped_factors()
        top = self.ranked_factors().head(20)
        sections = [
            f"# {self.config.title}",
            f"Factors analyzed: {len(enriched)}",
            (
                "## Counts\n\n"
                f"- Representative factors: {len(representatives)}\n"
                f"- Skipped factors: {len(skipped)}"
            ),
        ]
        for dimension in self.config.group_dimensions:
            grouped = self.group_by(dimension)
            if not grouped.empty:
                sections.append(f"## By {dimension}\n\n" + markdown_table(grouped))

        skipped_display = skipped
        if {"factor_name", "_skip_reason"}.issubset(skipped.columns):
            skipped_display = skipped[["factor_name", "_skip_reason"]]

        sections.extend([
            "## Top Ranked Factors\n\n"
            + markdown_table(_select_display_columns(top, self.config), include_index=False),
            "## Representative Factors\n\n"
            + markdown_table(
                _select_display_columns(representatives, self.config),
                include_index=False,
            ),
            "## Skipped Factors\n\n" + markdown_table(skipped_display, include_index=False),
        ])
        return "\n\n".join(sections)

    def _calculate_composite_score(self, enriched: pd.DataFrame) -> pd.Series:
        return (
            percentile_score(enriched["adjusted_ICIR"]) * 0.25
            + percentile_score(enriched["adjusted_t-stat"]) * 0.20
            + percentile_score(enriched["long_exc_ann_ret"]) * 0.25
            + percentile_score(enriched["long_exc_sharpe"]) * 0.20
            + percentile_score(
                enriched["turnover_daily_long"],
                higher_is_better=False,
            )
            * 0.10
        )


def run_analysis(
    *,
    summary_path: Path,
    output_dir: Path,
    config: EvaluationAnalysisConfig,
) -> AnalysisRunResult:
    analyzer = EvaluationAnalyzer.from_summary_csv(summary_path, config)
    report_path = analyzer.write_outputs(output_dir)
    return AnalysisRunResult(
        report_path=report_path,
        output_dir=output_dir,
        analyzed_count=len(analyzer.enrich()),
        skipped_count=len(analyzer.skipped_factors()),
    )


def markdown_table(frame: pd.DataFrame, *, include_index: bool = True) -> str:
    table = frame.reset_index() if include_index else frame.copy()
    if table.empty:
        return "_No rows._"
    formatted = table.copy()
    for column in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.4f}")
        else:
            formatted[column] = formatted[column].map(str)
    headers = [str(c) for c in formatted.columns]
    rows = formatted.values.tolist()
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _select_display_columns(
    frame: pd.DataFrame,
    config: EvaluationAnalysisConfig,
) -> pd.DataFrame:
    columns = [column for column in config.display_columns if column in frame.columns]
    return frame.loc[:, columns].copy()


ROLLING_RETURN_ANALYSIS_CONFIG = EvaluationAnalysisConfig(
    parse_factor_name=parse_rolling_return_factor_name,
    group_dimensions=["base_factor", "preprocess", "window", "window_bucket"],
    representative_dimensions=["base_factor", "preprocess", "window_bucket"],
    display_columns=[
        "factor_name",
        "composite_score",
        "base_factor",
        "preprocess",
        "window",
        "long_exc_ann_ret",
        "long_exc_sharpe",
        "adjusted_ICIR",
        "adjusted_t-stat",
        "turnover_daily_long",
        "directional_IC>0 %",
        "monotonicity",
        "ls_ann_ret",
    ],
    title="Rolling Return Factor Evaluation Analysis",
)

ANALYSIS_CONFIGS = {
    "rolling_return": ROLLING_RETURN_ANALYSIS_CONFIG,
}
