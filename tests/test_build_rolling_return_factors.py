from __future__ import annotations

import pandas as pd
import pytest

from zer0factor.pipeline import (
    _long_to_wide,
    compute_raw_rolling_return_factors,
)


class FakeStorage:
    def __init__(self, frames: dict[str, pd.DataFrame] | None = None) -> None:
        self.frames = frames or {}
        self.writes: dict[str, pd.DataFrame] = {}

    def read(
        self,
        factor_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        if factor_name not in self.frames:
            raise FileNotFoundError(f"Factor '{factor_name}' not found")
        frame = self.frames[factor_name].copy()
        if start_date is not None:
            frame = frame[frame["trade_date"] >= start_date]
        if end_date is not None:
            frame = frame[frame["trade_date"] <= end_date]
        return frame.reset_index(drop=True)

    def write(self, factor_name: str, df: pd.DataFrame) -> None:
        self.writes[factor_name] = df.copy()


def _base_factor(values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(values), freq="D")
    rows = []
    for date, value in zip(dates, values, strict=True):
        rows.append({
            "trade_date": date.strftime("%Y%m%d"),
            "ts_code": "000001.SZ",
            "value": value,
        })
    return pd.DataFrame(rows)


def test_compute_raw_rolling_return_factors_derives_from_stored_base_factors() -> None:
    storage = FakeStorage({
        "daily_return": _base_factor([1.0, 2.0, 3.0, 4.0, 5.0]),
        "open_return": _base_factor([10.0, 20.0, 30.0, 40.0, 50.0]),
        "intraday_return": _base_factor([2.0, 4.0, 6.0, 8.0, 10.0]),
        "overnight_return": _base_factor([5.0, 4.0, 3.0, 2.0, 1.0]),
    })

    rows = compute_raw_rolling_return_factors(
        storage=storage,
        start_date="20240101",
        end_date="20240105",
        windows=(5,),
    )

    assert set(rows) == {
        "daily_return_ma5",
        "open_return_ma5",
        "intraday_return_ma5",
        "overnight_return_ma5",
    }
    daily = storage.writes["daily_return_ma5"]
    assert list(daily.columns) == ["trade_date", "ts_code", "value"]
    assert daily["trade_date"].tolist() == ["20240102", "20240103", "20240104", "20240105"]
    assert daily["value"].tolist() == [1.5, 2.0, 2.5, 3.0]


def test_compute_raw_rolling_return_factors_preserves_lookback_before_start_date() -> None:
    storage = FakeStorage({
        "daily_return": _base_factor([1.0, 2.0, 3.0, 4.0, 5.0]),
        "open_return": _base_factor([10.0, 20.0, 30.0, 40.0, 50.0]),
        "intraday_return": _base_factor([2.0, 4.0, 6.0, 8.0, 10.0]),
        "overnight_return": _base_factor([5.0, 4.0, 3.0, 2.0, 1.0]),
    })

    rows = compute_raw_rolling_return_factors(
        storage=storage,
        start_date="20240103",
        end_date="20240105",
        windows=(5,),
    )

    daily = storage.writes["daily_return_ma5"]
    assert rows["daily_return_ma5"] == 3
    assert daily["trade_date"].tolist() == ["20240103", "20240104", "20240105"]
    assert daily["value"].tolist() == [2.0, 2.5, 3.0]


def test_compute_raw_rolling_return_factors_fails_when_base_factor_missing() -> None:
    storage = FakeStorage({
        "daily_return": _base_factor([1.0, 2.0, 3.0]),
    })

    with pytest.raises(FileNotFoundError, match="required factor missing: open_return"):
        compute_raw_rolling_return_factors(
            storage=storage,
            start_date=None,
            end_date=None,
            windows=(5,),
        )


def test_long_to_wide_rejects_duplicate_trade_date_code_pairs() -> None:
    frame = pd.DataFrame({
        "trade_date": ["20240101", "20240101"],
        "ts_code": ["000001.SZ", "000001.SZ"],
        "value": [1.0, 2.0],
    })

    with pytest.raises(ValueError, match="factor data contains duplicate trade_date/ts_code"):
        _long_to_wide(frame)
