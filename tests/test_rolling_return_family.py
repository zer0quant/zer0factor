from __future__ import annotations

import pytest

from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    parse_rolling_return_name,
    raw_factor_names,
)
from zer0factor.pipeline import get_family


def test_rolling_return_constants_match_design() -> None:
    assert WINDOWS == (5, 10, 20, 30, 60, 90, 120, 180)
    assert BASE_RETURN_FACTORS == (
        "daily_return",
        "open_return",
        "intraday_return",
        "overnight_return",
    )


def test_raw_factor_names_expand_to_32_in_stable_order() -> None:
    names = raw_factor_names()

    assert len(names) == 32
    assert len(set(names)) == 32
    assert names[0] == "daily_return_ma5"
    assert names[7] == "daily_return_ma180"
    assert names[8] == "open_return_ma5"
    assert names[-1] == "overnight_return_ma180"


def test_rolling_return_family_expands_profiles() -> None:
    family = get_family("rolling_return")

    assert family.raw_names() == raw_factor_names()
    assert len(family.preprocess_output_names()) == 128
    assert len(family.all_factor_names()) == 160
    assert family.all_factor_names()[0] == "daily_return_ma5"
    assert "z_daily_return_ma5" in family.all_factor_names()
    assert "z_size_neu_daily_return_ma5" in family.all_factor_names()
    assert "z_industry_neu_daily_return_ma5" in family.all_factor_names()
    assert "z_size_industry_neu_overnight_return_ma180" in family.all_factor_names()


def test_parse_rolling_return_name_handles_profiles() -> None:
    assert parse_rolling_return_name("daily_return_ma20") == {
        "base_factor": "daily_return",
        "preprocess": "raw",
        "window": 20,
    }
    assert parse_rolling_return_name("z_size_industry_neu_overnight_return_ma180") == {
        "base_factor": "overnight_return",
        "preprocess": "z_size_industry_neu",
        "window": 180,
    }


def test_parse_rolling_return_name_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown rolling return factor name"):
        parse_rolling_return_name("ma_bias_20d")
    with pytest.raises(ValueError, match="factor name does not end with _ma<window>"):
        parse_rolling_return_name("daily_return_mean20")
    with pytest.raises(ValueError, match="unsupported rolling return window"):
        parse_rolling_return_name("daily_return_ma999")
