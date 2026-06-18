import pytest

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.workflow import EvaluationWorkflow
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


def test_evaluation_service_request_path_uses_request_workers():
    workflow = RecordingWorkflow()
    service = EvaluationService(workflow=workflow)
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
        workers=4,
    )

    service.run(request)

    assert workflow.requests == [(request, None)]
    assert workflow.requests[0][0].workers == 4


def test_evaluation_service_request_path_rejects_workers_override():
    workflow = RecordingWorkflow()
    service = EvaluationService(workflow=workflow)
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
        workers=4,
    )

    with pytest.raises(TypeError, match="workers is part of EvaluationRequest"):
        service.run(request, workers=8)

    assert workflow.requests == []


def test_evaluation_service_from_dependencies_constructs_workflow_service(monkeypatch):
    workflow = RecordingWorkflow()
    log_info = object()
    notifier = object()
    calls = {}

    def fake_from_dependencies(*, storage, pro, log_info=None, notifier=None):
        calls.update(
            {
                "storage": storage,
                "pro": pro,
                "log_info": log_info,
                "notifier": notifier,
            }
        )
        return workflow

    monkeypatch.setattr(
        EvaluationWorkflow,
        "from_dependencies",
        staticmethod(fake_from_dependencies),
    )
    service = EvaluationService.from_dependencies(
        storage="storage",
        pro="pro",
        log_info=log_info,
        notifier=notifier,
    )
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
        workers=3,
    )

    result = service.run(request, run_id="run_002")

    assert result == "result"
    assert workflow.requests == [(request, "run_002")]
    assert calls == {
        "storage": "storage",
        "pro": "pro",
        "log_info": log_info,
        "notifier": notifier,
    }


def test_evaluation_service_run_requires_evaluation_request():
    workflow = RecordingWorkflow()
    service = EvaluationService(workflow=workflow)

    with pytest.raises(
        TypeError,
        match="EvaluationService.run expects an EvaluationRequest",
    ):
        service.run(object())

    assert workflow.requests == []
