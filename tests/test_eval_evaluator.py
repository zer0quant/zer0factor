import pandas as pd

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig
from zer0factor.eval.evaluator import FactorEvaluator
from zer0factor.eval.figures import FactorFigureWriter
from zer0factor.storage import FactorStorage


class FakePro:
    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102", "20240103", "20240104"],
                "ts_code": ["000001.SZ"] * 4,
                "open": [10.0, 11.0, 12.0, 13.0],
                "close": [10.5, 11.5, 12.5, 13.5],
            }
        )

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "universe": [universe, universe],
                "ts_code": ["000001.SZ", "000001.SZ"],
            }
        )


def test_factor_evaluator_writes_outputs(tmp_path, monkeypatch):
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
            "factor_quantile": [1, 2],
            "1D": [0.01, 0.02],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )
    monkeypatch.setattr(
        "zer0factor.eval.calculator.get_clean_factor_and_forward_returns",
        lambda *args, **kwargs: clean,
    )
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240102",
        periods=(1,),
        quantiles=2,
        output_dir=tmp_path / "evaluations",
    )
    run = EvaluationRun(
        run_id="run_001",
        run_dir=tmp_path / "evaluations" / "run_001",
        config=config,
    )
    run.run_dir.mkdir(parents=True)
    evaluator = FactorEvaluator(
        data_loader=EvaluationDataLoader(storage, FakePro()),
        metric_calculator=MetricsCalculator(),
        artifact_store=EvaluationArtifactStore(),
        figure_writer=FactorFigureWriter(),
    )

    result = evaluator.evaluate("factor_a", run)

    assert result.factor_name == "factor_a"
    assert result.output_dir == run.factor_dir("factor_a")
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert (result.output_dir / "clean_factor_data.parquet").exists()
    assert (result.output_dir / "daily_ic.parquet").exists()
    assert (result.output_dir / "quantile_returns.parquet").exists()
    assert (result.output_dir / "figures" / "quantile_returns_1D.png").exists()
