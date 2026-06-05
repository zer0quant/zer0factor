from __future__ import annotations

import pandas as pd
import pytest

from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    derive_rolling_mean_output,
    derive_rolling_mean_panel,
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


def test_parse_rolling_return_name_round_trips_family_profiles() -> None:
    family = get_family("rolling_return")

    for profile in family.profiles:
        factor_name = profile.output_name("daily_return_ma20")

        assert parse_rolling_return_name(factor_name) == {
            "base_factor": "daily_return",
            "preprocess": profile.key,
            "window": 20,
        }


def test_parse_rolling_return_name_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown rolling return factor name"):
        parse_rolling_return_name("ma_bias_20d")
    with pytest.raises(ValueError, match="factor name does not end with _ma<window>"):
        parse_rolling_return_name("daily_return_mean20")
    with pytest.raises(ValueError, match="unsupported rolling return window"):
        parse_rolling_return_name("daily_return_ma999")


def test_derive_rolling_mean_panel_uses_half_window_min_periods() -> None:
    panel = pd.DataFrame(
        {
            "000001.SZ": [1.0, 2.0, 3.0, 4.0, 5.0],
            "000002.SZ": [10.0, 20.0, 30.0, 40.0, 50.0],
        },
        index=pd.to_datetime(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        ),
    )

    result = derive_rolling_mean_panel(panel, window=4)

    expected = pd.DataFrame(
        {
            "000001.SZ": [float("nan"), 1.5, 2.0, 2.5, 3.5],
            "000002.SZ": [float("nan"), 15.0, 20.0, 25.0, 35.0],
        },
        index=panel.index,
    )
    pd.testing.assert_frame_equal(result, expected)


def test_derive_rolling_mean_output_returns_standard_sorted_long_schema() -> None:
    panel = pd.DataFrame(
        {
            "000002.SZ": [1.0, 3.0, 5.0],
            "000001.SZ": [2.0, 4.0, 6.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
    )

    result = derive_rolling_mean_output(panel, base_factor="daily_return", window=2)

    expected = pd.DataFrame(
        {
            "trade_date": [
                "20240101",
                "20240101",
                "20240102",
                "20240102",
                "20240103",
                "20240103",
            ],
            "ts_code": [
                "000001.SZ",
                "000002.SZ",
                "000001.SZ",
                "000002.SZ",
                "000001.SZ",
                "000002.SZ",
            ],
            "value": [2.0, 1.0, 3.0, 2.0, 5.0, 4.0],
        }
    )
    assert tuple(result.columns) == ("trade_date", "ts_code", "value")
    pd.testing.assert_frame_equal(result, expected)
