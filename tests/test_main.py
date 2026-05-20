import pandas as pd

from main import RETURN_FACTORS, compute_and_store_factors
from zer0factor.core import FactorFrame
from zer0factor.storage import FactorStorage


class FakeProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["close", "open"]
        assert start_date == "20240101"
        assert end_date == "20240103"
        assert universe == "000001.SZ"
        assert adjust == "hfq"
        if progress is not None:
            progress(0, 1, "")
            progress(1, 1, "000001.SZ")

        index = pd.date_range("2024-01-01", periods=3, freq="D")
        open_ = pd.DataFrame({"000001.SZ": [10.0, 11.0, 12.0]}, index=index)
        close = pd.DataFrame({"000001.SZ": [10.5, 12.0, 12.6]}, index=index)
        return FactorFrame({"open": open_, "close": close})


def test_compute_and_store_return_factors(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")

    row_counts = compute_and_store_factors(
        factors=RETURN_FACTORS,
        provider=FakeProvider(),
        storage=storage,
        start_date="20240101",
        end_date="20240103",
        universe="000001.SZ",
    )

    assert row_counts == {
        "daily_return": 2,
        "open_return": 2,
        "intraday_return": 3,
        "overnight_return": 2,
    }
    assert storage.list_factors() == [
        "daily_return",
        "intraday_return",
        "open_return",
        "overnight_return",
    ]
