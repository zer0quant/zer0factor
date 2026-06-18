from zer0factor.eval.domain import EvaluationRequest
from zer0factor.services.evaluate import EvaluationService


class RecordingWorkflow:
    def __init__(self):
        self.requests = []

    def run(self, request, *, run_id=None):
        self.requests.append((request, run_id))
        return "result"


def test_evaluation_service_delegates_to_workflow():
    workflow = RecordingWorkflow()
    service = EvaluationService(workflow=workflow)
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
    )

    result = service.run(request, run_id="run_001")

    assert result == "result"
    assert workflow.requests == [(request, "run_001")]
