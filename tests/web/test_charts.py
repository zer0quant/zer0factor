import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest

import zer0factor.web.charts as charts
from tests.eval_fixtures import make_clean_factor_data
from zer0factor.eval.series import SERIES_FILES, build_chart_series, write_chart_series
from zer0factor.web.charts import (
    autocorr_with_ci,
    detail_payload,
    get_series,
    group_table,
    ic_decay,
    latest_values,
)
from zer0factor.web.jsonsafe import to_jsonable
from zer0factor.web.runs import SummaryCache, scan_runs


@pytest.fixture
def run_fa(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"])
    (run,) = scan_runs(evaluations_dir)
    return run, SummaryCache().get(run)


def test_get_series_prefers_run_dir(run_fa, tmp_path):
    run, summary = run_fa
    cfd = pd.read_parquet(run.factor_dir("fa") / "clean_factor_data.parquet")
    write_chart_series(run.factor_dir("fa"), build_chart_series(cfd, summary))
    cache_dir = tmp_path / "cache"
    assert get_series(run, "fa", cache_dir, summary) is not None
    assert not (cache_dir / run.run_id / "fa").exists()


def test_get_series_derives_and_caches(run_fa, tmp_path, monkeypatch):
    run, summary = run_fa
    cache_dir = tmp_path / "cache"
    first = get_series(run, "fa", cache_dir, summary)
    assert first is not None
    for name in SERIES_FILES:
        assert (cache_dir / run.run_id / "fa" / name).exists()

    def boom(*args, **kwargs):
        raise AssertionError("should read cache")

    monkeypatch.setattr(charts, "build_chart_series", boom)
    assert get_series(run, "fa", cache_dir, summary) is not None


def test_get_series_returns_none_without_clean_data(make_run, evaluations_dir, tmp_path):
    make_run("20260101_000000", ["fa"], write_clean=False)
    (run,) = scan_runs(evaluations_dir)
    assert get_series(run, "fa", tmp_path / "cache", SummaryCache().get(run)) is None


def test_concurrent_derivation_is_safe(run_fa, tmp_path):
    run, summary = run_fa
    cache_dir = tmp_path / "cache"
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: get_series(run, "fa", cache_dir, summary), range(4)))
    assert all(r is not None for r in results)
    target = cache_dir / run.run_id / "fa"
    assert not list(target.glob("*.tmp-*"))
    for name in SERIES_FILES:
        pd.read_parquet(target / name)


def test_cumulative_ls_matches_portfolio(run_fa, tmp_path):
    run, summary = run_fa
    cache_dir = tmp_path / "cache"
    payload = detail_payload(run, "fa", "1D", cache_dir, summary)
    port = get_series(run, "fa", cache_dir, summary)["portfolio_daily_returns"]["1D:ls"]
    assert payload["cumulative"]["ls"][-1] == pytest.approx((1 + port).prod() - 1)
    assert set(payload["cumulative"]["groups"]) == {"1", "2", "3", "4", "5"}
    assert any("等权毛收益" in n for n in payload["notes"])
    assert any("10bps" in n for n in payload["notes"])


def test_group_table_has_ls_row_and_positive_max_dd():
    dates = pd.bdate_range("2024-01-02", periods=60)
    rng = np.random.default_rng(1)
    qret = pd.DataFrame(rng.normal(0, 0.01, (60, 3)), index=dates, columns=[1, 2, 3])
    port = pd.DataFrame(
        {"ls": rng.normal(0, 0.01, 60), "benchmark": rng.normal(0, 0.01, 60)}, index=dates
    )
    table = group_table(qret, port)
    assert [r["group"] for r in table] == ["1", "2", "3", "多空"]
    assert all(r["max_dd"] >= 0 for r in table)
    first = table[0]
    assert first["ann_vol"] == pytest.approx(qret[1].std() * np.sqrt(252))


def test_ic_decay_lag1_matches_manual():
    cfd = make_clean_factor_data(n_dates=30, n_assets=25)
    decay = ic_decay(cfd, max_lag=3)
    assert len(decay["rank"]) == 4 and len(decay["ic"]) == 4
    factor = cfd["factor"].unstack()
    ret = cfd["1D"].unstack()
    manual = [
        factor.iloc[i].corr(ret.iloc[i + 1], method="spearman") for i in range(len(factor) - 1)
    ]
    assert decay["rank"][1] == pytest.approx(np.mean(manual))
    lag0 = [factor.iloc[i].corr(ret.iloc[i], method="spearman") for i in range(len(factor))]
    assert decay["rank"][0] == pytest.approx(np.mean(lag0))


def test_autocorr_lag0_is_one():
    s = pd.Series(np.random.default_rng(3).normal(size=100))
    out = autocorr_with_ci(s, max_lag=5)
    assert out["acf"][0] == pytest.approx(1.0)
    assert len(out["acf"]) == 6
    assert out["ci"] == pytest.approx(1.96 / np.sqrt(100))


def test_detail_payload_all_nan_ic_is_serializable(run_fa, tmp_path):
    run, summary = run_fa
    ic_path = run.factor_dir("fa") / "daily_ic.parquet"
    ic = pd.read_parquet(ic_path)
    ic[:] = np.nan
    ic.to_parquet(ic_path)
    payload = detail_payload(run, "fa", "1D", tmp_path / "cache", summary)
    json.dumps(to_jsonable(payload), allow_nan=False)


def test_detail_payload_without_clean_data_still_has_summary(make_run, evaluations_dir, tmp_path):
    make_run("20260101_000000", ["fa"], write_clean=False)
    (run,) = scan_runs(evaluations_dir)
    payload = detail_payload(run, "fa", "1D", tmp_path / "cache", SummaryCache().get(run))
    assert payload["summary"]["factor_name"] == "fa"
    assert payload["cumulative"] is None
    assert payload["rank_ic"]["series"]["values"]


def test_latest_values_sorted_and_paged(run_fa, tmp_path):
    run, _ = run_fa
    out = latest_values(run, "fa", {"000001.SZ": "平安银行"}, 1, 10, tmp_path / "cache")
    assert out["total"] == 40 and len(out["items"]) == 10
    values = [i["value"] for i in out["items"]]
    assert values == sorted(values, reverse=True)
    page4 = latest_values(run, "fa", {}, 4, 10, tmp_path / "cache")
    assert len(page4["items"]) == 10
    assert out["date"] == "2024-04-22"
    named = [i for i in out["items"] + page4["items"] if i["ts_code"] == "000001.SZ"]
    assert not named or named[0]["name"] in ("平安银行", None)
