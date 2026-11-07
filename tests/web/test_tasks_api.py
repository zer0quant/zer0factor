import pytest
from fastapi.testclient import TestClient

from zer0factor.web.app import create_app


class FakeSpawn:
    def __init__(self):
        self.started = []

    def __call__(self, task):
        self.started.append(task["id"])
        return 4242


@pytest.fixture
def app(tmp_path, make_run, make_config):
    for name in ("fa", "fb"):
        (tmp_path / "factors" / name).mkdir(parents=True)
    for u in ("univ_trade_base", "univ_trade_hs300"):
        (tmp_path / "zer0share" / "stock" / "universe" / f"name={u}").mkdir(parents=True)
    make_run("20260101_000000", ["fa"])
    app = create_app(make_config(None), config_path=tmp_path / "settings.toml", scheduler=False)
    app.state.scheduler.spawn = FakeSpawn()
    app.state.scheduler.alive = lambda t: True
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _create(client, factors=("fa",), **params):
    return client.post("/api/tasks", json={"kind": "evaluate",
                                           "params": {"factors": list(factors), **params}})


def test_create_evaluate_task_and_list(client):
    r = _create(client, ("fa", "fb"))
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["status"] == "queued"
    assert "--run-id" in task["command"]
    assert task["progress_total"] == 2
    body = client.get("/api/tasks").json()
    assert [t["id"] for t in body["tasks"]] == [task["id"]]
    assert (body["queued"], body["running"]) == (1, 0)
    assert client.get(f"/api/tasks/{task['id']}").json()["id"] == task["id"]
    assert client.get("/api/tasks/nope").status_code == 404
    assert client.get("/api/tasks?status=succeeded").json()["tasks"] == []


def test_create_rejects_unknown_factor_422(client):
    r = _create(client, ("fa", "zz"))
    assert r.status_code == 422
    assert "zz" in r.json()["detail"]
    assert client.post("/api/tasks", json={"kind": "shell", "params": {}}).status_code == 422


def test_log_endpoint_offsets(client, app):
    task = _create(client).json()
    log = app.state.store.log_path(task["id"])
    log.write_bytes(b"x" * 300_000)
    first = client.get(f"/api/tasks/{task['id']}/log?offset=0").json()
    assert len(first["text"]) == 262144 and first["offset"] == 262144
    assert first["size"] == 300_000 and first["done"] is False
    second = client.get(f"/api/tasks/{task['id']}/log?offset={first['offset']}").json()
    assert len(second["text"]) == 300_000 - 262144 and second["offset"] == 300_000
    beyond = client.get(f"/api/tasks/{task['id']}/log?offset=999999").json()
    assert beyond["text"] == ""
    fresh = _create(client).json()
    assert client.get(f"/api/tasks/{fresh['id']}/log").json() == {
        "text": "", "offset": 0, "size": 0, "done": False}


def test_cancel_queued_task(client):
    task = _create(client).json()
    r = client.post(f"/api/tasks/{task['id']}/cancel")
    assert r.json()["status"] == "cancelled"


def test_retry_copies_params(client):
    task = _create(client, quantiles=5).json()
    again = client.post(f"/api/tasks/{task['id']}/retry").json()
    assert again["id"] != task["id"]
    assert again["params"]["quantiles"] == 5
    assert again["run_id"] != task["run_id"]


def test_eval_options_lists_universes(client):
    body = client.get("/api/eval/options").json()
    assert body["universes"] == ["univ_trade_base", "univ_trade_hs300"]
    assert body["defaults"]["periods"] == [1, 5, 10]
    assert body["standard"]["quantiles"] == 5
    assert body["return_types"] == ["open_t1", "close_t0"]


def test_finished_evaluate_refreshes_catalog(client, app, make_run):
    task = _create(client).json()
    app.state.scheduler.tick()  # starts it (fake spawn)
    assert app.state.store.get(task["id"])["status"] == "running"
    make_run(task["run_id"], ["fa"])
    # while the task runs, its half-written run directory stays off the board
    client.post("/api/refresh")
    assert task["run_id"] not in [r["run_id"] for r in client.get("/api/meta").json()["runs"]]
    app.state.store.finish(task["id"], "succeeded", 0, None)
    app.state.scheduler.tick()
    runs = [r["run_id"] for r in client.get("/api/meta").json()["runs"]]
    assert task["run_id"] in runs
