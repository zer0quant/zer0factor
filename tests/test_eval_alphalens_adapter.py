import pandas as pd
import pytest

from zer0factor.eval.alphalens_adapter import (
    build_price_matrix,
    factor_long_to_alphalens_series,
    filter_factor_by_universe,
)


def test_factor_long_to_alphalens_series_uses_date_asset_index():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240102", "20240102"],
            "ts_code": ["000001.SZ", "000002.SZ"],
            "value": [1.5, -0.2],
        }
    )

    result = factor_long_to_alphalens_series(factor)

    assert result.index.names == ["date", "asset"]
    assert result.loc[(pd.Timestamp("2024-01-02"), "000001.SZ")] == 1.5
    assert result.name == "factor"


def test_factor_long_to_alphalens_series_rejects_duplicates():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240102", "20240102"],
            "ts_code": ["000001.SZ", "000001.SZ"],
            "value": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="duplicate date/asset"):
        factor_long_to_alphalens_series(factor)


def test_build_price_matrix_open_t1_shifts_open_prices():
    raw = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240102", "20240103"],
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "open": [10.0, 11.0, 12.0],
            "close": [10.5, 11.5, 12.5],
        }
    )

    result = build_price_matrix(raw, return_type="open_t1")

    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 11.0
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 12.0
    assert pd.isna(result.loc[pd.Timestamp("2024-01-03"), "000001.SZ"])


def test_build_price_matrix_close_t0_does_not_shift_close_prices():
    raw = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240102"],
            "ts_code": ["000001.SZ", "000001.SZ"],
            "open": [10.0, 11.0],
            "close": [10.5, 11.5],
        }
    )

    result = build_price_matrix(raw, return_type="close_t0")

    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 10.5
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 11.5


def test_filter_factor_by_universe_keeps_only_members():
    factor = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-01"), "000002.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
        name="factor",
    )
    universe = pd.DataFrame(
        {
            "000001.SZ": [True, False],
            "000002.SZ": [False, True],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )

    result = filter_factor_by_universe(factor, universe)

    assert list(result.index) == [(pd.Timestamp("2024-01-01"), "000001.SZ")]
