import json

import pytest
from fastapi.testclient import TestClient

from zer0factor.web.app import create_app


@pytest.fixture
def stored(tmp_path):
    for name in ("fa", "fb", "fc"):
        (tmp_path / "factors" / name).mkdir(parents=True)


@pytest.fixture
def client(stored, make_run, make_config):
    make_run("20260101_000000", ["fa", "fb"])
    return TestClient(create_app(make_config(None)))


def test_factors_endpoint_returns_rows(client):
    rows = client.get("/api/factors").json()["rows"]
    assert [r["name"] for r in rows] == ["fa", "fb", "fc"]
    assert rows[0]["evaluated"] is True
    for key in ("long_ann_ret", "long_max_dd", "long_sharpe"):
        assert isinstance(rows[0][key], float), key
        assert rows[2][key] is None, key  # unevaluated


def test_meta_endpoint(client):
    meta = client.get("/api/meta").json()
    assert meta["standard"]["universe"] == "univ_trade_base"
    assert meta["runs"][0]["standard"] is True
    assert meta["runs"][0]["n_factors"] == 2


def test_factor_endpoint_default_run(client):
    body = client.get("/api/factors/fa").json()
    assert body["default_run"] == "20260101_000000"
    assert body["runs"][0]["run_id"] == "20260101_000000"


def test_detail_endpoint_ok(client):
    r = client.get("/api/factors/fa/runs/20260101_000000", params={"period": "1D"})
    assert r.status_code == 200
    body = r.json()
    assert body["cumulative"]["ls"]
    assert body["rank_ic"]["series"]["values"]


def test_latest_endpoint(client):
    body = client.get("/api/factors/fa/runs/20260101_000000/latest?page=1&size=5").json()
    assert body["total"] == 40 and len(body["items"]) == 5


@pytest.mark.parametrize(
    "url",
    [
        "/api/factors/..%2F..%2Fetc/runs/x",
        "/api/factors/fa/runs/..%2Fx",
        "/api/factors/..",
        "/api/factors/fa/runs/%2E%2E",
        "/api/factors/nope",
    ],
)
def test_path_traversal_rejected(client, url):
    assert client.get(url).status_code == 404


def test_run_not_containing_factor_404(client):
    assert client.get("/api/factors/fc/runs/20260101_000000").status_code == 404


def test_unknown_period_404(client):
    assert client.get("/api/factors/fa/runs/20260101_000000?period=5D").status_code == 404


def test_compare_requires_2_to_8(client):
    assert client.get("/api/compare", params={"f": "fa"}).status_code == 422
    nine = ",".join(["fa"] * 9)
    assert client.get("/api/compare", params={"f": nine}).status_code == 422


def test_compare_ok_and_marks_inconsistent(stored, make_run, make_config):
    make_run("20260101_000000", ["fa"])
    make_run("20260102_000000", ["fb"], metadata={"universe": None})
    client = TestClient(create_app(make_config(None)))
    body = client.get("/api/compare", params={"f": "fa,fb"}).json()
    assert body["factors"] == ["fa", "fb"]
    assert body["inconsistent"] == ["fb"]
    assert body["missing_curve"] == ["fa", "fb"]  # compare never derives caches


def test_compare_unknown_factor_404(client):
    assert client.get("/api/compare", params={"f": "fa,zz"}).status_code == 404


def test_refresh_picks_up_new_run(client, make_run):
    make_run("20260105_000000", ["fc"])
    assert client.get("/api/factors").json()["rows"][2]["evaluated"] is False
    client.post("/api/refresh")
    assert client.get("/api/factors").json()["rows"][2]["evaluated"] is True


