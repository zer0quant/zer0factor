"""Incremental evaluation must reproduce a full evaluation (design 2026-11-09)."""

import json
import os

import numpy as np
import pandas as pd
import pytest

from zer0factor.eval.domain import EvaluationRequest, EvaluationRunConfig
from zer0factor.eval.incremental import (
    chunk_start,
    evaluation_horizon,
    find_base_run,
    merge_clean,
    setting_mismatches,
    shared_load_start,
)
from zer0factor.eval.workflow import EvaluationWorkflow
from zer0factor.storage import FactorStorage

DATES = pd.bdate_range("2023-06-01", "2024-03-29")
ASSETS = [f"{i:06d}.SZ" for i in range(40)]
T1 = "20240215"  # market data end when the base run was made
T2 = "20240329"  # market data end now


def _market():
    rng = np.random.default_rng(7)
    shape = (len(DATES), len(ASSETS))
    log_ret = rng.normal(0, 0.02, size=shape)
    opens = 10 * np.exp(np.cumsum(log_ret, axis=0))
    signal = np.vstack([log_ret[1:], np.zeros((1, len(ASSETS)))])  # peeks one day ahead
    factor = 0.3 * signal + rng.normal(0, 0.02, size=shape)
    factor[rng.random(shape) < 0.05] = np.nan
    return (
        pd.DataFrame(opens, index=DATES, columns=ASSETS),
        pd.DataFrame(factor, index=DATES, columns=ASSETS),
    )


OPENS, FACTOR = _market()


def _long(panel, end):
    frame = panel.loc[: pd.Timestamp(end)].stack().rename("value").reset_index()
    frame.columns = ["trade_date", "ts_code", "value"]
    frame["trade_date"] = frame["trade_date"].dt.strftime("%Y%m%d")
    return frame


class FakePro:
    def __init__(self, market_end):
        self.market_end = pd.Timestamp(market_end)

    def _window(self, start_date, end_date):
        end = min(pd.Timestamp(end_date), self.market_end) if end_date else self.market_end
        return pd.Timestamp(start_date) if start_date else DATES[0], end

    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        start, end = self._window(start_date, end_date)
        bars = _long(OPENS, end.strftime("%Y%m%d"))
        bars = bars[bars["trade_date"] >= start.strftime("%Y%m%d")]
        return bars.rename(columns={"value": "open"}).assign(close=lambda d: d["open"])

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        start, end = self._window(start_date, end_date)
        days = DATES[(DATES >= start) & (DATES <= end)]
        rows = [(d.strftime("%Y%m%d"), universe, a) for d in days for a in ASSETS[:36]]
        return pd.DataFrame(rows, columns=["trade_date", "universe", "ts_code"])

    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(columns=["trade_date", "pct_chg"])


def _storage(tmp_path, name, end):
    storage = FactorStorage(tmp_path / name, tmp_path / f"{name}.duckdb")
    storage.write("factor_a", _long(FACTOR, end))
    return storage


def _request(output_dir, **kwargs):
    return EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20230601",
        end_date=None,
        periods=(1,),
        quantiles=5,
        universe="univ_test",
        output_dir=output_dir,
        generate_report=False,
        **kwargs,
    )


def _run(storage, pro, request, run_id):
    return EvaluationWorkflow.from_dependencies(storage=storage, pro=pro).run(request, run_id=run_id)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("incremental")
    out = tmp_path / "evaluations"
    base = _run(_storage(tmp_path, "f1", T1), FakePro(T1), _request(out), "base")
    now = _storage(tmp_path, "f2", T2)
    full = _run(now, FakePro(T2), _request(tmp_path / "full"), "full")
    inc = _run(now, FakePro(T2), _request(out, incremental=True), "inc")
    return base, full, inc


def test_incremental_summary_equals_full(runs):
    base, full, inc = runs
    assert inc.summary["end_date"].iloc[0] > base.summary["end_date"].iloc[0]
    pd.testing.assert_frame_equal(inc.summary, full.summary, check_exact=False, rtol=1e-10)


def test_incremental_artifacts_equal_full(runs):
    _, full, inc = runs
    full_dir, inc_dir = full.run.factor_dir("factor_a"), inc.run.factor_dir("factor_a")
    names = sorted(p.name for p in full_dir.iterdir() if p.suffix == ".parquet")
    assert "clean_factor_data.parquet" in names
    for name in names:
        pd.testing.assert_frame_equal(
            pd.read_parquet(inc_dir / name), pd.read_parquet(full_dir / name),
            check_exact=False, rtol=1e-10,
        )


