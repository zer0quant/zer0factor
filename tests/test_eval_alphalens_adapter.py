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


def test_factor_long_to_alphalens_series_parses_float_like_numeric_dates():
    factor = pd.DataFrame(
        {
            "trade_date": [20240102.0],
            "ts_code": ["000001.SZ"],
            "value": [1.5],
        }
    )

    result = factor_long_to_alphalens_series(factor)

    assert result.loc[(pd.Timestamp("2024-01-02"), "000001.SZ")] == 1.5


def test_factor_long_to_alphalens_series_parses_float_like_string_dates():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240102.0"],
            "ts_code": ["000001.SZ"],
            "value": [1.5],
        }
    )

    result = factor_long_to_alphalens_series(factor)

    assert result.loc[(pd.Timestamp("2024-01-02"), "000001.SZ")] == 1.5


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


def test_build_price_matrix_rejects_duplicate_date_asset_rows():
    raw = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240101"],
            "ts_code": ["000001.SZ", "000001.SZ"],
            "open": [10.0, 11.0],
            "close": [10.5, 11.5],
        }
    )

    with pytest.raises(ValueError, match="duplicate date/asset"):
        build_price_matrix(raw, return_type="close_t0")


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


def test_filter_factor_by_universe_treats_nan_as_not_member():
    factor = pd.Series(
        [1.0],
        index=pd.MultiIndex.from_tuples(
            [(pd.Timestamp("2024-01-01"), "000001.SZ")],
            names=["date", "asset"],
        ),
        name="factor",
    )
    universe = pd.DataFrame(
        {"000001.SZ": [float("nan")]},
        index=pd.to_datetime(["2024-01-01"]),
    )

    result = filter_factor_by_universe(factor, universe)

    assert result.empty


def _reference_filter(factor, universe):
    """The original row-by-row implementation, kept as the oracle."""
    membership = pd.Series(
        (
            pd.notna(universe.at[date, asset]) and bool(universe.at[date, asset])
            if date in universe.index and asset in universe.columns
            else False
        )
        for date, asset in factor.index
    )
    return factor[membership.to_numpy()]


def _random_case(seed, universe_values):
    import numpy as np

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=40)
    assets = [f"{i:06d}.SZ" for i in range(30)]
    index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    keep = rng.random(len(index)) < 0.7
    factor = pd.Series(rng.normal(size=keep.sum()), index=index[keep], name="factor")
    # universe misses some dates and assets and has extra ones
    u_dates = dates[rng.random(len(dates)) < 0.9].append(pd.DatetimeIndex(["2030-01-01"]))
    u_assets = [a for a in assets if rng.random() < 0.85] + ["999999.SH"]
    values = universe_values(rng, (len(u_dates), len(u_assets)))
    universe = pd.DataFrame(values, index=u_dates, columns=u_assets)
    return factor, universe


def test_filter_factor_by_universe_matches_reference_bool_panel():
    for seed in range(5):
        factor, universe = _random_case(seed, lambda rng, shape: rng.random(shape) < 0.6)
        pd.testing.assert_series_equal(
            filter_factor_by_universe(factor, universe), _reference_filter(factor, universe)
        )


def test_filter_factor_by_universe_matches_reference_object_panel_with_nan():
    import numpy as np

    def values(rng, shape):
        choice = rng.integers(0, 4, size=shape)
        out = np.empty(shape, dtype=object)
        out[choice == 0] = True
        out[choice == 1] = False
        out[choice == 2] = np.nan
        out[choice == 3] = 1.0
        return out

    for seed in range(5):
        factor, universe = _random_case(seed, values)
        pd.testing.assert_series_equal(
            filter_factor_by_universe(factor, universe), _reference_filter(factor, universe)
        )


def test_filter_factor_by_universe_empty_inputs():
    factor = pd.Series(
        [], index=pd.MultiIndex.from_arrays([pd.DatetimeIndex([]), []], names=["date", "asset"]),
        name="factor", dtype=float,
    )
    assert filter_factor_by_universe(factor, pd.DataFrame(dtype=bool)).empty
    one = pd.Series(
        [1.0], index=pd.MultiIndex.from_tuples([(pd.Timestamp("2024-01-01"), "A")], names=["date", "asset"]),
        name="factor",
    )
    assert filter_factor_by_universe(one, pd.DataFrame(dtype=bool)).empty


def test_factor_long_to_alphalens_series_date_types_match():
    import numpy as np

    expected = pd.to_datetime(["2024-01-02", "2024-01-03"])
    for raw in (
        np.array([20240102, 20240103], dtype="int64"),
        np.array([20240102, 20240103], dtype="int32"),
        np.array([20240102.0, 20240103.0]),
        ["20240102", "20240103"],
        ["20240102.0", "20240103"],
        pd.array([20240102, 20240103], dtype="Int64"),
    ):
        factor = pd.DataFrame({"trade_date": raw, "ts_code": ["A", "A"], "value": [1.0, 2.0]})
        result = factor_long_to_alphalens_series(factor)
        assert list(result.index.get_level_values("date")) == list(expected), raw
