import pandas as pd
from click.testing import CliRunner

from main import (
    MARKET_CAP_FACTORS,
    RETURN_FACTORS,
    cli,
    compute_and_store_factors,
    compute_and_store_market_cap_factors,
)
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


class FakeMarketCapProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["circ_mv", "total_mv"]
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert universe == "000001.SZ,000002.SZ"
        assert adjust is None

        index = pd.date_range("2024-01-01", periods=2, freq="D")
        total_mv = pd.DataFrame(
            {"000001.SZ": [100.0, 110.0], "000002.SZ": [200.0, 220.0]},
            index=index,
        )
        circ_mv = pd.DataFrame(
            {"000001.SZ": [50.0, 55.0], "000002.SZ": [80.0, 88.0]},
            index=index,
        )
        return FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})


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


def test_compute_and_store_market_cap_factors_writes_raw_and_zscored(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")

    row_counts = compute_and_store_market_cap_factors(
        factors=MARKET_CAP_FACTORS,
        provider=FakeMarketCapProvider(),
        storage=storage,
        start_date="20240101",
        end_date="20240102",
        universe="000001.SZ,000002.SZ",
    )

    assert row_counts == {
        "log_total_market_cap": 4,
        "log_circulating_market_cap": 4,
        "z_log_total_market_cap": 4,
        "z_log_circulating_market_cap": 4,
    }
    assert sorted(storage.list_factors()) == [
        "log_circulating_market_cap",
        "log_total_market_cap",
        "z_log_circulating_market_cap",
        "z_log_total_market_cap",
    ]

    z_total = storage.read("z_log_total_market_cap")
    assert sorted(z_total["trade_date"].astype(str).unique()) == ["20240101", "20240102"]
    assert z_total.groupby("trade_date")["value"].mean().abs().max() < 1e-12


def test_compute_market_cap_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["compute-market-cap", "--help"])

    assert result.exit_code == 0
    assert "Compute built-in market cap factors" in result.output
