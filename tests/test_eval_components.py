import json

import pandas as pd

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig, FactorEvaluationResult


def _run(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        periods=(1,),
        output_dir=tmp_path,
    )
    return EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)


def test_artifact_store_writes_factor_and_run_artifacts(tmp_path):
    run = _run(tmp_path)
    store = EvaluationArtifactStore()
    store.create_run(run)
    result = FactorEvaluationResult(
        factor_name="factor_a",
        output_dir=run.factor_dir("factor_a"),
        summary=pd.DataFrame({"factor_name": ["factor_a"]}),
        clean_factor_data=pd.DataFrame({"x": [1]}),
        daily_ic=pd.DataFrame({"1D": [0.1]}),
        quantile_returns=pd.DataFrame({"1D": [0.01, 0.02]}, index=[1, 2]),
    )

    factor_paths = store.write_factor_artifacts(result)
    run_paths = store.write_run_summary(
        run,
        pd.DataFrame({"factor_name": ["factor_a"]}),
    )

    assert factor_paths["clean_factor_data"].exists()
    assert factor_paths["daily_ic"].exists()
    assert factor_paths["quantile_returns"].exists()
    assert run_paths["summary_csv"] == run.summary_csv
    assert run_paths["summary_parquet"] == run.summary_parquet
    assert run_paths["metadata"] == run.metadata_json
    metadata = json.loads(run.metadata_json.read_text(encoding="utf-8"))
    assert metadata["run_id"] == "run_001"
    assert metadata["factor_names"] == ["factor_a"]


def test_metrics_calculator_builds_period_sample_counts(monkeypatch):
    calculator = MetricsCalculator()

    def fake_clean(*args, **kwargs):
        period = kwargs["periods"][0]
        return pd.DataFrame({f"{period}D": [0.1, None, 0.2]})

    monkeypatch.setattr(
        "zer0factor.eval.calculator.get_clean_factor_and_forward_returns",
        fake_clean,
    )

    counts = calculator.calculate_period_sample_counts(
        pd.Series(dtype=float),
        pd.DataFrame(),
        quantiles=2,
        periods=(1, 5),
        max_loss=0.35,
    )

    assert counts == {"1D": 2, "5D": 2}


def test_metrics_calculator_suppresses_metric_stdout(monkeypatch, capsys):
    calculator = MetricsCalculator()
    expected = pd.DataFrame({"1D": [0.1]})

    def fake_daily_ic(clean_factor_data):
        print("alphalens output")
        return expected

    monkeypatch.setattr(
        "zer0factor.eval.calculator.calculate_daily_ic",
        fake_daily_ic,
    )

    result = calculator.calculate_daily_ic(pd.DataFrame({"factor": [1.0]}))

    pd.testing.assert_frame_equal(result, expected)
    assert capsys.readouterr().out == ""
