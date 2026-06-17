import pandas as pd
import pytest

from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig
from zer0factor.eval.report import ReportThresholds
from zer0factor.eval.reporting import (
    EvaluationReporter,
    MarkdownReportRenderer,
    QuantileMonotonicityLoader,
    SummaryRanker,
)


def _summary():
    return pd.DataFrame(
        {
            "factor_name": ["factor_good", "factor_bad"],
            "period": ["1D", "1D"],
            "sample_count": [2000, 500],
            "IC Mean": [0.03, 0.01],
            "adjusted_ICIR": [0.5, 0.2],
            "directional_IC>0 %": [55.0, 49.0],
            "long_short_spread_bps": [4.0, -1.0],
        }
    )


def test_summary_ranker_scores_and_flags_rows():
    monotonicity = pd.Series(
        [0.8, -0.2],
        index=pd.MultiIndex.from_tuples(
            [("factor_good", "1D"), ("factor_bad", "1D")],
            names=["factor_name", "period"],
        ),
    )
    ranked = SummaryRanker(ReportThresholds()).rank(_summary(), monotonicity)

    assert ranked["factor_name"].tolist() == ["factor_good", "factor_bad"]
    assert ranked.loc[0, "adjusted_score"] == pytest.approx(4.7)
    assert ranked.loc[0, "passed"]
    assert not ranked.loc[1, "passed"]


def test_reporter_writes_ranked_summary_and_markdown(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_good", "factor_bad"),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )
    run = EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)
    run.run_dir.mkdir(parents=True)
    factor_dir = run.factor_dir("factor_good")
    factor_dir.mkdir(parents=True)
    pd.DataFrame({"1D": [0.01, 0.02, 0.03]}, index=[1, 2, 3]).to_parquet(
        factor_dir / "quantile_returns.parquet"
    )
    (factor_dir / "figures").mkdir()
    (factor_dir / "figures" / "quantile_returns_1D.png").write_text("fake")
    reporter = EvaluationReporter(
        ranker=SummaryRanker(ReportThresholds()),
        monotonicity_loader=QuantileMonotonicityLoader(),
        renderer=MarkdownReportRenderer(),
    )

    result = reporter.generate(run, _summary())

    assert result.ranked_summary_path == run.ranked_summary_csv
    assert result.report_path == run.report_md
    assert result.ranked_summary_path.exists()
    assert result.report_path.exists()
    assert "factor_good" in result.report_path.read_text(encoding="utf-8")
