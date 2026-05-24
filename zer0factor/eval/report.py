from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

REQUIRED_SUMMARY_COLUMNS = {
    "factor_name",
    "period",
    "sample_count",
    "IC Mean",
    "ICIR",
    "IC>0 %",
    "long_short_spread_bps",
}


@dataclass(frozen=True)
class ReportThresholds:
    min_ic: float = 0.02
    min_icir: float = 0.3
    min_win_rate: float = 52.0
    min_spread_bps: float = 0.0
    min_sample_count: int = 1000


@dataclass(frozen=True)
class EvaluationReportResult:
    run_dir: Path
    report_path: Path
    ranked_summary_path: Path
    ranked_summary: pd.DataFrame


def find_latest_run_dir(evaluations_dir: Path | str = Path("data/evaluations")) -> Path:
    root = Path(evaluations_dir)
    run_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if not run_dirs:
        raise FileNotFoundError(f"no evaluation run directories found under {root}")
    return run_dirs[-1]


def build_ranked_summary(
    summary: pd.DataFrame,
    thresholds: ReportThresholds,
) -> pd.DataFrame:
    missing = REQUIRED_SUMMARY_COLUMNS.difference(summary.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(f"summary.csv missing required columns: {missing_columns}")

    ranked = summary.copy()
    ranked["score"] = (
        ranked["IC Mean"] * 100 + ranked["ICIR"] + ranked["long_short_spread_bps"] / 10
    )
    ranked["passed"] = (
        ranked["IC Mean"].ge(thresholds.min_ic)
        & ranked["ICIR"].ge(thresholds.min_icir)
        & ranked["IC>0 %"].ge(thresholds.min_win_rate)
        & ranked["long_short_spread_bps"].gt(thresholds.min_spread_bps)
        & ranked["sample_count"].ge(thresholds.min_sample_count)
    )
    ranked["passed"] = ranked["passed"].fillna(False).astype(bool)
    return ranked.sort_values(["passed", "score"], ascending=[False, False]).reset_index(
        drop=True
    )


def generate_evaluation_report(
    *,
    run_dir: Path | str,
    thresholds: ReportThresholds | None = None,
) -> EvaluationReportResult:
    resolved_run_dir = Path(run_dir)
    summary_path = resolved_run_dir / "summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(f"summary.csv not found: {summary_path}")

    resolved_thresholds = thresholds or ReportThresholds()
    summary = pd.read_csv(summary_path)
    ranked = build_ranked_summary(summary, resolved_thresholds)

    ranked_summary_path = resolved_run_dir / "ranked_summary.csv"
    report_path = resolved_run_dir / "report.md"
    ranked.to_csv(ranked_summary_path, index=False)
    report_path.write_text(
        render_markdown_report(
            run_dir=resolved_run_dir,
            ranked_summary=ranked,
            thresholds=resolved_thresholds,
        ),
        encoding="utf-8",
    )
    return EvaluationReportResult(
        run_dir=resolved_run_dir,
        report_path=report_path,
        ranked_summary_path=ranked_summary_path,
        ranked_summary=ranked,
    )


def render_markdown_report(
    *,
    run_dir: Path,
    ranked_summary: pd.DataFrame,
    thresholds: ReportThresholds,
) -> str:
    passed = ranked_summary[ranked_summary["passed"]]
    rejected = ranked_summary[~ranked_summary["passed"]]
    sections = [
        "# Factor Evaluation Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Generated at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## Rules",
        "",
        f"- IC Mean >= {thresholds.min_ic}",
        f"- ICIR >= {thresholds.min_icir}",
        f"- IC>0 % >= {thresholds.min_win_rate}",
        f"- long_short_spread_bps > {thresholds.min_spread_bps}",
        f"- sample_count >= {thresholds.min_sample_count}",
        "",
        "## Top Factors",
        "",
        _to_markdown_table(_display_columns(ranked_summary.head(20))),
        "",
        "## Passed Factors",
        "",
        _to_markdown_table(_display_columns(passed)),
        "",
        "## Rejected Factors",
        "",
        _to_markdown_table(_display_columns(rejected)),
        "",
        "## Figures",
        "",
        _render_figure_links(run_dir),
        "",
    ]
    return "\n".join(sections)


def _display_columns(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "factor_name",
        "period",
        "score",
        "passed",
        "IC Mean",
        "ICIR",
        "IC>0 %",
        "long_short_spread_bps",
        "sample_count",
    ]
    return frame.loc[:, [column for column in columns if column in frame.columns]]


def _to_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_None_"
    columns = list(frame.columns)
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = (_format_markdown_value(row[column]) for column in columns)
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def _format_markdown_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value).replace("|", "\\|")


def _render_figure_links(run_dir: Path) -> str:
    figures = sorted((run_dir / "factors").glob("*/figures/*.png"))
    if not figures:
        return "_No figures found_"
    return "\n".join(f"- `{path.relative_to(run_dir)}`" for path in figures)
