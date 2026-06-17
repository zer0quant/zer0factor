import pandas as pd

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.workflow import EvaluationWorkflow
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

    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(columns=["trade_date", "pct_chg"])


def test_workflow_runs_evaluation_and_report(tmp_path, monkeypatch):
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
    workflow = EvaluationWorkflow.from_dependencies(storage=storage, pro=FakePro())

    result = workflow.run(
        EvaluationRequest(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240102",
            periods=(1,),
            quantiles=2,
            output_dir=tmp_path / "evaluations",
            generate_report=True,
        )
    )

    assert result.run.summary_csv.exists()
    assert result.run.ranked_summary_csv.exists()
    assert result.run.report_md.exists()
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert result.report is not None
