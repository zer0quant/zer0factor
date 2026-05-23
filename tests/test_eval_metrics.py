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

    assert result["period"].tolist() == ["1D", "5D"]
    assert result.loc[0, "factor_name"] == "factor_a"
    assert result.loc[0, "return_type"] == "open_t1"
    assert result.loc[0, "sample_count"] == 100
    assert result.loc[0, "IC Mean"] == pytest.approx(0.05)
    assert result.loc[0, "IC>0 %"] == pytest.approx(50.0)
    assert result.loc[0, "mean_return_q1"] == pytest.approx(0.001)
    assert result.loc[0, "mean_return_qN"] == pytest.approx(0.004)
    assert result.loc[0, "long_short_spread"] == pytest.approx(0.003)
    assert result.loc[0, "long_short_spread_bps"] == pytest.approx(30.0)
