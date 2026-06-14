import pandas as pd
import pytest

from zer0factor.panel import (
    filter_long_by_universe,
    filter_panel_by_universe,
    long_to_wide,
    parse_trade_dates,
    read_universe_panel,
    wide_to_long,
)


class FakeUniversePro:
    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        assert universe == "univ_trade_base"
        assert fields == "trade_date,universe,ts_code"
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240101", "20240102"],
                "universe": ["univ_trade_base"] * 3,
                "ts_code": ["000001.SZ", "000003.SZ", "000002.SZ"],
            }
        )


def _long_frame():
    return pd.DataFrame(
        {
            "trade_date": ["20240101", "20240101", "20240102", "20240102"],
            "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )


def test_parse_trade_dates_handles_strings_and_numerics():
    strings = parse_trade_dates(pd.Series(["20240101", "20240102"]))
    numerics = parse_trade_dates(pd.Series([20240101, 20240102]))
    expected = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]))
    pd.testing.assert_series_equal(strings, expected)
    pd.testing.assert_series_equal(numerics, expected)


def test_long_to_wide_pivots_and_sorts():
    wide = long_to_wide(_long_frame())
    assert list(wide.columns) == ["000001.SZ", "000002.SZ"]
    assert wide.index.tolist() == pd.to_datetime(["2024-01-01", "2024-01-02"]).tolist()
    assert wide.loc[pd.Timestamp("2024-01-02"), "000002.SZ"] == 4.0


def test_long_to_wide_rejects_duplicates():
    frame = _long_frame()
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        long_to_wide(duplicated)


def test_wide_to_long_roundtrips():
    long = wide_to_long(long_to_wide(_long_frame()))
    assert list(long.columns) == ["trade_date", "ts_code", "value"]
    pd.testing.assert_frame_equal(long, _long_frame())


def test_filter_panel_by_universe_masks_and_drops_empty_columns():
    panel = long_to_wide(_long_frame())
    universe = pd.DataFrame(
        {"000001.SZ": [True, True], "000002.SZ": [False, False]},
        index=panel.index,
    )
    filtered = filter_panel_by_universe(panel, universe)
    assert list(filtered.columns) == ["000001.SZ"]
    assert filtered["000001.SZ"].tolist() == [1.0, 3.0]


def test_filter_panel_by_universe_none_is_identity():
    panel = long_to_wide(_long_frame())
    pd.testing.assert_frame_equal(filter_panel_by_universe(panel, None), panel)


def test_filter_long_by_universe_masks_rows():
    panel = long_to_wide(_long_frame())
    universe = pd.DataFrame(
        {"000001.SZ": [True, False], "000002.SZ": [True, True]},
        index=panel.index,
    )
    filtered = filter_long_by_universe(_long_frame(), universe)
    assert filtered[["ts_code", "value"]].values.tolist() == [
        ["000001.SZ", 1.0],
        ["000002.SZ", 2.0],
        ["000002.SZ", 4.0],
    ]


def test_read_universe_panel_builds_boolean_panel():
    panel = read_universe_panel(
        FakeUniversePro(),
        universe_name="univ_trade_base",
        start_date="20240101",
        end_date="20240102",
    )
    assert panel.dtypes.unique().tolist() == [bool]
    assert panel.loc[pd.Timestamp("2024-01-01"), "000001.SZ"]
    assert not panel.loc[pd.Timestamp("2024-01-02"), "000001.SZ"]
    assert panel.loc[pd.Timestamp("2024-01-02"), "000002.SZ"]


def test_read_universe_panel_empty_result_returns_empty_bool_frame():
    class EmptyUniversePro:
        def universe(self, universe=None, start_date=None, end_date=None, fields=None):
            return pd.DataFrame(columns=["trade_date", "universe", "ts_code"])

    panel = read_universe_panel(
        EmptyUniversePro(),
        universe_name="univ_trade_base",
        start_date="20240101",
        end_date="20240102",
    )
    assert panel.shape == (0, 0)


def test_filter_long_by_universe_none_is_identity():
    frame = _long_frame()
    pd.testing.assert_frame_equal(filter_long_by_universe(frame, None), frame)
