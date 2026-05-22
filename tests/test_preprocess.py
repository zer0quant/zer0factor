import numpy as np
import pandas as pd
import pytest

from zer0factor.preprocess import (
    FactorPreprocessPipeline,
    PreprocessConfig,
    impute_missing,
    neutralize,
    standardize,
    winsorize,
)


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


def test_zscore_standardization_has_cross_sectional_mean_zero_and_std_one():
    factor = _panel([[1.0, 2.0, 3.0]])

    result = standardize(factor, method="zscore")

    row = result.loc[pd.Timestamp("2024-01-01")]
    assert row.mean() == pytest.approx(0.0)
    assert row.std() == pytest.approx(1.0)


def test_zscore_standardization_returns_nan_for_zero_std_rows():
    factor = _panel([[1.0, 1.0, 1.0]])

    result = standardize(factor, method="zscore")

    assert result.loc[pd.Timestamp("2024-01-01")].isna().all()


def test_zscore_standardization_preserves_missing_and_ignores_infinite_values():
    factor = _panel([[1.0, np.nan, np.inf, 3.0]])

    result = standardize(factor, method="zscore")

    row = result.loc[pd.Timestamp("2024-01-01")]
    assert row["000001.SZ"] == pytest.approx(-0.7071067811865475)
    assert pd.isna(row["000002.SZ"])
    assert pd.isna(row["000003.SZ"])
    assert row["000004.SZ"] == pytest.approx(0.7071067811865475)


def test_standardization_none_returns_cleaned_copy():
    factor = _panel([[1.0, np.inf, 3.0]])

    result = standardize(factor, method="none")

    assert result is not factor
    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 1.0
    assert pd.isna(result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"])


def test_standardization_rejects_unknown_method():
    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError, match="unknown standardization method"):
        standardize(factor, method="unsupported")


def test_rank_standardization_outputs_percentile_ranks():
    factor = _panel([[10.0, 30.0, 20.0]])

    result = standardize(factor, method="rank_pct")

    row = result.loc[pd.Timestamp("2024-01-01")]
    assert row["000001.SZ"] == pytest.approx(1 / 3)
    assert row["000003.SZ"] == pytest.approx(2 / 3)
    assert row["000002.SZ"] == pytest.approx(1.0)


def test_size_industry_neutralization_removes_size_and_industry_exposure():
    factor = pd.DataFrame(
        [[11.0, 13.0, 17.0, 19.0, 23.0, 29.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=[
            "000001.SZ",
            "000002.SZ",
            "000003.SZ",
            "000004.SZ",
            "000005.SZ",
            "000006.SZ",
        ],
    )
    size = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
        index=factor.index,
        columns=factor.columns,
    )
    industry = pd.DataFrame(
        [["bank", "bank", "tech", "tech", "energy", "energy"]],
        index=factor.index,
        columns=factor.columns,
    )

    result = neutralize(
        factor,
        method="size_industry",
        exposures={"size": size, "industry": industry},
    )

    valid = result.loc[pd.Timestamp("2024-01-01")].dropna()
    design = pd.DataFrame(
        {
            "intercept": 1.0,
            "size": size.loc[pd.Timestamp("2024-01-01"), valid.index],
        },
        index=valid.index,
    )
    dummies = pd.get_dummies(
        industry.loc[pd.Timestamp("2024-01-01"), valid.index],
        drop_first=True,
        dtype=float,
    )
    design = pd.concat([design, dummies], axis=1)

    assert abs(valid.sum()) < 1e-10
    assert np.abs(design.T.to_numpy() @ valid.to_numpy()).max() < 1e-10


def test_size_industry_neutralization_requires_exposures():
    factor = _panel([[1.0, 2.0, 3.0]])
    size = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(
        ValueError,
        match="size_industry neutralization requires size and industry",
    ):
        neutralize(factor, method="size_industry", exposures={"size": size})


def test_size_industry_neutralization_returns_nan_when_rows_are_insufficient():
    factor = _panel([[1.0, 2.0, 3.0]])
    size = _panel([[1.0, 2.0, 3.0]])
    industry = pd.DataFrame(
        [["bank", "tech", "energy"]],
        index=factor.index,
        columns=factor.columns,
    )

    result = neutralize(
        factor,
        method="size_industry",
        exposures={"size": size, "industry": industry},
    )

    assert result.loc[pd.Timestamp("2024-01-01")].isna().all()


def test_size_industry_neutralization_preserves_factor_axes():
    factor = _panel([[1.0, 2.0, 3.0, 4.0]])
    size = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0, 5.0]],
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        columns=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "999999.SZ"],
    )
    industry = pd.DataFrame(
        [["bank", "bank", "tech", "tech", "other"], ["bank", "bank", "tech", "tech", "other"]],
        index=size.index,
        columns=size.columns,
    )

    result = neutralize(
        factor,
        method="size_industry",
        exposures={"size": size, "industry": industry},
    )

    assert list(result.index) == list(factor.index)
    assert list(result.columns) == list(factor.columns)


