import math

import pandas as pd
import pytest

from zer0factor.eval.metrics.monotonicity import (
    calculate_monotonicity,
    calculate_quarterly_monotonicity_stats,
)


def make_quantile_returns(direction: int = 1):
    """Monotonically increasing quantile returns (direction=1 → positive mono)."""
    n = 5
    returns = [i * 0.001 * direction for i in range(1, n + 1)]
    return pd.Series(
        returns,
        index=pd.Index(range(1, n + 1), name="factor_quantile"),
    )


def make_mean_ret_by_date(n_dates=12, n_quantiles=5):
    """Synthetic MultiIndex (date, factor_quantile) daily returns."""
    dates = pd.date_range("2024-01-02", periods=n_dates, freq="B")
    quantiles = list(range(1, n_quantiles + 1))
    index = pd.MultiIndex.from_product([dates, quantiles], names=["date", "factor_quantile"])
    # Each quantile returns its rank × 0.001
    values = [(q * 0.001) for _ in dates for q in quantiles]
    return pd.DataFrame({"1D": values}, index=index)


def test_calculate_monotonicity_perfect_ascending_is_one():
    qr = make_quantile_returns(direction=1)
    result = calculate_monotonicity(qr, direction=1)
    assert result == pytest.approx(1.0)


def test_calculate_monotonicity_perfect_descending_with_direction_minus_one_is_one():
    qr = make_quantile_returns(direction=-1)
    result = calculate_monotonicity(qr, direction=-1)
    assert result == pytest.approx(1.0)


def test_calculate_monotonicity_single_quantile_is_nan():
    qr = pd.Series([0.001], index=pd.Index([1], name="factor_quantile"))
    assert math.isnan(calculate_monotonicity(qr, direction=1))


def test_calculate_quarterly_monotonicity_stats_keys():
    mean_ret = make_mean_ret_by_date(n_dates=60, n_quantiles=5)
    result = calculate_quarterly_monotonicity_stats(mean_ret, direction=1, period="1D")
    for key in ["monotonicity_q_mean", "monotonicity_q_ir", "monotonicity_q_pos_rate"]:
        assert key in result, f"missing key: {key}"


def test_calculate_quarterly_monotonicity_stats_few_quarters_is_nan():
    mean_ret = make_mean_ret_by_date(n_dates=5, n_quantiles=5)
    result = calculate_quarterly_monotonicity_stats(mean_ret, direction=1, period="1D")
    assert math.isnan(result["monotonicity_q_mean"])


def test_calculate_quarterly_monotonicity_pos_rate_between_0_and_100():
    mean_ret = make_mean_ret_by_date(n_dates=60, n_quantiles=5)
    result = calculate_quarterly_monotonicity_stats(mean_ret, direction=1, period="1D")
    if not math.isnan(result["monotonicity_q_pos_rate"]):
        assert 0 <= result["monotonicity_q_pos_rate"] <= 100
