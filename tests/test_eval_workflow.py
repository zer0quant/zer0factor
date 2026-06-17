import pandas as pd
import pytest

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import EvaluationRequest, FactorEvaluationResult
from zer0factor.eval.figures import FactorFigureWriter
from zer0factor.eval.selection import FactorSelector
from zer0factor.eval.workflow import (
    DefaultReporterFactory,
    EvaluationRunFactory,
    EvaluationWorkflow,
)
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


class CustomMetricsCalculator(MetricsCalculator):
    pass


class RecordingMetricsCalculator(MetricsCalculator):
    def __init__(self, clean):
        self.clean = clean
        self.used = False

    def clean_factor_and_forward_returns(self, *args, **kwargs):
        self.used = True
        return self.clean

    def calculate_daily_ic(self, clean_factor_data):
        return pd.DataFrame(
            {"1D": [0.1, 0.2]},
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        )

    def calculate_quantile_returns(self, clean_factor_data):
        return pd.DataFrame({"1D": [0.01, 0.02]}, index=[1, 2])

    def build_factor_summary(self, **kwargs):
        return pd.DataFrame(
            {
                "factor_name": [kwargs["factor_name"]],
                "custom_metric_calculator_used": [self.used],
            }
        )

    def calculate_period_sample_counts(self, *args, **kwargs):
        return {"1D": 2}


class NoopFigureWriter:
    def write(self, result, *, rolling_ic_window):
        return ()


class FakeProcessPoolEvaluationExecutor:
    def __init__(self, **kwargs):
        pass

    def execute(self, run):
        return tuple(
            FactorEvaluationResult(
                factor_name=factor_name,
                output_dir=run.factor_dir(factor_name),
                summary=pd.DataFrame({"factor_name": [factor_name]}),
            )
            for factor_name in run.config.factor_names
        )


def test_workflow_uses_custom_metric_calculator_in_serial(tmp_path):
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
    metric_calculator = RecordingMetricsCalculator(clean)
    workflow = EvaluationWorkflow(
        selector=FactorSelector(),
        run_factory=EvaluationRunFactory(),
        data_loader=EvaluationDataLoader(storage, FakePro()),
        artifact_store=EvaluationArtifactStore(),
        metric_calculator=metric_calculator,
        figure_writer=NoopFigureWriter(),
        reporter_factory=DefaultReporterFactory(),
    )

    result = workflow.run(
        EvaluationRequest(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240102",
            periods=(1,),
            quantiles=2,
            output_dir=tmp_path / "evaluations",
            generate_report=False,
            workers=1,
        )
    )

    assert metric_calculator.used
    assert result.summary["custom_metric_calculator_used"].tolist() == [True]


def test_workflow_rejects_custom_components_with_process_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "zer0factor.eval.workflow.ProcessPoolEvaluationExecutor",
        FakeProcessPoolEvaluationExecutor,
    )
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    workflow = EvaluationWorkflow(
        selector=FactorSelector(),
        run_factory=EvaluationRunFactory(),
        data_loader=EvaluationDataLoader(storage, FakePro()),
        artifact_store=EvaluationArtifactStore(),
        metric_calculator=CustomMetricsCalculator(),
        figure_writer=FactorFigureWriter(),
        reporter_factory=DefaultReporterFactory(),
    )

    with pytest.raises(
        ValueError,
        match="custom workflow components are not supported with process-pool",
    ):
        workflow.run(
            EvaluationRequest(
                factor_names=("factor_a", "factor_b"),
                start_date="20240101",
                end_date="20240102",
                periods=(1,),
                quantiles=2,
                output_dir=tmp_path / "evaluations",
                generate_report=False,
                workers=2,
            )
        )
