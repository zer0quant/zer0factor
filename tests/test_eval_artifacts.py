import json

import pandas as pd

from zer0factor.eval.artifacts import (
    create_run_directory,
    write_factor_artifacts,
    write_run_summary,
)
from zer0factor.eval.config import EvaluationConfig


def test_create_run_directory_uses_config_output_dir(tmp_path):
    config = EvaluationConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )

    run_id, run_dir = create_run_directory(config, run_id="20240131_120000")

    assert run_id == "20240131_120000"
    assert run_dir == tmp_path / "20240131_120000"
    assert run_dir.exists()


def test_write_factor_artifacts_creates_expected_files(tmp_path):
    clean = pd.DataFrame({"factor": [1.0]})
    daily_ic = pd.DataFrame({"1D": [0.1]}, index=pd.to_datetime(["2024-01-01"]))
    quantile_returns = pd.DataFrame({"1D": [0.001, 0.002]}, index=[1, 2])

    paths = write_factor_artifacts(
        factor_dir=tmp_path / "factors" / "factor_a",
        clean_factor_data=clean,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert paths["clean_factor_data"].name == "clean_factor_data.parquet"
    assert paths["daily_ic"].name == "daily_ic.parquet"
    assert paths["quantile_returns"].name == "quantile_returns.parquet"
    assert paths["clean_factor_data"].exists()
    assert paths["daily_ic"].exists()
    assert paths["quantile_returns"].exists()


def test_write_run_summary_creates_summary_and_metadata(tmp_path):
    summary = pd.DataFrame({"factor_name": ["factor_a"], "period": ["1D"]})
    config = EvaluationConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )

    paths = write_run_summary(
        run_dir=tmp_path,
        summary=summary,
        config=config,
        run_id="run_a",
    )

    assert paths["summary_csv"].exists()
    assert paths["summary_parquet"].exists()
    assert paths["metadata"].exists()
    metadata = json.loads(paths["metadata"].read_text())
    assert metadata["run_id"] == "run_a"
    assert metadata["factor_names"] == ["factor_a"]
    assert metadata["return_type"] == "open_t1"
