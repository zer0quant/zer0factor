import math

import pandas as pd
import pytest

from zer0factor.eval.metrics import build_summary, calculate_long_short_spread


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

    expected_columns = {
        "factor_name",
        "return_type",
        "period",
        "sample_count",
        "start_date",
        "end_date",
        "quantiles",
        "IC Mean",
        "IC Std",
        "ICIR",
        "t-stat",
        "IC>0 %",
        "mean_return_q1",
        "mean_return_qN",
        "long_short_spread",
        "long_short_spread_bps",
    }
    expected_ic_std = pd.Series([0.1, 0.2, -0.1, 0.0]).std()
    expected_icir = 0.05 / expected_ic_std

    assert expected_columns.issubset(result.columns)
    assert result["period"].tolist() == ["1D", "5D"]
    assert result.loc[0, "factor_name"] == "factor_a"
    assert result.loc[0, "return_type"] == "open_t1"
    assert result.loc[0, "sample_count"] == 100
    assert result.loc[0, "start_date"] == "20240101"
    assert result.loc[0, "end_date"] == "20240131"
    assert result.loc[0, "quantiles"] == 10
    assert result.loc[0, "IC Mean"] == pytest.approx(0.05)
    assert result.loc[0, "IC Std"] == pytest.approx(expected_ic_std)
    assert result.loc[0, "ICIR"] == pytest.approx(expected_icir)
    assert result.loc[0, "t-stat"] == pytest.approx(expected_icir * math.sqrt(4))
    assert result.loc[0, "IC>0 %"] == pytest.approx(50.0)
    assert result.loc[0, "mean_return_q1"] == pytest.approx(0.001)
    assert result.loc[0, "mean_return_qN"] == pytest.approx(0.004)
    assert result.loc[0, "long_short_spread"] == pytest.approx(0.003)
    assert result.loc[0, "long_short_spread_bps"] == pytest.approx(30.0)
