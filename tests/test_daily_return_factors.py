from __future__ import annotations

import pandas as pd

from zer0factor.factor import FactorFrame, run_factor
from zer0factor.factors import (
    DailyReturn,
    IntradayReturn,
    OpenReturn,
    OvernightReturn,
)


def _factor_frame() -> FactorFrame:
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    open_ = pd.DataFrame(
        {"000001.SZ": [10.0, 11.0, 12.0], "000002.SZ": [20.0, 21.0, 24.0]},
        index=index,
    )
    close = pd.DataFrame(
        {"000001.SZ": [10.5, 12.0, 12.6], "000002.SZ": [21.0, 22.0, 25.2]},
        index=index,
    )
    return FactorFrame({"open": open_, "close": close})


def _values_by_date(result: pd.DataFrame, ts_code: str = "000001.SZ") -> dict[str, float]:
    rows = result[result["ts_code"] == ts_code]
    return dict(zip(rows["trade_date"], rows["value"], strict=True))


def test_daily_return_uses_close_to_previous_close():
    result = run_factor(DailyReturn(), _factor_frame())

    values = _values_by_date(result)
    assert set(values) == {"20240102", "20240103"}
    assert values["20240102"] == 12.0 / 10.5 - 1
    assert values["20240103"] == 12.6 / 12.0 - 1


def test_open_return_uses_open_to_previous_open():
    result = run_factor(OpenReturn(), _factor_frame())

    values = _values_by_date(result)
    assert set(values) == {"20240102", "20240103"}
    assert values["20240102"] == 11.0 / 10.0 - 1
    assert values["20240103"] == 12.0 / 11.0 - 1


def test_intraday_return_uses_close_to_same_day_open():
    result = run_factor(IntradayReturn(), _factor_frame())

    values = _values_by_date(result)
    assert set(values) == {"20240101", "20240102", "20240103"}
    assert values["20240101"] == 10.5 / 10.0 - 1
    assert values["20240102"] == 12.0 / 11.0 - 1


def test_overnight_return_uses_open_to_previous_close():
    result = run_factor(OvernightReturn(), _factor_frame())

    values = _values_by_date(result)
    assert set(values) == {"20240102", "20240103"}
    assert values["20240102"] == 11.0 / 10.5 - 1
    assert values["20240103"] == 12.0 / 12.0 - 1
