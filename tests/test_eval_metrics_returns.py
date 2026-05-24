import math

import numpy as np
import pandas as pd
import pytest

from zer0factor.eval.metrics.returns import (
    annualized_return,
    max_drawdown,
    sharpe_ratio,
    calmar_ratio,
    detect_direction,
    build_group_return_metrics,
)


def make_daily_returns(n=252, seed=42):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.001, 0.01, n))


def test_detect_direction_positive_ic_gives_plus_one():
    daily_ic = pd.DataFrame(
        {"1D": [0.1, 0.2, 0.05]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == 1


def test_detect_direction_negative_ic_gives_minus_one():
    daily_ic = pd.DataFrame(
        {"1D": [-0.1, -0.2, -0.05]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == -1


def test_detect_direction_zero_ic_gives_plus_one():
    daily_ic = pd.DataFrame(
        {"1D": [0.0, 0.0, 0.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == 1


def test_annualized_return_constant_positive_return():
    daily = pd.Series([0.001] * 252)
    result = annualized_return(daily)
    expected = (1.001**252) - 1
    assert result == pytest.approx(expected, rel=1e-6)


def test_annualized_return_empty_series_is_nan():
    assert math.isnan(annualized_return(pd.Series([], dtype=float)))


def test_max_drawdown_no_drawdown_is_zero():
    daily = pd.Series([0.01] * 10)
    assert max_drawdown(daily) == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_single_loss():
    daily = pd.Series([0.1, -0.5, 0.1])
    result = max_drawdown(daily)
    assert result < 0


def test_sharpe_ratio_zero_std_is_nan():
    daily = pd.Series([0.001] * 10)
    assert math.isnan(sharpe_ratio(daily))


def test_sharpe_ratio_positive_returns():
    rng = np.random.default_rng(0)
    daily = pd.Series(abs(rng.normal(0.001, 0.01, 252)))
    result = sharpe_ratio(daily)
    assert result > 0


def test_calmar_ratio_no_drawdown_is_nan():
    daily = pd.Series([0.01] * 252)
    assert math.isnan(calmar_ratio(daily))


def test_build_group_return_metrics_keys_present():
    mean_ret = pd.DataFrame(
        {
            "1D": [0.001, 0.0015, 0.0005],
            "5D": [0.003, 0.004, 0.002],
        },
        index=pd.MultiIndex.from_product(
            [pd.date_range("2024-01-02", periods=1), [1, 5, 10]],
            names=["date", "factor_quantile"],
        ),
    )
    result = build_group_return_metrics(
        mean_ret_by_date=mean_ret,
        mean_ret_by_date_demeaned=mean_ret,
        direction=1,
        period="1D",
        n_quantiles=10,
    )
    expected_keys = [
        "long_ann_ret", "long_max_dd", "long_calmar", "long_sharpe",
        "short_ann_ret", "short_max_dd", "short_calmar", "short_sharpe",
        "ls_ann_ret", "ls_max_dd", "ls_calmar", "ls_sharpe",
        "long_exc_ann_ret", "long_exc_max_dd", "long_exc_calmar", "long_exc_sharpe",
        "ls_ann_ret_ratio",
    ]
    for key in expected_keys:
        assert key in result, f"missing key: {key}"


def test_build_group_return_metrics_direction_minus_one_flips_groups():
    mean_ret = pd.DataFrame(
        {"1D": [0.001, 0.002]},
        index=pd.MultiIndex.from_product(
            [pd.date_range("2024-01-02", periods=1), [1, 2]],
            names=["date", "factor_quantile"],
        ),
    )
    result_pos = build_group_return_metrics(mean_ret, mean_ret, direction=1, period="1D", n_quantiles=2)
    result_neg = build_group_return_metrics(mean_ret, mean_ret, direction=-1, period="1D", n_quantiles=2)
    # direction=+1: long=q2, short=q1; direction=-1: long=q1, short=q2
    assert result_pos["long_ann_ret"] != result_neg["long_ann_ret"]
