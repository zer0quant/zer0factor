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


def _trading_days(cfd: pd.DataFrame) -> pd.DatetimeIndex:
    return cfd.index.get_level_values("date").unique()


@pytest.mark.parametrize("period", ["1D", "5D"])
def test_daily_returns_only_cover_trading_days(period):
    # create_pyfolio_input resamples to calendar days; weekends must not survive.
    cfd = make_clean_factor_data()
    r = build_portfolio_daily_returns(
        cfd, direction=1, period=period, long_quantile=5, short_quantile=1,
        transaction_cost_bps=10,
    )
    trading_days = _trading_days(cfd)
    for name in ["long", "short", "ls", "full", "benchmark", "ls_benchmark", "full_benchmark"]:
        series = getattr(r, name)
        assert series.index.isin(trading_days).all(), name
        assert (series.index.dayofweek < 5).all(), name
    for name in ["long_positions", "short_positions", "ls_positions", "full_positions"]:
        assert getattr(r, name).index.isin(trading_days).all(), name


def test_ann_ret_annualizes_over_trading_days():
    # 80 business days: annual return must use 252 / 80, not 252 / calendar-day count.
    cfd = make_clean_factor_data()
    n = len(_trading_days(cfd))
    kwargs = dict(direction=1, period="1D", long_quantile=5, short_quantile=1)
    r = build_portfolio_daily_returns(cfd, **kwargs)
    metrics = build_pyfolio_return_metrics(cfd, **kwargs)
    for prefix in ["long", "short", "ls", "full"]:
        series = getattr(r, prefix)
        expected = (1 + series).prod() ** (252 / n) - 1
        assert metrics[f"{prefix}_ann_ret"] == pytest.approx(expected, rel=1e-10), prefix


def test_transaction_costs_ignore_non_trading_days():
    # Fixed quantile membership means zero real turnover, so costs must be zero.
    cfd = make_clean_factor_data()
    assets = cfd.index.get_level_values("asset")
    asset_rank = pd.Series(range(len(assets.unique())), index=assets.unique())
    cfd["factor"] = asset_rank.reindex(assets).to_numpy(dtype=float)
    cfd["factor_quantile"] = (
        pd.qcut(asset_rank, 5, labels=False).reindex(assets).to_numpy() + 1
    )
    kwargs = dict(direction=1, period="1D", long_quantile=5, short_quantile=1)
    gross = build_portfolio_daily_returns(cfd, **kwargs)
    net = build_portfolio_daily_returns(cfd, transaction_cost_bps=10, **kwargs)
    for name in ["long", "short", "ls"]:
        # the first day is the initial build-up of the book
        pd.testing.assert_series_equal(
            getattr(net, name).iloc[1:], getattr(gross, name).iloc[1:], check_names=False
        )
