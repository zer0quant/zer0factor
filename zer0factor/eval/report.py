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
    "adjusted_ICIR",
    "directional_IC>0 %",
    "long_short_spread_bps",
}


@dataclass(frozen=True)
class ReportThresholds:
    min_ic: float = 0.02
    min_icir: float = 0.3
    min_win_rate: float = 52.0
    min_spread_bps: float = 0.0
    min_sample_count: int = 1000
    min_monotonicity: float = 0.3


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
    monotonicity: pd.Series | None = None,
) -> pd.DataFrame:
    missing = REQUIRED_SUMMARY_COLUMNS.difference(summary.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(f"summary.csv missing required columns: {missing_columns}")

    ranked = summary.copy()
    if "factor_direction" in ranked.columns:
        ranked["direction"] = ranked["factor_direction"].fillna(1).astype(int)
    else:
        ranked["direction"] = 1
        ranked.loc[ranked["IC Mean"].lt(0), "direction"] = -1
    ranked["adjusted_icir"] = ranked["adjusted_ICIR"]
    ranked["directional_IC_win_rate"] = ranked["directional_IC>0 %"]
    ranked["adjusted_spread_bps"] = ranked["long_short_spread_bps"]
    ranked["monotonicity"] = _align_monotonicity(ranked, monotonicity)
    ranked["score"] = (
        ranked["IC Mean"] * 100
        + ranked["adjusted_ICIR"]
        + ranked["long_short_spread_bps"] / 10
    )
    ranked["adjusted_score"] = (
        ranked["IC Mean"].abs() * 100
        + ranked["adjusted_icir"]
        + ranked["adjusted_spread_bps"] / 10
        + ranked["monotonicity"].fillna(0)
    )
    ranked["passed"] = (
        ranked["IC Mean"].abs().ge(thresholds.min_ic)
        & ranked["adjusted_icir"].ge(thresholds.min_icir)
        & ranked["directional_IC_win_rate"].ge(thresholds.min_win_rate)
        & ranked["adjusted_spread_bps"].gt(thresholds.min_spread_bps)
        & ranked["sample_count"].ge(thresholds.min_sample_count)
        & ranked["monotonicity"].ge(thresholds.min_monotonicity)
    )
    ranked["passed"] = ranked["passed"].fillna(False).astype(bool)
    return ranked.sort_values(
        ["passed", "adjusted_score"], ascending=[False, False]
    ).reset_index(drop=True)


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
    monotonicity = load_quantile_monotonicity(resolved_run_dir, summary)
    ranked = build_ranked_summary(summary, resolved_thresholds, monotonicity=monotonicity)

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
        f"- abs(IC Mean) >= {thresholds.min_ic}",
        f"- adjusted_ICIR >= {thresholds.min_icir}",
        f"- directional_IC>0 % >= {thresholds.min_win_rate}",
        f"- adjusted_spread_bps > {thresholds.min_spread_bps}",
        f"- sample_count >= {thresholds.min_sample_count}",
        f"- monotonicity >= {thresholds.min_monotonicity}",
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
        "adjusted_score",
        "score",
        "passed",
        "direction",
        "IC Mean",
        "adjusted_ICIR",
        "adjusted_icir",
        "adjusted_t-stat",
        "directional_IC>0 %",
        "directional_IC_win_rate",
        "adjusted_spread_bps",
        "monotonicity",
        "monotonicity_q_mean",
        "monotonicity_q_ir",
        "monotonicity_q_pos_rate",
        "monotonicity_q_gt_50_rate",
        "long_sharpe",
        "long_calmar",
        "long_ann_ret",
        "ls_sharpe",
        "ls_calmar",
        "ls_ann_ret",
        "ls_max_dd",
        "full_sharpe",
        "full_calmar",
        "full_ann_ret",
        "full_max_dd",
        "long_exc_sharpe",
        "long_exc_calmar",
        "long_exc_ann_ret",
        "long_exc_max_dd",
        "short_exc_sharpe",
        "short_exc_calmar",
        "short_exc_ann_ret",
        "short_exc_max_dd",
        "idx_exc_sharpe",
        "idx_exc_calmar",
        "idx_exc_ann_ret",
        "idx_exc_max_dd",
        "turnover_daily_long",
        "turnover_annual_rebalance_long",
        "turnover_daily_short",
        "turnover_annual_rebalance_short",
        "directional_IC>0 %(W)",
        "directional_IC>0 %(M)",
        "IC_near_far_ratio",
        "ls_ann_ret_ratio",
        "long_short_spread_bps",
        "sample_count",
    ]
    return frame.loc[:, [column for column in columns if column in frame.columns]]


def load_quantile_monotonicity(run_dir: Path, summary: pd.DataFrame) -> pd.Series:
    values: dict[tuple[str, str], float] = {}
    factors = summary["factor_name"].dropna().astype(str).unique()
    quantile_returns_by_factor = {
        factor_name: _read_quantile_returns(run_dir, factor_name)
        for factor_name in factors
    }
    for _, row in summary.iterrows():
        factor_name = str(row["factor_name"])
        period = str(row["period"])
        direction = -1 if row["IC Mean"] < 0 else 1
        quantile_returns = quantile_returns_by_factor.get(factor_name)
        raw_monotonicity = _calculate_period_monotonicity(quantile_returns, period)
        values[(factor_name, period)] = raw_monotonicity * direction
    if not values:
        return pd.Series(
            dtype="float64",
            index=pd.MultiIndex.from_tuples([], names=["factor_name", "period"]),
        )
    return pd.Series(
        values,
        index=pd.MultiIndex.from_tuples(values.keys(), names=["factor_name", "period"]),
        dtype="float64",
    )


def _align_monotonicity(
    ranked: pd.DataFrame,
    monotonicity: pd.Series | None,
) -> pd.Series:
    index = pd.MultiIndex.from_frame(
        ranked.loc[:, ["factor_name", "period"]].astype(str)
    )
    if monotonicity is None:
        return pd.Series(float("nan"), index=ranked.index, dtype="float64")
    aligned = monotonicity.reindex(index)
    return pd.Series(aligned.to_numpy(), index=ranked.index, dtype="float64")


def _read_quantile_returns(run_dir: Path, factor_name: str) -> pd.DataFrame | None:
    path = run_dir / "factors" / factor_name / "quantile_returns.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _calculate_period_monotonicity(
    quantile_returns: pd.DataFrame | None,
    period: str,
) -> float:
    if quantile_returns is None or period not in quantile_returns.columns:
        return float("nan")

    period_returns = quantile_returns[period].dropna()
    if len(period_returns) < 2:
        return float("nan")

    quantile_order = pd.Series(
        range(1, len(period_returns) + 1),
        index=period_returns.index,
        dtype="float64",
    )
    return float(quantile_order.corr(period_returns, method="spearman"))


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