def test_incremental_hard_links_unchanged_years(runs):
    base, _, inc = runs
    base_clean = base.run.factor_dir("factor_a") / "clean_factor_data.parquet"
    inc_clean = inc.run.factor_dir("factor_a") / "clean_factor_data.parquet"
    assert sorted(p.name for p in inc_clean.iterdir()) == ["2023.parquet", "2024.parquet"]
    assert os.stat(inc_clean / "2023.parquet").st_ino == os.stat(base_clean / "2023.parquet").st_ino
    assert os.stat(inc_clean / "2024.parquet").st_ino != os.stat(base_clean / "2024.parquet").st_ino


def test_incremental_metadata_and_shared_load_window(runs):
    base, _, inc = runs
    meta = json.loads(inc.run.metadata_json.read_text())
    assert meta["mode"] == "incremental"
    assert meta["base_run_id"] == "base"
    assert meta["end_date"] is None  # still a standard "latest" run for the board
    assert "20240101" < meta["data_start_date"] < T1
    assert "mode" not in json.loads(base.run.metadata_json.read_text())


def test_incremental_without_base_run_is_full(tmp_path):
    storage = _storage(tmp_path, "f", T1)
    result = _run(storage, FakePro(T1), _request(tmp_path / "empty", incremental=True), "only")
    assert "mode" not in json.loads(result.run.metadata_json.read_text())


def test_incremental_rejects_multi_period_and_mismatched_base(runs, tmp_path):
    base, _, _ = runs
    storage = _storage(tmp_path, "f", T2)
    with pytest.raises(ValueError, match="single period"):
        _run(storage, FakePro(T2), _request(tmp_path / "x", base_run_dir=base.run.run_dir).__class__(
            **{**_request(tmp_path / "x", base_run_dir=base.run.run_dir).__dict__, "periods": (1, 5)}
        ), "multi")
    other = _request(tmp_path / "y", base_run_dir=base.run.run_dir)
    other = other.__class__(**{**other.__dict__, "quantiles": 10})
    with pytest.raises(ValueError, match="quantiles"):
        _run(storage, FakePro(T2), other, "mismatch")


def _config(**kwargs):
    defaults = dict(
        factor_names=("a",), start_date="20160101", periods=(1,), quantiles=10,
        return_type="open_t1", universe="u",
    )
    return EvaluationRunConfig(**{**defaults, **kwargs})


def test_evaluation_horizon():
    assert evaluation_horizon(_config()) == 2
    assert evaluation_horizon(_config(periods=(5,), return_type="close_t0")) == 5


def test_setting_mismatches_and_find_base_run(tmp_path):
    config = _config()
    meta = {
        "start_date": "20160101", "periods": [1], "quantiles": 10, "return_type": "open_t1",
        "universe": "u", "max_loss": 0.35, "end_date": None,
    }
    assert setting_mismatches(meta, config) == []
    assert setting_mismatches({**meta, "end_date": "20240101"}, config)
    for run_id, m in (("20240101_000000", meta), ("20240102_000000", {**meta, "quantiles": 5})):
        run = tmp_path / run_id
        run.mkdir()
        (run / "metadata.json").write_text(json.dumps(m))
        (run / "summary.parquet").write_bytes(b"")
    (tmp_path / "20240103_000000").mkdir()  # no summary: skipped
    assert find_base_run(tmp_path, config).name == "20240101_000000"


def test_shared_load_start_uses_summary_end_dates(tmp_path):
    pd.DataFrame({"factor_name": ["a", "b"], "end_date": ["20240315", "20240101"]}).to_parquet(
        tmp_path / "summary.parquet"
    )
    assert shared_load_start(tmp_path, _config()) == "20240220"  # 20240315 - (2*2+20) days
    assert shared_load_start(tmp_path, _config(factor_names=("zzz",))) == "20160101"


def test_chunk_start_and_merge_clean():
    dates = pd.bdate_range("2024-01-01", periods=5)
    index = pd.MultiIndex.from_product([dates, ["A", "B"]], names=["date", "asset"])
    base = pd.DataFrame(
        {"1D": np.arange(10.0), "factor": np.arange(10.0), "factor_quantile": [1, 2] * 5},
        index=index,
    )
    start = chunk_start(base, 2)
    assert start == dates[3]
    chunk = base[base.index.get_level_values("date") >= start] * 1
    chunk["factor_quantile"] = chunk["factor_quantile"].astype(float)
    merged = merge_clean(base, chunk, start)
    pd.testing.assert_frame_equal(merged, base)
