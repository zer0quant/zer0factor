import pandas as pd
import pytest

from zer0factor.eval.metrics.ic import (
    calculate_ic_freq_win_rates,
    calculate_ic_near_far_ratio,
)


def make_daily_ic():
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    return pd.DataFrame(
        {
            "1D": [0.1 if i % 3 != 0 else -0.1 for i in range(60)],
            "5D": [-0.05 if i % 4 == 0 else 0.05 for i in range(60)],
        },
        index=dates,
    )


def test_calculate_ic_freq_win_rates_returns_weekly_and_monthly():
    daily_ic = make_daily_ic()
    result = calculate_ic_freq_win_rates(daily_ic)
    assert "weekly" in result
    assert "monthly" in result
    assert set(result["weekly"].index) == {"1D", "5D"}
    assert set(result["monthly"].index) == {"1D", "5D"}


def test_calculate_ic_freq_win_rates_weekly_between_0_and_100():
    daily_ic = make_daily_ic()
    result = calculate_ic_freq_win_rates(daily_ic)
    assert (result["weekly"] >= 0).all()
    assert (result["weekly"] <= 100).all()


def test_calculate_ic_freq_win_rates_all_positive_ic_gives_100_pct():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    daily_ic = pd.DataFrame({"1D": [0.05] * 20}, index=dates)
    result = calculate_ic_freq_win_rates(daily_ic)
    assert result["weekly"]["1D"] == pytest.approx(100.0)
    assert result["monthly"]["1D"] == pytest.approx(100.0)


def test_calculate_ic_near_far_ratio_returns_series_indexed_by_period():
    daily_ic = make_daily_ic()
    result = calculate_ic_near_far_ratio(daily_ic)
    assert isinstance(result, pd.Series)
    assert set(result.index) == {"1D", "5D"}


def test_calculate_ic_near_far_ratio_is_nan_when_all_ic_is_zero():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    daily_ic = pd.DataFrame({"1D": [0.0] * 20}, index=dates)
    result = calculate_ic_near_far_ratio(daily_ic)
    assert pd.isna(result["1D"])


def test_build_summary_includes_ic_freq_and_ratio_columns():
    from zer0factor.eval.metrics import build_summary

    daily_ic = make_daily_ic()
    quantile_returns = pd.DataFrame(
        {"1D": [0.001, 0.004], "5D": [0.002, 0.006]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )
    result = build_summary(
        factor_name="f",
        return_type="open_t1",
        clean_factor_data_sample_count=100,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-03-31"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )
    for col in ["directional_IC>0 %(W)", "directional_IC>0 %(M)", "IC_near_far_ratio"]:
        assert col in result.columns, f"missing column: {col}"
    assert "IC>0 %(W)" not in result.columns
    assert "IC>0 %(M)" not in result.columns
