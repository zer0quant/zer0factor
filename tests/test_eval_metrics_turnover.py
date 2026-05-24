import pandas as pd
import pytest

from zer0factor.eval.metrics.turnover import calculate_quantile_turnover


def make_clean_factor_data():
    """3 dates × 4 assets, quantiles 1..4."""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    assets = ["A", "B", "C", "D"]
    index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    return pd.DataFrame(
        {
            "factor": [1.0, 2.0, 3.0, 4.0] * 3,
            "factor_quantile": [1, 2, 3, 4] * 3,
            "1D": [0.01] * 12,
        },
        index=index,
    )


def test_calculate_quantile_turnover_returns_expected_keys():
    cfd = make_clean_factor_data()
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    for key in ["turnover_daily_long", "turnover_annual_long",
                "turnover_daily_short", "turnover_annual_short"]:
        assert key in result, f"missing key: {key}"


def test_calculate_quantile_turnover_zero_when_holdings_unchanged():
    """Same stocks in quantile every day → turnover = 0."""
    cfd = make_clean_factor_data()
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    assert result["turnover_daily_long"] == pytest.approx(0.0)
    assert result["turnover_daily_short"] == pytest.approx(0.0)


def test_calculate_quantile_turnover_annual_equals_daily_times_252_over_period():
    cfd = make_clean_factor_data()
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    expected_annual = result["turnover_daily_long"] * 252 / 1
    assert result["turnover_annual_long"] == pytest.approx(expected_annual)


def test_calculate_quantile_turnover_full_turnover_when_all_stocks_change():
    dates = pd.date_range("2024-01-02", periods=2, freq="B")
    # Day 1: A,B in q4; Day 2: C,D in q4 — complete turnover
    index = pd.MultiIndex.from_tuples(
        [(dates[0], "A"), (dates[0], "B"), (dates[0], "C"), (dates[0], "D"),
         (dates[1], "A"), (dates[1], "B"), (dates[1], "C"), (dates[1], "D")],
        names=["date", "asset"],
    )
    cfd = pd.DataFrame(
        {
            "factor": [1.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0],
            "factor_quantile": [1, 2, 3, 4, 4, 3, 2, 1],
            "1D": [0.01] * 8,
        },
        index=index,
    )
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    assert result["turnover_daily_long"] == pytest.approx(1.0)
