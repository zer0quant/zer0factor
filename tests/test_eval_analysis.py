from __future__ import annotations

import pandas as pd
import pytest

from zer0factor.eval.analysis import (
    ROLLING_RETURN_ANALYSIS_CONFIG,
    EvaluationAnalyzer,
    run_analysis,
    window_bucket,
)
from zer0factor.factor_registry import get_family


def _row(
    factor_name: str,
    *,
    t_stat: float = 18.0,
    icir: float = 0.36,
    ic_mean: float = -0.038,
    ic_win: float = 65.0,
    monthly_ic_win: float = 90.0,
    long_ann_ret: float = 0.10,
    long_sharpe: float = 1.5,
    long_calmar: float = 1.0,
    long_max_dd: float = -0.10,
    long_exc_ann_ret: float = 0.04,
    long_exc_sharpe: float = 0.8,
    monotonicity: float = 0.9,
    turnover: float = 0.25,
    direction: int = -1,
) -> dict:
    return {
        "factor_name": factor_name,
        "adjusted_t-stat": t_stat,
        "adjusted_ICIR": icir,
        "IC Mean": ic_mean,
        "directional_IC>0 %": ic_win,
        "directional_IC>0 %(M)": monthly_ic_win,
        "long_ann_ret": long_ann_ret,
        "long_sharpe": long_sharpe,
        "long_calmar": long_calmar,
        "long_max_dd": long_max_dd,
        "long_exc_ann_ret": long_exc_ann_ret,
        "long_exc_sharpe": long_exc_sharpe,
        "monotonicity": monotonicity,
        "turnover_daily_long": turnover,
        "factor_direction": direction,
        # Present in real summaries but intentionally not used by the new score.
        "long_short_spread_bps": 99.0,
        "ls_ann_ret": 0.03,
        "ls_sharpe": 99.0,
    }


def test_rolling_return_family_analysis_dimensions_extracts_all_fields() -> None:
    family = get_family("rolling_return")
    parsed = family.analysis_dimensions("z_size_industry_neu_intraday_return_ma20")

    assert parsed == {
        "base_factor": "intraday_return",
        "preprocess": "z_size_industry_neu",
        "window": 20,
    }


def test_window_bucket_groups_short_medium_and_long_windows() -> None:
    assert window_bucket(10) == "short"
    assert window_bucket(20) == "medium"
    assert window_bucket(60) == "long"


def test_analyzer_enrich_skips_unparseable_factor_names() -> None:
    analyzer = EvaluationAnalyzer(
        pd.DataFrame([
            _row("z_size_industry_neu_intraday_return_ma20"),
            _row("z_neu_daily_return"),
        ]),
        ROLLING_RETURN_ANALYSIS_CONFIG,
    )

    enriched = analyzer.enrich()

    assert enriched["factor_name"].tolist() == ["z_size_industry_neu_intraday_return_ma20"]
    assert analyzer.skipped_factors()["factor_name"].tolist() == ["z_neu_daily_return"]
    assert enriched.iloc[0]["base_factor"] == "intraday_return"
    assert enriched.iloc[0]["window_bucket"] == "medium"
    assert "composite_score" in enriched.columns


def test_ranked_factors_use_simple_composite_score_formula() -> None:
    summary = pd.DataFrame([
        _row(
            "z_size_industry_neu_intraday_return_ma10",
            t_stat=10.0,
            icir=0.10,
            long_exc_ann_ret=0.0,
            long_exc_sharpe=0.0,
            turnover=0.8,
        )
        | {"long_ann_ret": 100.0, "long_sharpe": 100.0, "ls_sharpe": 100.0},
        _row(
            "z_size_industry_neu_intraday_return_ma20",
            t_stat=20.0,
            icir=0.40,
            long_exc_ann_ret=0.05,
            long_exc_sharpe=0.9,
            turnover=0.1,
        )
        | {"long_ann_ret": -100.0, "long_sharpe": -100.0, "ls_sharpe": -100.0},
    ])
    analyzer = EvaluationAnalyzer(summary, ROLLING_RETURN_ANALYSIS_CONFIG)

    ranked = analyzer.ranked_factors()

    assert ranked.iloc[0]["factor_name"] == "z_size_industry_neu_intraday_return_ma20"
    assert ranked.iloc[0]["composite_score"] == pytest.approx(1.0)
    assert ranked.iloc[1]["composite_score"] == pytest.approx(0.5)


