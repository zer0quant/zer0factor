from pathlib import Path

import pytest

from zer0factor.eval.domain import (
    EvaluationRequest,
    EvaluationRun,
    EvaluationRunConfig,
)


def test_run_config_normalizes_periods_output_dir_and_universe(tmp_path):
    config = EvaluationRunConfig(
        factor_names=["factor_a", "factor_b"],
        start_date="20240101",
        end_date=None,
        periods=["1", 5],
        quantiles=5,
        output_dir=str(tmp_path / "evaluations"),
    )

    assert config.factor_names == ("factor_a", "factor_b")
    assert config.periods == (1, 5)
    assert config.output_dir == tmp_path / "evaluations"
    assert config.universe == "univ_trade_base"
    assert config.workers == 1


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"factor_names": []}, "factor_names must not be empty"),
        ({"periods": [0]}, "periods must be positive integers"),
        ({"quantiles": 1}, "quantiles must be >= 2"),
        ({"return_type": "bad"}, "return_type must be one of"),
        ({"max_loss": 1.0}, "max_loss must satisfy"),
        ({"transaction_cost_bps": -1}, "transaction_cost_bps must be >= 0"),
        ({"workers": 0}, "workers must be >= 1"),
    ],
)
def test_run_config_rejects_invalid_values(tmp_path, kwargs, message):
    values = {
        "factor_names": ("factor_a",),
        "start_date": "20240101",
        "end_date": "20240131",
        "periods": (1,),
        "quantiles": 5,
        "output_dir": tmp_path,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        EvaluationRunConfig(**values)


def test_evaluation_run_exposes_paths(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )
    run = EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)

    assert run.summary_csv == tmp_path / "run_001" / "summary.csv"
    assert run.summary_parquet == tmp_path / "run_001" / "summary.parquet"
    assert run.metadata_json == tmp_path / "run_001" / "metadata.json"
    assert run.ranked_summary_csv == tmp_path / "run_001" / "ranked_summary.csv"
    assert run.report_md == tmp_path / "run_001" / "report.md"
    assert run.factor_dir("factor_a") == tmp_path / "run_001" / "factors" / "factor_a"
    assert run.analysis_dir == tmp_path / "run_001" / "analysis"


def test_evaluation_request_allows_explicit_factor_names(tmp_path):
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date=None,
        output_dir=tmp_path,
    )

    assert request.factor_names == ("factor_a",)
    assert request.factor_source == "explicit"


def test_evaluation_request_rejects_string_factor_names():
    with pytest.raises(ValueError, match="factor_names must be a sequence of names"):
        EvaluationRequest(factor_names="factor_a")


def test_evaluation_request_rejects_string_categories():
    with pytest.raises(ValueError, match="categories must be a sequence of names"):
        EvaluationRequest(categories="style")
