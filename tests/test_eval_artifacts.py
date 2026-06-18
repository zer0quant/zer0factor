import json

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from zer0factor.eval.artifacts import (
    create_run_directory,
    write_factor_artifacts,
    write_run_summary,
)
from zer0factor.eval.domain import (
    DEFAULT_EVALUATION_UNIVERSE,
    EvaluationRunConfig,
)
from zer0factor.eval.plots import (
    plot_cumulative_ic,
    plot_quantile_returns,
    plot_rolling_ic,
)


def test_create_run_directory_uses_config_output_dir(tmp_path):
    config = EvaluationRunConfig(
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

    pd.testing.assert_frame_equal(
        pd.read_parquet(paths["clean_factor_data"]),
        clean,
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(paths["daily_ic"]),
        daily_ic,
        check_freq=False,
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(paths["quantile_returns"]),
        quantile_returns,
    )


def test_write_run_summary_creates_summary_and_metadata(tmp_path):
    summary = pd.DataFrame(
        {"factor_name": ["factor_a"], "period": ["1D"]},
        index=pd.Index([7], name="source_index"),
    )
    config = EvaluationRunConfig(
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

    expected_summary = pd.DataFrame({"factor_name": ["factor_a"], "period": ["1D"]})
    pd.testing.assert_frame_equal(pd.read_csv(paths["summary_csv"]), expected_summary)
    pd.testing.assert_frame_equal(pd.read_parquet(paths["summary_parquet"]), expected_summary)

    metadata = json.loads(paths["metadata"].read_text())
    assert metadata["run_id"] == "run_a"
    assert metadata["factor_names"] == ["factor_a"]
    assert metadata["return_type"] == "open_t1"
    assert metadata["transaction_cost_bps"] == 10.0


def test_write_run_summary_serializes_tuple_periods_and_none_values(tmp_path):
    summary = pd.DataFrame({"factor_name": ["factor_a"], "period": ["1D"]})
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date=None,
        periods=(1, 5),
        universe=None,
        output_dir=tmp_path,
    )

    paths = write_run_summary(
        run_dir=tmp_path,
        summary=summary,
        config=config,
        run_id="run_a",
    )

    metadata = json.loads(paths["metadata"].read_text())
    assert metadata["end_date"] is None
    assert metadata["periods"] == [1, 5]
    assert metadata["universe"] == DEFAULT_EVALUATION_UNIVERSE


@pytest.mark.parametrize(
    ("plot_func", "kwargs"),
    [
        (
            plot_quantile_returns,
            {
                "quantile_returns": pd.DataFrame({"1D": [0.001, 0.002]}, index=[1, 2]),
                "period": "1D",
            },
        ),
        (
            plot_cumulative_ic,
            {"daily_ic": pd.DataFrame({"1D": [0.1]}, index=pd.to_datetime(["2024-01-01"]))},
        ),
        (
            plot_rolling_ic,
            {
                "daily_ic": pd.DataFrame({"1D": [0.1]}, index=pd.to_datetime(["2024-01-01"])),
                "window": 2,
            },
        ),
    ],
)
def test_plot_functions_close_figures_when_save_raises(tmp_path, monkeypatch, plot_func, kwargs):
    def raise_save_error(self, *args, **kwargs):
        raise OSError("save failed")

    monkeypatch.setattr(plt.Figure, "savefig", raise_save_error)

    with pytest.raises(OSError, match="save failed"):
        plot_func(**kwargs, output_path=tmp_path / "plot.png")

    assert plt.get_fignums() == []
