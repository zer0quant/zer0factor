import pytest

from zer0factor.web.catalog import build_catalog

REGISTRY = """
[[factors]]
name = "fa"
category = "price"
source_type = "stored"
enabled = true
tags = ["momentum"]
description = "Factor A"
"""


@pytest.fixture
def stored(tmp_path):
    for name in ("fa", "fb", "fc"):
        (tmp_path / "factors" / name).mkdir(parents=True)


def test_board_rows_lists_all_stored_factors(stored, make_run, make_config):
    make_run("20260101_000000", ["fa", "fb"])
    catalog = build_catalog(make_config(REGISTRY))
    rows = {r["name"]: r for r in catalog.board_rows()}
    assert sorted(rows) == ["fa", "fb", "fc"]
    assert rows["fa"]["evaluated"] and rows["fb"]["evaluated"]
    assert rows["fc"]["evaluated"] is False
    assert rows["fc"]["icir"] is None and rows["fc"]["run_id"] is None
    assert rows["fa"]["run_id"] == "20260101_000000"


def test_board_ic_adj_is_direction_adjusted(stored, make_run, make_config):
    make_run("20260101_000000", ["fa"])
    catalog = build_catalog(make_config(REGISTRY))
    summary = catalog.summary_cache.get(catalog.get_run("20260101_000000"))
    raw = summary.iloc[0]
    row = next(r for r in catalog.board_rows() if r["name"] == "fa")
    assert row["direction"] == int(raw["factor_direction"])
    assert row["ic_adj"] == pytest.approx(raw["IC Mean"] * raw["factor_direction"])
    assert row["icir"] == pytest.approx(raw["adjusted_ICIR"])


def test_board_merges_registry_metadata(stored, make_config):
    rows = {r["name"]: r for r in build_catalog(make_config(REGISTRY)).board_rows()}
    assert rows["fa"]["category"] == "price"
    assert rows["fa"]["tags"] == ["momentum"]
    assert rows["fa"]["description"] == "Factor A"
    assert rows["fb"]["category"] is None and rows["fb"]["tags"] == []


def test_board_survives_missing_registry(stored, make_config):
    rows = build_catalog(make_config(None)).board_rows()
    assert len(rows) == 3


def test_runs_for_and_lookup(stored, make_run, make_config):
    make_run("20260101_000000", ["fa"])
    make_run("20260102_000000", ["fa", "fb"])
    catalog = build_catalog(make_config(REGISTRY))
    assert [r.run_id for r in catalog.runs_for("fa")] == ["20260102_000000", "20260101_000000"]
    assert catalog.has_factor("fc") and not catalog.has_factor("../etc")
    assert catalog.get_run("nope") is None


def test_latest_data_end_computed_once_per_catalog(stored, make_run, make_config):
    make_run("20260101_000000", ["fa"])
    make_run("20260201_000000", ["fb"])
    catalog = build_catalog(make_config(REGISTRY))
    calls = []
    real_get = catalog.summary_cache.get
    catalog.summary_cache.get = lambda run: calls.append(run.run_id) or real_get(run)
    for _ in range(3):
        for run in catalog.runs:
            catalog.is_standard(run)
    assert catalog.latest_end is not None
    assert len(calls) <= len(catalog.runs)
