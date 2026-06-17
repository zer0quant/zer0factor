import pandas as pd
import pytest

from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.storage import FactorStorage


class FakePro:
    def __init__(self):
        self.price_end_date = None

    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        self.price_end_date = end_date
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "open": [10.0, 11.0],
                "close": [10.5, 11.5],
            }
        )

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "universe": [universe, universe],
                "ts_code": ["000001.SZ", "000002.SZ"],
            }
        )

    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "pct_chg": [1.0, -0.5],
            }
        )


def test_data_loader_reads_factor_and_extends_price_window(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101"],
                "ts_code": ["000001.SZ"],
                "value": [1.0],
            }
        ),
    )
    pro = FakePro()
    loader = EvaluationDataLoader(storage, pro)

    factor = loader.load_factor("factor_a", start_date="20240101", end_date=None)
    prices = loader.load_prices(
        start_date="20240101",
        end_date="20240102",
        periods=(5,),
    )

    assert factor["value"].tolist() == [1.0]
    assert len(prices) == 2
    assert pro.price_end_date == "20240127"


def test_data_loader_builds_universe_panel(tmp_path):
    loader = EvaluationDataLoader(None, FakePro())

    panel = loader.load_universe(
        universe_name="demo",
        start_date="20240101",
        end_date="20240102",
    )

    assert panel.index.tolist() == pd.to_datetime(
        ["2024-01-01", "2024-01-02"]
    ).tolist()
    assert panel.columns.tolist() == ["000001.SZ", "000002.SZ"]
    assert panel.loc[pd.Timestamp("2024-01-01"), "000001.SZ"]
    assert not panel.loc[pd.Timestamp("2024-01-01"), "000002.SZ"]


def test_data_loader_loads_benchmark_returns(tmp_path):
    loader = EvaluationDataLoader(None, FakePro())

    returns = loader.load_benchmark_returns(
        ts_code="000300.SH",
        start_date="20240101",
        end_date="20240102",
    )

    assert returns.name == "000300.SH"
    assert returns.loc[pd.Timestamp("2024-01-01")] == pytest.approx(0.01)


def test_data_loader_max_factor_trade_date_accepts_float_dates(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": [20240101.0, 20240220.0],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    loader = EvaluationDataLoader(storage, FakePro())

    assert (
        loader.max_factor_trade_date(("factor_a",), start_date="20240101")
        == "20240220"
    )
