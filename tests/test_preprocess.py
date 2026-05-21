import numpy as np
import pandas as pd
import pytest

from zer0factor.preprocess import impute_missing, winsorize


def _panel(values: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        values,
        index=pd.date_range("2024-01-01", periods=len(values), freq="D"),
        columns=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"][
            : len(values[0])
        ],
    )


def test_mad_winsorization_clips_extreme_cross_sectional_value():
    factor = _panel([[1.0, 2.0, 3.0, 100.0]])

    result = winsorize(factor, method="mad", n=2.0)

    assert result.loc[pd.Timestamp("2024-01-01"), "000004.SZ"] == 4.5
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


def test_winsorization_none_returns_copy():
    factor = _panel([[1.0, 2.0, 3.0]])

    result = winsorize(factor, method="none")

    assert result is not factor
    pd.testing.assert_frame_equal(result, factor)


def test_winsorization_rejects_non_positive_mad_multiplier():
    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError, match="n must be positive"):
        winsorize(factor, method="mad", n=0.0)


def test_winsorization_rejects_invalid_quantile_bounds():
    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError, match="0 <= lower < upper <= 1"):
        winsorize(
            factor,
            method="quantile",
            lower_quantile=0.9,
            upper_quantile=0.1,
        )


def test_winsorization_rejects_unknown_method():
    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError, match="unknown winsorization method"):
        winsorize(factor, method="unsupported")


def test_cross_section_median_imputation_fills_per_date():
    factor = _panel([[1.0, np.nan, 3.0], [np.nan, 10.0, 14.0]])

    result = impute_missing(factor, method="cross_section_median")

    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 2.0
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 12.0


def test_imputation_treats_infinite_values_as_missing():
    factor = _panel([[1.0, np.inf, 3.0]])

    result = impute_missing(factor, method="cross_section_median")

    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 2.0


def test_imputation_handles_duplicate_index_labels_by_row_position():
    factor = pd.DataFrame(
        [[1.0, np.nan, 3.0], [np.nan, 10.0, 14.0]],
        index=pd.to_datetime(["2024-01-01", "2024-01-01"]),
        columns=["000001.SZ", "000002.SZ", "000003.SZ"],
    )

    result = impute_missing(factor, method="cross_section_median")

    assert result.iloc[0]["000002.SZ"] == 2.0
    assert result.iloc[1]["000001.SZ"] == 12.0


def test_entirely_missing_rows_remain_missing_after_imputation():
    factor = _panel([[np.nan, np.nan, np.nan]])

    result = impute_missing(factor, method="cross_section_median")

    assert result.loc[pd.Timestamp("2024-01-01")].isna().all()


def test_industry_median_imputation_without_industry_data_raises():
    factor = _panel([[1.0, np.nan, 3.0]])

    with pytest.raises(ValueError, match="industry_median imputation requires industry data"):
        impute_missing(factor, method="industry_median")