def test_size_industry_neutralization_rejects_duplicate_axes():
    factor = pd.DataFrame(
        [[1.0, 2.0], [3.0, 4.0]],
        index=pd.to_datetime(["2024-01-01", "2024-01-01"]),
        columns=["000001.SZ", "000002.SZ"],
    )
    size = factor.copy()
    industry = pd.DataFrame(
        [["bank", "tech"], ["bank", "tech"]],
        index=factor.index,
        columns=factor.columns,
    )

    with pytest.raises(ValueError, match="duplicate index labels"):
        neutralize(
            factor,
            method="size_industry",
            exposures={"size": size, "industry": industry},
        )

    factor = pd.DataFrame(
        [[1.0, 2.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=["000001.SZ", "000001.SZ"],
    )
    size = factor.copy()
    industry = pd.DataFrame([["bank", "tech"]], index=factor.index, columns=factor.columns)

    with pytest.raises(ValueError, match="duplicate column labels"):
        neutralize(
            factor,
            method="size_industry",
            exposures={"size": size, "industry": industry},
        )


def test_neutralization_none_returns_copy():
    factor = _panel([[1.0, 2.0, 3.0]])

    result = neutralize(factor, method="none")

    assert result is not factor
    pd.testing.assert_frame_equal(result, factor)


def test_neutralization_default_returns_copy():
    factor = _panel([[1.0, 2.0, 3.0]])

    result = neutralize(factor)

    assert result is not factor
    pd.testing.assert_frame_equal(result, factor)


def test_neutralization_rejects_unknown_method():
    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError, match="unknown neutralization method"):
        neutralize(factor, method="unsupported")


def test_pipeline_applies_winsorize_impute_standardize_in_fixed_order():
    factor = _panel([[1.0, 2.0, np.nan, 100.0]])
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="mad",
            winsorize_n=2.0,
            impute_method="cross_section_median",
            standardize_method="zscore",
            neutralize_method=None,
        )
    )

    result = pipeline.transform(factor)

    row = result.loc[pd.Timestamp("2024-01-01")]
    assert not row.isna().any()
    assert row.mean() == pytest.approx(0.0)
    assert row.std() == pytest.approx(1.0)


def test_pipeline_long_input_returns_standard_long_output():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240101", "20240101"],
            "ts_code": ["000002.SZ", "000001.SZ", "000003.SZ"],
            "value": [2.0, 1.0, 3.0],
        }
    )
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="rank_pct",
            neutralize_method=None,
        )
    )

    result = pipeline.transform(factor)

    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result.iloc[0].to_dict() == {
        "trade_date": "20240101",
        "ts_code": "000001.SZ",
        "value": pytest.approx(1 / 3),
    }
    assert result.iloc[1].to_dict() == {
        "trade_date": "20240101",
        "ts_code": "000002.SZ",
        "value": pytest.approx(2 / 3),
    }
    assert result.iloc[2].to_dict() == {
        "trade_date": "20240101",
        "ts_code": "000003.SZ",
        "value": pytest.approx(1.0),
    }


def test_pipeline_size_industry_neutralization_preserves_long_output():
    stocks = [
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
        "000004.SZ",
        "000005.SZ",
        "000006.SZ",
    ]
    factor = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": stocks,
            "value": [11.0, 13.0, 17.0, 19.0, 23.0, 29.0],
        }
    )
    size = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=stocks,
    )
    industry = pd.DataFrame(
        [["bank", "bank", "tech", "tech", "energy", "energy"]],
        index=size.index,
        columns=stocks,
    )
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="none",
            neutralize_method="size_industry",
        )
    )

    result = pipeline.transform(
        factor,
        exposures={"size": size, "industry": industry},
    )

    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result["trade_date"].unique().tolist() == ["20240101"]
    assert len(result) == 6


def test_pipeline_long_input_parses_numeric_yyyymmdd_dates():
    factor = pd.DataFrame(
        {
            "trade_date": [20240101, 20240101, 20240101],
            "ts_code": ["000002.SZ", "000001.SZ", "000003.SZ"],
            "value": [2.0, 1.0, 3.0],
        }
    )
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="rank_pct",
            neutralize_method=None,
        )
    )

    result = pipeline.transform(factor)

    assert result["trade_date"].unique().tolist() == ["20240101"]


def test_pipeline_rejects_duplicate_long_factor_keys():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240101"],
            "ts_code": ["000001.SZ", "000001.SZ"],
            "value": [1.0, 2.0],
        }
    )
    pipeline = FactorPreprocessPipeline()

    with pytest.raises(ValueError, match="duplicate trade_date/ts_code"):
        pipeline.transform(factor)


def test_pipeline_rejects_long_input_missing_required_columns():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240101"],
            "value": [1.0],
        }
    )
    pipeline = FactorPreprocessPipeline()

    with pytest.raises(ValueError, match="long factor input must contain columns"):
        pipeline.transform(factor)


def test_preprocess_config_rejects_invalid_quantile_bounds():
    with pytest.raises(ValueError, match="quantile bounds must satisfy"):
        PreprocessConfig(
            winsorize_method="quantile",
            winsorize_lower_quantile=0.9,
            winsorize_upper_quantile=0.1,
        )
