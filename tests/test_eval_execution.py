import pandas as pd

from zer0factor.eval.domain import (
    EvaluationRun,
    EvaluationRunConfig,
    FactorEvaluationResult,
)
from zer0factor.eval.execution import SerialEvaluationExecutor


class RecordingEvaluator:
    def __init__(self):
        self.calls = []

    def evaluate(self, factor_name, run, shared_data=None):
        self.calls.append((factor_name, shared_data))
        return FactorEvaluationResult(
            factor_name=factor_name,
            output_dir=run.factor_dir(factor_name),
            summary=pd.DataFrame({"factor_name": [factor_name]}),
        )


def test_serial_executor_preserves_factor_order(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_b", "factor_a"),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )
    run = EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)
    evaluator = RecordingEvaluator()
    executor = SerialEvaluationExecutor(evaluator=evaluator, data_loader=None)

    results = executor.execute(run)

    assert [r.factor_name for r in results] == ["factor_b", "factor_a"]
    assert [call[0] for call in evaluator.calls] == ["factor_b", "factor_a"]
