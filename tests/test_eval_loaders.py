import pandas as pd
import pytest

from zer0factor.eval.loaders import load_index_daily


class FakeIndexPro:
    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame({
            "ts_code": ["000300.SH"] * 3,
            "trade_date": ["20240102", "20240103", "20240104"],
            "pct_chg": [1.5, -0.8, 0.3],
        })


class EmptyIndexPro:
    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(columns=["ts_code", "trade_date", "pct_chg"])


def test_load_index_daily_returns_series_with_datetime_index():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert isinstance(result, pd.Series)
    assert pd.api.types.is_datetime64_any_dtype(result.index)


def test_load_index_daily_values_are_pct_chg_divided_by_100():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert result.iloc[0] == pytest.approx(0.015)
    assert result.iloc[1] == pytest.approx(-0.008)


def test_load_index_daily_empty_returns_empty_series():
    pro = EmptyIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert isinstance(result, pd.Series)
    assert len(result) == 0


def test_load_index_daily_index_is_sorted():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert result.index.is_monotonic_increasing


def test_load_index_daily_series_name_is_ts_code():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert result.name == "000300.SH"


def test_load_index_daily_drops_nan_pct_chg_rows():
    class NanRowPro:
        def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
            return pd.DataFrame({
                "ts_code": ["000300.SH"] * 3,
                "trade_date": ["20240102", "20240103", "20240104"],
                "pct_chg": [1.5, None, 0.3],
            })
    result = load_index_daily(NanRowPro(), ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert len(result) == 2


def test_load_index_daily_deduplicates_trade_date():
    class DupPro:
        def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
            return pd.DataFrame({
                "ts_code": ["000300.SH"] * 4,
                "trade_date": ["20240102", "20240102", "20240103", "20240104"],
                "pct_chg": [1.0, 1.5, -0.8, 0.3],
            })
    result = load_index_daily(DupPro(), ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert len(result) == 3
