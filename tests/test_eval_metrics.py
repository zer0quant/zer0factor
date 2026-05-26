import math

import pandas as pd
import pytest

from zer0factor.eval.metrics import build_summary, calculate_long_short_spread

EXPECTED_SUMMARY_COLUMNS = [
    "factor_name",
    "return_type",
    "period",
    "sample_count",
    "start_date",
    "end_date",
    "quantiles",
    "IC Mean",
    "IC Std",
    "adjusted_ICIR",
    "adjusted_t-stat",
    "directional_IC>0 %",
    "mean_return_q1",
    "mean_return_qN",
    "long_short_spread",
    "long_short_spread_bps",
]


def test_calculate_long_short_spread_uses_highest_minus_lowest_quantile():
    quantile_returns = pd.DataFrame(
        {
            "1D": [0.001, 0.002, 0.004],
            "5D": [0.005, 0.006, 0.009],
        },
        index=pd.Index([1, 2, 3], name="factor_quantile"),
    )

    result = calculate_long_short_spread(quantile_returns)

    assert result["1D"] == pytest.approx(0.003)
    assert result["5D"] == pytest.approx(0.004)


def test_build_summary_has_one_row_per_period_and_required_fields():
    daily_ic = pd.DataFrame(
        {
            "1D": [0.1, 0.2, -0.1, 0.0],
            "5D": [0.2, 0.3, 0.1, -0.2],
        },
        index=pd.date_range("2024-01-01", periods=4),
    )
    quantile_returns = pd.DataFrame(
        {
            "1D": [0.001, 0.004],
            "5D": [0.002, 0.008],
        },
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=100,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-31"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    expected_ic_std = pd.Series([0.1, 0.2, -0.1, 0.0]).std()
    expected_adjusted_icir = 0.05 / expected_ic_std

    assert all(col in result.columns for col in EXPECTED_SUMMARY_COLUMNS)
    assert result["period"].tolist() == ["1D", "5D"]
    assert result.loc[0, "factor_name"] == "factor_a"
    assert result.loc[0, "return_type"] == "open_t1"
    assert result.loc[0, "sample_count"] == 100
    assert result.loc[0, "start_date"] == "20240101"
    assert result.loc[0, "end_date"] == "20240131"
    assert result.loc[0, "quantiles"] == 10
    assert result.loc[0, "IC Mean"] == pytest.approx(0.05)
    assert result.loc[0, "IC Std"] == pytest.approx(expected_ic_std)
    assert result.loc[0, "adjusted_ICIR"] == pytest.approx(expected_adjusted_icir)
    assert result.loc[0, "adjusted_t-stat"] == pytest.approx(expected_adjusted_icir * math.sqrt(4))
    assert "ICIR" not in result.columns
    assert "t-stat" not in result.columns
    assert result.loc[0, "directional_IC>0 %"] == pytest.approx(50.0)
    assert "IC>0 %" not in result.columns
    assert result.loc[0, "mean_return_q1"] == pytest.approx(0.001)
    assert result.loc[0, "mean_return_qN"] == pytest.approx(0.004)
    assert result.loc[0, "long_short_spread"] == pytest.approx(0.003)
    assert result.loc[0, "long_short_spread_bps"] == pytest.approx(30.0)
    assert result.loc[0, "monotonicity"] == pytest.approx(1.0)


def test_build_summary_aligns_long_short_spread_with_negative_ic_direction():
    daily_ic = pd.DataFrame(
        {"1D": [-0.1, -0.2, -0.3]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    quantile_returns = pd.DataFrame(
        {"1D": [-0.001, -0.004]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=3,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-03"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert result.loc[0, "factor_direction"] == -1
    assert result.loc[0, "adjusted_ICIR"] == pytest.approx(2.0)
    assert result.loc[0, "adjusted_t-stat"] > 0
    assert result.loc[0, "directional_IC>0 %"] == pytest.approx(100.0)
    assert result.loc[0, "long_quantile"] == 1
    assert result.loc[0, "short_quantile"] == 10
    assert result.loc[0, "long_short_spread"] == pytest.approx(0.003)
    assert result.loc[0, "long_short_spread_bps"] == pytest.approx(30.0)
    assert "raw_quantile_spread" not in result.columns
    assert "raw_quantile_spread_bps" not in result.columns


def test_build_summary_direction_adjusts_weekly_and_monthly_ic_win_rates():
    daily_ic = pd.DataFrame(
        {"1D": [-0.1] * 10},
        index=pd.date_range("2024-01-01", periods=10, freq="D"),
    )
    quantile_returns = pd.DataFrame(
        {"1D": [-0.001, -0.004]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=10,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-10"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert result.loc[0, "directional_IC>0 %(W)"] == pytest.approx(100.0)
    assert result.loc[0, "directional_IC>0 %(M)"] == pytest.approx(100.0)
    assert "IC>0 %(W)" not in result.columns
    assert "IC>0 %(M)" not in result.columns


def test_build_summary_uses_period_sample_counts_when_provided():
    daily_ic = pd.DataFrame(
        {
            "1D": [0.1, 0.2, 0.3, 0.4],
            "5D": [0.1, 0.2, None, None],
        },
        index=pd.date_range("2024-01-01", periods=4),
    )
    quantile_returns = pd.DataFrame(
        {
            "1D": [0.001, 0.004],
            "5D": [0.002, 0.008],
        },
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=4,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-04"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        period_sample_counts={"1D": 40, "5D": 20},
    )

    assert result.loc[result["period"].eq("1D"), "sample_count"].iloc[0] == 40
    assert result.loc[result["period"].eq("5D"), "sample_count"].iloc[0] == 20


def test_build_summary_uses_hac_t_stat_for_overlapping_periods():
    daily_ic = pd.DataFrame(
        {"5D": [0.10, 0.09, 0.08, -0.01, -0.02, -0.03]},
        index=pd.date_range("2024-01-01", periods=6),
    )
    quantile_returns = pd.DataFrame(
        {"5D": [0.001, 0.004]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=6,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-06"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    ic = daily_ic["5D"]
    naive_t_stat = ic.mean() / (ic.std() / math.sqrt(ic.count()))
    assert result.loc[0, "adjusted_t-stat"] < abs(naive_t_stat)


def test_build_summary_treats_effectively_zero_ic_std_as_undefined():
    daily_ic = pd.DataFrame(
        {"1D": [0.1, 0.1, 0.1]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    quantile_returns = pd.DataFrame(
        {"1D": [0.001, 0.004]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=3,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-03"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert result.loc[0, "IC Std"] == pytest.approx(0.0, abs=1e-15)
    assert pd.isna(result.loc[0, "adjusted_ICIR"])
    assert pd.isna(result.loc[0, "adjusted_t-stat"])


def test_build_summary_treats_single_valid_ic_stat_ratios_as_undefined():
    daily_ic = pd.DataFrame(
        {"1D": [0.1, None, None]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    quantile_returns = pd.DataFrame(
        {"1D": [0.001, 0.004]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=3,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-03"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert pd.isna(result.loc[0, "IC Std"])
    assert pd.isna(result.loc[0, "adjusted_ICIR"])
    assert pd.isna(result.loc[0, "adjusted_t-stat"])
