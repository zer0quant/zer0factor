from __future__ import annotations

import pandas as pd
import pytest

from zer0factor.factor_registry import get_family
from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    RollingReturnFamily,
)
from zer0factor.families import FactorOutputSpec
from zer0factor.preprocess_profile import (
    PROFILES,
    RANK,
    RANK_INDUSTRY_NEU,
    RANK_SIZE_INDUSTRY_NEU,
    RANK_SIZE_NEU,
    RAW,
    Z_INDUSTRY_NEU,
    Z_SIZE_INDUSTRY_NEU,
    Z_SIZE_NEU,
    Z,
)


def test_rolling_return_constants_match_design() -> None:
    assert WINDOWS == (5, 10, 20, 30, 60, 90, 120, 180)
    assert BASE_RETURN_FACTORS == (
        "daily_return",
        "open_return",
        "intraday_return",
        "overnight_return",
    )


def test_preprocess_profiles_cover_all_five_methods() -> None:
    assert len(PROFILES) == 5
    keys = [p.key for p in PROFILES]
    assert keys == ["raw", "z", "z_size_neu", "z_industry_neu", "z_size_industry_neu"]


def test_preprocess_profile_boolean_fields_reflect_steps() -> None:
    assert RAW.zscore is False
    assert RAW.size_neutral is False
    assert RAW.industry_neutral is False

    assert Z.zscore is True
    assert Z.size_neutral is False
    assert Z.industry_neutral is False

    assert Z_SIZE_NEU.zscore is True
    assert Z_SIZE_NEU.size_neutral is True
    assert Z_SIZE_NEU.industry_neutral is False

    assert Z_INDUSTRY_NEU.zscore is True
    assert Z_INDUSTRY_NEU.size_neutral is False
    assert Z_INDUSTRY_NEU.industry_neutral is True

    assert Z_SIZE_INDUSTRY_NEU.zscore is True
    assert Z_SIZE_INDUSTRY_NEU.size_neutral is True
    assert Z_SIZE_INDUSTRY_NEU.industry_neutral is True


def test_preprocess_profile_neutralize_method() -> None:
    assert RAW.neutralize_method is None
    assert Z.neutralize_method is None
    assert Z_SIZE_NEU.neutralize_method == "size"
    assert Z_INDUSTRY_NEU.neutralize_method == "industry"
    assert Z_SIZE_INDUSTRY_NEU.neutralize_method == "size_industry"


def test_preprocess_profile_output_name() -> None:
    assert RAW.output_name("daily_return_ma5") == "daily_return_ma5"
    assert Z.output_name("daily_return_ma5") == "z_daily_return_ma5"
    assert Z_SIZE_NEU.output_name("daily_return_ma5") == "z_size_neu_daily_return_ma5"


def test_rank_preprocess_profiles_use_rank_normal_standardization() -> None:
    assert RANK.key == "rank"
    assert RANK.standardize_method == "rank_normal"
    assert RANK.output_name("rtn_intra_turn_strength_5d") == "rank_rtn_intra_turn_strength_5d"
    assert RANK_SIZE_NEU.neutralize_method == "size"
    assert RANK_INDUSTRY_NEU.neutralize_method == "industry"
    assert RANK_SIZE_INDUSTRY_NEU.neutralize_method == "size_industry"


def test_raw_names_expand_to_32_in_stable_order() -> None:
    family = get_family("rolling_return")
    names = family.raw_names()

    assert len(names) == 32
    assert len(set(names)) == 32
    assert names[0] == "daily_return_ma5"
    assert names[7] == "daily_return_ma180"
    assert names[8] == "open_return_ma5"
    assert names[-1] == "overnight_return_ma180"


def test_rolling_return_family_variant_counts() -> None:
    family = get_family("rolling_return")

    assert len(family.all_factor_names()) == 160   # 32 raw × 5 profiles
    assert len(family.preprocess_output_names()) == 128  # 32 raw × 4 preprocessed
    assert family.all_factor_names()[0] == "daily_return_ma5"
    assert "z_daily_return_ma5" in family.all_factor_names()
    assert "z_size_neu_daily_return_ma5" in family.all_factor_names()
    assert "z_industry_neu_daily_return_ma5" in family.all_factor_names()
    assert "z_size_industry_neu_overnight_return_ma180" in family.all_factor_names()


def test_parse_output_name_returns_factor_output_spec_for_raw() -> None:
    family = get_family("rolling_return")
    spec = family.parse_output_name("daily_return_ma20")

    assert isinstance(spec, FactorOutputSpec)
    assert spec.family == "rolling_return"
    assert spec.raw_name == "daily_return_ma20"
    assert spec.is_raw is True
    assert spec.preprocess == "raw"
    assert spec.name == "daily_return_ma20"
    assert spec.params == {"base_factor": "daily_return", "window": 20}
    assert spec.analysis_dimensions() == {
        "base_factor": "daily_return",
        "preprocess": "raw",
        "window": 20,
    }


def test_parse_output_name_returns_factor_output_spec_for_preprocessed() -> None:
    family = get_family("rolling_return")
    spec = family.parse_output_name("z_size_industry_neu_overnight_return_ma180")

    assert isinstance(spec, FactorOutputSpec)
    assert spec.family == "rolling_return"
    assert spec.raw_name == "overnight_return_ma180"
    assert spec.is_raw is False
    assert spec.preprocess == "z_size_industry_neu"
    assert spec.profile == Z_SIZE_INDUSTRY_NEU
    assert spec.name == "z_size_industry_neu_overnight_return_ma180"
    assert spec.params == {"base_factor": "overnight_return", "window": 180}


def test_parse_output_name_round_trips_all_profiles() -> None:
    family = get_family("rolling_return")

    for profile in family.profiles:
        factor_name = profile.output_name("daily_return_ma20")
        spec = family.parse_output_name(factor_name)
        assert spec.profile == profile
        assert spec.raw_name == "daily_return_ma20"
        assert spec.name == factor_name


def test_parse_output_name_rejects_unknown_names() -> None:
    family = get_family("rolling_return")

    with pytest.raises(ValueError, match="unknown factor name"):
        family.parse_output_name("ma_bias_20d")
    with pytest.raises(ValueError, match="unknown factor name"):
        family.parse_output_name("daily_return_mean20")
    with pytest.raises(ValueError, match="unknown factor name"):
        family.parse_output_name("daily_return_ma999")


def test_derive_uses_half_window_min_periods() -> None:
    family = RollingReturnFamily()
    panel = pd.DataFrame(
        {
            "000001.SZ": [1.0, 2.0, 3.0, 4.0, 5.0],
            "000002.SZ": [10.0, 20.0, 30.0, 40.0, 50.0],
        },
        index=pd.to_datetime(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        ),
    )

    result = family.derive(panel, window=4)

    expected = pd.DataFrame(
        {
            "000001.SZ": [float("nan"), 1.5, 2.0, 2.5, 3.5],
            "000002.SZ": [float("nan"), 15.0, 20.0, 25.0, 35.0],
        },
        index=panel.index,
    )
    pd.testing.assert_frame_equal(result, expected)
