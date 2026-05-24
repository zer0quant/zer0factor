import pandas as pd
import pytest

from zer0factor.eval.report import (
    ReportThresholds,
    build_ranked_summary,
    find_latest_run_dir,
    generate_evaluation_report,
)


def _summary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "factor_name": ["factor_good", "factor_bad", "factor_reverse"],
            "period": ["1D", "1D", "1D"],
            "sample_count": [2000, 500, 2000],
            "IC Mean": [0.03, 0.01, -0.03],
            "ICIR": [0.5, 0.2, 0.5],
            "IC>0 %": [55.0, 49.0, 55.0],
            "long_short_spread_bps": [4.0, -1.0, -4.0],
        }
    )


def test_build_ranked_summary_scores_and_flags_rows():
    summary = _summary().query("factor_name != 'factor_reverse'")
    monotonicity = pd.Series(
        [0.8, -0.2],
        index=pd.MultiIndex.from_tuples(
            [("factor_good", "1D"), ("factor_bad", "1D")],
            names=["factor_name", "period"],
        ),
    )

    ranked = build_ranked_summary(
        summary,
        ReportThresholds(),
        monotonicity=monotonicity,
    )

    assert ranked["factor_name"].tolist() == ["factor_good", "factor_bad"]
    assert ranked.loc[0, "score"] == pytest.approx(3.9)
    assert ranked.loc[0, "adjusted_score"] == pytest.approx(4.7)
    assert ranked.loc[0, "passed"]
    assert not ranked.loc[1, "passed"]


def test_build_ranked_summary_adjusts_reverse_factor_direction():
    summary = _summary().query("factor_name == 'factor_reverse'")

    ranked = build_ranked_summary(
        summary,
        ReportThresholds(min_monotonicity=0.0),
        monotonicity=pd.Series(
            [0.8],
            index=pd.MultiIndex.from_tuples(
                [("factor_reverse", "1D")], names=["factor_name", "period"]
            ),
        ),
    )

    assert ranked.loc[0, "direction"] == -1
    assert ranked.loc[0, "adjusted_spread_bps"] == pytest.approx(4.0)
    assert ranked.loc[0, "monotonicity"] == pytest.approx(0.8)
    assert ranked.loc[0, "adjusted_score"] == pytest.approx(3.9 + 0.8)
    assert ranked.loc[0, "passed"]


def test_generate_evaluation_report_loads_quantile_monotonicity(tmp_path):
    run_dir = tmp_path / "20260102_090000"
    run_dir.mkdir()
    _summary().query("factor_name == 'factor_reverse'").to_csv(
        run_dir / "summary.csv", index=False
    )
    factor_dir = run_dir / "factors" / "factor_reverse"
    factor_dir.mkdir(parents=True)
    pd.DataFrame({"1D": [0.03, 0.02, 0.01]}, index=[1, 2, 3]).to_parquet(
        factor_dir / "quantile_returns.parquet"
    )

    result = generate_evaluation_report(run_dir=run_dir)

    ranked = pd.read_csv(result.ranked_summary_path)
    assert ranked.loc[0, "direction"] == -1
    assert ranked.loc[0, "adjusted_spread_bps"] == pytest.approx(4.0)
    assert ranked.loc[0, "monotonicity"] == pytest.approx(1.0)
    assert ranked.loc[0, "passed"]
    report = result.report_path.read_text(encoding="utf-8")
    assert "adjusted_spread_bps" in report
    assert "monotonicity" in report


def test_build_ranked_summary_rejects_missing_required_columns():
    with pytest.raises(ValueError, match="summary.csv missing required columns"):
        build_ranked_summary(pd.DataFrame({"factor_name": ["factor_a"]}), ReportThresholds())


def test_find_latest_run_dir_uses_newest_directory_name(tmp_path):
    (tmp_path / "20260101_090000").mkdir()
    latest = tmp_path / "20260102_090000"
    latest.mkdir()

    assert find_latest_run_dir(tmp_path) == latest


def test_generate_evaluation_report_writes_ranked_summary_and_markdown(tmp_path):
    run_dir = tmp_path / "20260102_090000"
    run_dir.mkdir()
    _summary().query("factor_name != 'factor_reverse'").to_csv(
        run_dir / "summary.csv", index=False
    )
    figures_dir = run_dir / "factors" / "factor_good" / "figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "quantile_returns_1D.png").write_text("fake", encoding="utf-8")
    pd.DataFrame({"1D": [0.01, 0.02, 0.03]}, index=[1, 2, 3]).to_parquet(
        figures_dir.parent / "quantile_returns.parquet"
    )

    result = generate_evaluation_report(run_dir=run_dir)

    assert result.run_dir == run_dir
    assert result.report_path == run_dir / "report.md"
    assert result.ranked_summary_path == run_dir / "ranked_summary.csv"
    assert result.report_path.exists()
    assert result.ranked_summary_path.exists()
    ranked = pd.read_csv(result.ranked_summary_path)
    assert ranked["factor_name"].tolist() == ["factor_good", "factor_bad"]
    report = result.report_path.read_text(encoding="utf-8")
    assert "# Factor Evaluation Report" in report
    assert "factor_good" in report
    assert "quantile_returns_1D.png" in report


def test_generate_evaluation_report_requires_summary_csv(tmp_path):
    run_dir = tmp_path / "20260102_090000"
    run_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="summary.csv not found"):
        generate_evaluation_report(run_dir=run_dir)
