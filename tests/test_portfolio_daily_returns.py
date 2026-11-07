import json
from pathlib import Path

import pandas as pd
import pyfolio as pf
import pytest

from tests.eval_fixtures import make_clean_factor_data
from zer0factor.eval.metrics.returns import (
    build_portfolio_daily_returns,
    build_pyfolio_return_metrics,
)

SNAPSHOT_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "pyfolio_metrics_snapshot.json").read_text()
)


@pytest.mark.parametrize("case", SNAPSHOT_CASES, ids=lambda c: c["kwargs"]["period"])
def test_metrics_unchanged_after_refactor(case):
    got = build_pyfolio_return_metrics(make_clean_factor_data(), **case["kwargs"])
    assert set(got) == set(case["expected"])
    for key, value in case["expected"].items():
        if value is None:
            assert pd.isna(got[key]), key
        else:
            assert got[key] == pytest.approx(value, rel=1e-12, abs=1e-15), key


def test_daily_returns_reproduce_ls_ann_ret():
    cfd = make_clean_factor_data()
    kwargs = dict(
        direction=1, period="1D", long_quantile=5, short_quantile=1, transaction_cost_bps=10
    )
    r = build_portfolio_daily_returns(cfd, **kwargs)
    metrics = build_pyfolio_return_metrics(cfd, **kwargs)
    assert pf.timeseries.perf_stats(r.ls)["Annual return"] == pytest.approx(
        metrics["ls_ann_ret"]
    )
    assert r.long.index.equals(r.short.index)


def test_daily_returns_can_skip_full_portfolio():
    cfd = make_clean_factor_data()
    kwargs = dict(direction=1, period="1D", long_quantile=5, short_quantile=1)
    lean = build_portfolio_daily_returns(cfd, include_full=False, **kwargs)
    full = build_portfolio_daily_returns(cfd, **kwargs)
    assert lean.full is None and lean.full_positions is None
    pd.testing.assert_series_equal(lean.ls, full.ls)
