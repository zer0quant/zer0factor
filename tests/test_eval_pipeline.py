import pandas as pd

from zer0factor.eval import EvaluationConfig, evaluate_factors
from zer0factor.storage import FactorStorage


class FakePro:
    def pro_bar(self, ts_code="", start_date=None, end_date=None, adj=None):
        assert start_date == "20240101"
        assert end_date is not None
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102", "20240103", "20240104"],
                "ts_code": ["000001.SZ"] * 4,
                "open": [10.0, 11.0, 12.0, 13.0],
                "close": [10.5, 11.5, 12.5, 13.5],
            }
        )


def test_evaluate_factors_writes_run_artifacts(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )

    clean = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "1D": [0.01, 0.02],
            "factor_quantile": [1, 2],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )

    def fake_clean_factor_and_forward_returns(*args, **kwargs):
        return clean

    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        fake_clean_factor_and_forward_returns,
    )

    config = EvaluationConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240102",
        periods=(1,),
        quantiles=2,
        output_dir=tmp_path / "evaluations",
    )

    result = evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=FakePro(),
        config=config,
        run_id="run_001",
    )

    assert result.run_id == "run_001"
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert (result.output_dir / "summary.csv").exists()
    assert (result.output_dir / "metadata.json").exists()
    factor_dir = result.output_dir / "factors" / "factor_a"
    assert (factor_dir / "clean_factor_data.parquet").exists()
    assert (factor_dir / "daily_ic.parquet").exists()
    assert (factor_dir / "quantile_returns.parquet").exists()
    assert (factor_dir / "figures" / "quantile_returns_1D.png").exists()
