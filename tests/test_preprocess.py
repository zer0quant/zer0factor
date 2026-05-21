import pandas as pd

from zer0factor.preprocess import winsorize


def _panel(values: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        values,
        index=pd.date_range("2024-01-01", periods=len(values), freq="D"),
        columns=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
    )


def test_mad_winsorization_clips_extreme_cross_sectional_value():
    factor = _panel([[1.0, 2.0, 3.0, 100.0]])

    result = winsorize(factor, method="mad", n=2.0)

    assert result.loc[pd.Timestamp("2024-01-01"), "000004.SZ"] == 5.5
    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 1.0


def test_quantile_winsorization_clips_to_configured_quantiles():
    factor = _panel([[1.0, 2.0, 3.0, 100.0]])

    result = winsorize(factor, method="quantile", lower_quantile=0.25, upper_quantile=0.75)

    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 1.75
    assert result.loc[pd.Timestamp("2024-01-01"), "000004.SZ"] == 27.25


def test_mad_winsorization_skips_zero_mad_rows():
    factor = _panel([[1.0, 1.0, 1.0, 50.0]])

    result = winsorize(factor, method="mad", n=5.0)

    pd.testing.assert_frame_equal(result, factor)
