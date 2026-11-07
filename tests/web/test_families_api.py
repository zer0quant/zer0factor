import pytest
from fastapi.testclient import TestClient

from zer0factor.web.app import create_app


def _fam(name, outputs, raw, error=None, module=None):
    return {
        "name": name, "module": module or f"pkg.{name}", "origin": "package", "error": error,
        "base_factors": ["x"], "windows": [5], "profiles": ["raw", "z"], "raw_names": raw,
        "outputs": outputs, "uses_data_provider": False, "source": None,
    }


@pytest.fixture
def client(tmp_path, make_config):
    cfg = make_config(None)
    (tmp_path / "factors" / "a_x_5" / "date=20260105").mkdir(parents=True)
    (tmp_path / "factors" / "a_x_5" / "date=20260107").mkdir(parents=True)
    app = create_app(cfg, config_path=tmp_path / "s.toml", scheduler=False)
    calls = []

    def fake_run():
        calls.append(1)
        return {"families": [
            _fam("fam_a", ["a_x_5", "z_a_x_5"], ["a_x_5"]),
            _fam("broken", [], [], error="ImportError: boom"),
        ]}

    app.state.families.run = fake_run
    c = TestClient(app)
    c.calls = calls
    return c


def test_families_api_merges_state(client):
    body = client.get("/api/families").json()
    rows = {f["name"]: f for f in body["families"]}
    a = rows["fam_a"]
    assert a["status"] == "enabled" and a["is_new"] is True
    assert a["stored"] == 1 and a["stored_names"] == ["a_x_5"]
    assert a["data_end"] == "20260107"
    assert rows["broken"]["error"] == "ImportError: boom"
    assert body["scanned_at"]

    r = client.patch("/api/families/fam_a", json={"status": "archived", "note": "weak"})
    assert r.status_code == 200 and r.json()["status"] == "archived"
    again = {f["name"]: f for f in client.get("/api/families").json()["families"]}
    assert again["fam_a"]["status"] == "archived" and again["fam_a"]["note"] == "weak"
    assert client.patch("/api/families/broken", json={"status": "archived"}).status_code == 404
    assert client.patch("/api/families/fam_a", json={"status": "bogus"}).status_code == 422


def test_families_cached_until_refresh(client):
    client.get("/api/families")
    client.get("/api/families")
    assert len(client.calls) == 1
    client.get("/api/families?refresh=true")
    assert len(client.calls) == 2


def test_build_task_uses_discovered_families(client):
    r = client.post("/api/tasks", json={"kind": "build", "params": {"family": "fam_a"}})
    assert r.status_code == 201, r.text
    assert client.post("/api/tasks", json={"kind": "build",
                                            "params": {"family": "broken"}}).status_code == 422
    rows = {f["name"]: f for f in client.get("/api/families").json()["families"]}
    assert rows["fam_a"]["last_task"]["status"] == "queued"
