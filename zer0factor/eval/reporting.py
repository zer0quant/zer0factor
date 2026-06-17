from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from zer0factor.eval.report import (
    EvaluationReportResult,
    ReportThresholds,
    build_ranked_summary,
    load_quantile_monotonicity,
    render_markdown_report,
)


@dataclass(frozen=True)
class SummaryRanker:
    thresholds: ReportThresholds

    def rank(
        self,
        summary: pd.DataFrame,
        monotonicity: pd.Series | None = None,
    ) -> pd.DataFrame:
        return build_ranked_summary(summary, self.thresholds, monotonicity=monotonicity)


class QuantileMonotonicityLoader:
    def load(self, run, summary: pd.DataFrame) -> pd.Series:
        return load_quantile_monotonicity(run.run_dir, summary)


class MarkdownReportRenderer:
    def render(
        self,
        run,
        ranked_summary: pd.DataFrame,
        thresholds: ReportThresholds,
    ) -> str:
        return render_markdown_report(
            run_dir=run.run_dir,
            ranked_summary=ranked_summary,
            thresholds=thresholds,
        )


class EvaluationReporter:
    def __init__(
        self,
        *,
        ranker: SummaryRanker,
        monotonicity_loader: QuantileMonotonicityLoader,
        renderer: MarkdownReportRenderer,
    ) -> None:
        self.ranker = ranker
        self.monotonicity_loader = monotonicity_loader
        self.renderer = renderer

    def generate(self, run, summary: pd.DataFrame) -> EvaluationReportResult:
        monotonicity = self.monotonicity_loader.load(run, summary)
        ranked = self.ranker.rank(summary, monotonicity)
        ranked.to_csv(run.ranked_summary_csv, index=False)
        run.report_md.write_text(
            self.renderer.render(run, ranked, self.ranker.thresholds),
            encoding="utf-8",
        )
        return EvaluationReportResult(
            run_dir=run.run_dir,
            report_path=run.report_md,
            ranked_summary_path=run.ranked_summary_csv,
            ranked_summary=ranked,
        )