def test_representative_factors_keep_best_rank_per_dimension_group() -> None:
    summary = pd.DataFrame([
        _row(
            "z_size_industry_neu_intraday_return_ma30",
            long_exc_ann_ret=0.01,
            long_exc_sharpe=0.2,
        ),
        _row(
            "z_size_industry_neu_intraday_return_ma20",
            long_exc_ann_ret=0.05,
            long_exc_sharpe=0.8,
        ),
        _row("z_overnight_return_ma20", long_sharpe=-0.2, long_ann_ret=-0.03),
    ])
    analyzer = EvaluationAnalyzer(summary, ROLLING_RETURN_ANALYSIS_CONFIG)

    representatives = analyzer.representative_factors()

    assert "z_size_industry_neu_intraday_return_ma20" in representatives["factor_name"].values
    assert "z_size_industry_neu_intraday_return_ma30" not in representatives["factor_name"].values
    assert "z_overnight_return_ma20" in representatives["factor_name"].values


def test_run_analysis_writes_object_oriented_outputs_without_filter_buckets(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    output_dir = tmp_path / "analysis"
    pd.DataFrame([
        _row("z_size_industry_neu_intraday_return_ma20"),
        _row("z_overnight_return_ma20", long_sharpe=-0.2, long_ann_ret=-0.03),
        _row("z_neu_daily_return"),
    ]).to_csv(summary_path, index=False)

    result = run_analysis(
        summary_path=summary_path,
        output_dir=output_dir,
        config=ROLLING_RETURN_ANALYSIS_CONFIG,
    )

    assert result.report_path == output_dir / "analysis_report.md"
    assert result.analyzed_count == 2
    assert result.skipped_count == 1
    assert (output_dir / "ranked_factors.csv").exists()
    assert (output_dir / "representative_factors.csv").exists()
    assert (output_dir / "by_base_factor.csv").exists()
    assert (output_dir / "skipped_factors.csv").exists()
    assert not (output_dir / "strict_candidates.csv").exists()
    assert not (output_dir / "usable_candidates.csv").exists()
    assert not (output_dir / "weak_candidates.csv").exists()
    report = result.report_path.read_text(encoding="utf-8")
    assert "Representative Factors" in report
    assert "Strict candidates" not in report

    ranked = pd.read_csv(output_dir / "ranked_factors.csv")
    assert ranked.columns.tolist() == [
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
    ]
    assert "long_ann_ret" not in ranked.columns
    assert "long_sharpe" not in ranked.columns


def test_analysis_runner_writes_family_outputs(tmp_path) -> None:
    from zer0factor.eval.analysis import EvaluationAnalysisRunner
    from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig

    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    pd.DataFrame([
        _row("z_size_industry_neu_intraday_return_ma20"),
        _row("z_neu_daily_return"),
    ]).to_csv(run_dir / "ranked_summary.csv", index=False)
    config = EvaluationRunConfig(
        factor_names=("z_size_industry_neu_intraday_return_ma20", "z_neu_daily_return"),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
        analysis_family="rolling_return",
    )
    run = EvaluationRun(run_id="run_001", run_dir=run_dir, config=config)

    result = EvaluationAnalysisRunner().run(run, family_name="rolling_return")

    assert result.report_path == run.analysis_dir / "analysis_report.md"
    assert result.analyzed_count == 1
    assert result.skipped_count == 1
    assert (run.analysis_dir / "ranked_factors.csv").exists()


def test_analysis_runner_honors_empty_configs() -> None:
    from zer0factor.eval.analysis import EvaluationAnalysisRunner

    with pytest.raises(ValueError) as exc_info:
        EvaluationAnalysisRunner(configs={}).run(object(), family_name="rolling_return")

    message = str(exc_info.value)
    assert "unknown analysis family: rolling_return" in message
    assert message.endswith("known families: ")