def test_spa_fallback_serves_index(stored, make_config, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>app</html>")
    client = TestClient(create_app(make_config(None), static_dir=static))
    r = client.get("/factor/abc")
    assert r.status_code == 200 and "app" in r.text
    assert client.get("/api/nope").status_code == 404


def test_responses_have_no_nan(client):
    for url in [
        "/api/meta",
        "/api/factors",
        "/api/factors/fc",
        "/api/factors/fa/runs/20260101_000000",
        "/api/compare?f=fa,fc",
    ]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "NaN" not in r.text and "Infinity" not in r.text
        json.loads(r.text)


def test_compare_reads_cache_only_and_reports_missing_curve(stored, make_run, make_config):
    make_run("20260101_000000", ["fa", "fb"])
    cfg = make_config(None)
    client = TestClient(create_app(cfg))
    body = client.get("/api/compare", params={"f": "fa,fb"}).json()
    assert body["missing_curve"] == ["fa", "fb"]
    assert body["curves"]["series"] == {}
    assert not cfg.web.cache_dir.exists()
    client.get("/api/factors/fa/runs/20260101_000000")  # detail derives fa's cache
    body = client.get("/api/compare", params={"f": "fa,fb"}).json()
    assert body["missing_curve"] == ["fb"]
    assert set(body["curves"]["series"]) == {"fa"}


def test_refresh_clears_correlation_cache(client):
    from zer0factor.web.correlation import _cached

    assert client.get("/api/compare/correlation", params={"f": "fa,fb"}).status_code == 200
    assert _cached.cache_info().currsize > 0
    client.post("/api/refresh")
    assert _cached.cache_info().currsize == 0


def test_board_curves_reads_cache_only(stored, make_run, make_config):
    make_run("20260101_000000", ["fa", "fb"])
    cfg = make_config(None)
    client = TestClient(create_app(cfg))
    body = client.get("/api/board/curves").json()
    assert set(body["items"]) == {"fa", "fb"}  # only standard-evaluated factors
    assert body["items"]["fa"] == {"cached": False, "ls": None}
    assert not cfg.web.cache_dir.exists()  # never derives
    client.get("/api/factors/fa/runs/20260101_000000")  # detail derives fa's cache
    body = client.get("/api/board/curves", params={"points": 20}).json()
    fa = body["items"]["fa"]
    assert fa["cached"] is True
    assert 2 <= len(fa["ls"]) <= 20
    assert all(v is None or isinstance(v, float) for v in fa["ls"])
    assert body["items"]["fb"]["cached"] is False


def test_board_curves_points_validated(client):
    assert client.get("/api/board/curves", params={"points": 5}).status_code == 422


def test_bases_endpoint_lists_bases(client):
    rows = client.get("/api/bases").json()["rows"]
    assert [r["base"] for r in rows] == ["fa", "fb", "fc"]
    for r in rows:
        assert r["status"] in {"ok", "mixed", "unevaluated", "missing"}
        assert r["status"] == "missing"  # no z_size_industry_neu_ versions stored


def test_base_versions_endpoint(client):
    body = client.get("/api/bases/fa").json()
    assert body["default_prep"] == "raw"
    assert [(v["name"], v["prep"], v["window"], v["evaluated"]) for v in body["versions"]] == [
        ("fa", "raw", None, True)
    ]


def test_base_versions_unknown_404(client):
    assert client.get("/api/bases/nope").status_code == 404


def _warm(client, name="fa"):
    assert client.get(f"/api/factors/{name}/runs/20260101_000000", params={"period": "1D"}).status_code == 200


def test_base_curves_by_prep(client):
    _warm(client)
    body = client.get("/api/bases/fa/curves", params={"prep": "raw"}).json()
    assert body["kind"] == "long_excess"
    assert body["missing"] == []
    assert list(body["series"]) == ["fa"]
    assert len(body["series"]["fa"]) == len(body["dates"]) > 0


def test_base_curves_by_window_none(client):
    _warm(client)
    body = client.get("/api/bases/fa/curves", params={"win": "none", "kind": "ls"}).json()
    assert body["kind"] == "ls"
    assert list(body["series"]) == ["fa"]


def test_base_curves_long_is_cumulative_long_return(client):
    _warm(client)
    long = client.get("/api/bases/fa/curves", params={"prep": "raw", "kind": "long"}).json()
    excess = client.get("/api/bases/fa/curves", params={"prep": "raw"}).json()
    assert long["kind"] == "long"
    assert long["dates"] == excess["dates"]
    assert len(long["series"]["fa"]) == len(long["dates"]) > 0
    assert long["series"]["fa"] != excess["series"]["fa"]


def test_base_curves_rejects_unknown_kind(client):
    assert client.get("/api/bases/fa/curves", params={"prep": "raw", "kind": "x"}).status_code == 400


def test_base_curves_missing_when_uncached(client):
    body = client.get("/api/bases/fa/curves", params={"prep": "raw"}).json()
    assert body["missing"] == ["fa"] and body["series"] == {}
    body = client.get("/api/bases/fc/curves", params={"prep": "raw"})
    assert body.status_code == 200
    assert body.json()["missing"] == ["fc"]


def test_base_curves_bad_args(client):
    assert client.get("/api/bases/fa/curves", params={"prep": "raw", "win": "5"}).status_code == 400
    assert client.get("/api/bases/fa/curves").status_code == 400
    assert client.get("/api/bases/fa/curves", params={"prep": "raw", "kind": "foo"}).status_code == 400
    assert client.get("/api/bases/fa/curves", params={"win": "abc"}).status_code == 400
    assert client.get("/api/bases/nope/curves", params={"prep": "raw"}).status_code == 404
