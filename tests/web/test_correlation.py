import numpy as np
import pandas as pd
import pytest

from zer0factor.web.correlation import factor_correlation, sample_dates

DATES = [d.strftime("%Y%m%d") for d in pd.bdate_range("2024-01-02", periods=30)]
CODES = [f"{i:06d}.SZ" for i in range(50)]


@pytest.fixture
def store(tmp_path, make_factor_store):
    rng = np.random.default_rng(0)
    frames = {"a": [], "b": [], "c": []}
    for d in DATES:
        a = rng.normal(size=len(CODES))
        frames["a"].append(pd.DataFrame({"trade_date": d, "ts_code": CODES, "value": a}))
        b = a * 2 + rng.normal(scale=0.01, size=len(CODES))
        frames["b"].append(pd.DataFrame({"trade_date": d, "ts_code": CODES, "value": b}))
        c = rng.normal(size=len(CODES))
        frames["c"].append(pd.DataFrame({"trade_date": d, "ts_code": CODES, "value": c}))
    factor_dir = None
    for name, parts in frames.items():
        factor_dir = make_factor_store(name, pd.concat(parts))
    universe_dir = tmp_path / "universe"
    for d in DATES:
        part = universe_dir / f"date={d}"
        part.mkdir(parents=True)
        pd.DataFrame(
            {"trade_date": d, "universe": "univ_trade_base", "ts_code": CODES[:40]}
        ).to_parquet(part / "data.parquet", index=False)
    return factor_dir, universe_dir


def _full_range(*names):
    return {n: (DATES[0], DATES[-1]) for n in names}


def test_sample_dates_even_and_bounded():
    available = [d.strftime("%Y%m%d") for d in pd.bdate_range("2024-01-02", periods=100)]
    got = sample_dates(available, available[5], available[94], n=10)
    assert len(got) == 10
    assert got == sorted(got)
    assert got[0] >= available[5] and got[-1] <= available[94]
    assert got[0] == available[5] and got[-1] == available[94]
    assert sample_dates(available[:3], available[0], available[2], n=10) == available[:3]


def test_correlation_detects_duplicate_pair(store):
    factor_dir, universe_dir = store
    out = factor_correlation(["a", "b", "c"], factor_dir, universe_dir, _full_range("a", "b", "c"))
    m = np.array(out["matrix"])
    assert out["factors"] == ["a", "b", "c"]
    assert m[0, 1] > 0.95 and abs(m[0, 2]) < 0.3
    assert m[0, 0] == pytest.approx(1.0)
    pairs = {(p["a"], p["b"]) for p in out["pairs_over_threshold"]}
    assert pairs == {("a", "b")}


def test_correlation_restricts_to_universe(store):
    factor_dir, universe_dir = store
    # poison codes outside the universe in factor c so they would dominate a rank corr
    for d in DATES:
        path = factor_dir / "c" / f"date={d}" / "data.parquet"
        df = pd.read_parquet(path)
        a = pd.read_parquet(factor_dir / "a" / f"date={d}" / "data.parquet")
        df["value"] = np.where(df["ts_code"].isin(CODES[40:]), a["value"] * 100, df["value"])
        df.to_parquet(path, index=False)
    out = factor_correlation(["a", "c"], factor_dir, universe_dir, _full_range("a", "c"))
    assert abs(out["matrix"][0][1]) < 0.3


def test_correlation_uses_range_intersection(store):
    factor_dir, universe_dir = store
    ranges = {"a": (DATES[0], DATES[19]), "b": (DATES[10], DATES[-1])}
    out = factor_correlation(["a", "b"], factor_dir, universe_dir, ranges)
    assert out["dates_used"] == 10
