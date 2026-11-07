import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from tests.eval_fixtures import make_clean_factor_data
from zer0factor.eval.metrics.returns import build_portfolio_daily_returns
from zer0factor.eval.series import (
    SERIES_FILES,
    build_chart_series,
    pearson_daily_ic,
    portfolio_daily_returns,
    quantile_daily_returns,
    read_chart_series,
    write_chart_series,
)


def _summary(direction=1, long_q=5, short_q=1, periods=("1D", "5D"), cost=10.0):
    return pd.DataFrame(
        [
            {
                "factor_name": "fa",
                "period": p,
                "factor_direction": direction,
                "long_quantile": float(long_q),
                "short_quantile": float(short_q),
                "transaction_cost_bps": cost,
            }
            for p in periods
        ]
    )


def test_quantile_daily_returns_matches_groupby_mean():
    cfd = make_clean_factor_data()
    got = quantile_daily_returns(cfd, "1D")
    expected = cfd.groupby(["date", "factor_quantile"])["1D"].mean().unstack()
    assert list(got.columns) == [1, 2, 3, 4, 5]
    np.testing.assert_allclose(got.to_numpy(), expected.to_numpy())


def test_quantile_daily_returns_converts_multi_day_period():
    cfd = make_clean_factor_data()
    got = quantile_daily_returns(cfd, "5D")
    mean = cfd.groupby(["date", "factor_quantile"])["5D"].mean().unstack()
    np.testing.assert_allclose(got.to_numpy(), ((1 + mean) ** (1 / 5) - 1).to_numpy())


def test_pearson_daily_ic_equals_manual():
    cfd = make_clean_factor_data()
    got = pearson_daily_ic(cfd)
    first = cfd.index.get_level_values("date")[0]
    day = cfd.xs(first, level="date")
    assert list(got.columns) == ["1D", "5D"]
    assert got.loc[first, "1D"] == pytest.approx(np.corrcoef(day["factor"], day["1D"])[0, 1])


def test_portfolio_daily_returns_uses_summary_row():
    cfd = make_clean_factor_data()
    row = _summary(direction=-1, long_q=1, short_q=5).iloc[0].to_dict()
    got = portfolio_daily_returns(cfd, row)
    expected = build_portfolio_daily_returns(
        cfd, direction=-1, period="1D", long_quantile=1, short_quantile=5,
        transaction_cost_bps=10.0,
    )
    assert list(got.columns) == ["long", "short", "ls", "benchmark"]
    assert_series_equal(got["ls"], expected.ls, check_names=False)


def test_build_chart_series_prefixes_columns_by_period():
    series = build_chart_series(make_clean_factor_data(), _summary())
    assert set(series) == {f.removesuffix(".parquet") for f in SERIES_FILES}
    assert "1D:3" in series["quantile_daily_returns"].columns
    assert "5D:ls" in series["portfolio_daily_returns"].columns


def test_build_chart_series_tolerates_portfolio_failure():
    cfd = make_clean_factor_data(n_dates=3, n_assets=4, quantiles=2)
    series = build_chart_series(cfd, _summary(long_q=2, short_q=1, periods=("1D",)))
    assert "1D:1" in series["quantile_daily_returns"].columns
    assert "portfolio_daily_returns" in series


def test_write_then_read_roundtrip(tmp_path):
    series = build_chart_series(make_clean_factor_data(), _summary())
    write_chart_series(tmp_path, series)
    back = read_chart_series(tmp_path)
    assert back is not None
    for name, frame in series.items():
        assert_frame_equal(back[name], frame, check_freq=False)


def test_read_returns_none_when_any_file_missing(tmp_path):
    write_chart_series(tmp_path, build_chart_series(make_clean_factor_data(), _summary()))
    (tmp_path / SERIES_FILES[0]).unlink()
    assert read_chart_series(tmp_path) is None


def test_write_leaves_no_tmp_files(tmp_path):
    write_chart_series(tmp_path, build_chart_series(make_clean_factor_data(), _summary()))
    assert not list(tmp_path.glob("*.tmp-*"))
