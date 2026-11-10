import pandas as pd

from zer0factor.core import FactorFrame
from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS
from zer0factor.services.compute import FactorComputeService, ZScorePostProcess
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
    service = FactorComputeService(provider=FakeProvider(), storage=storage)

    row_counts = service.compute_and_store(
        RETURN_FACTORS,
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
    service = FactorComputeService(provider=FakeMarketCapProvider(), storage=storage)

    row_counts = service.compute_and_store(
        MARKET_CAP_FACTORS,
        start_date="20240101",
        end_date="20240102",
        universe="000001.SZ,000002.SZ",
        postprocess=ZScorePostProcess(storage),
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


class RollingMeanFactor:
    """5-day rolling mean of close: needs 4 days of look-back to be exact."""

    from zer0factor.core import FactorSpec as _Spec

    spec = _Spec(name="close_ma5", inputs=["close"], min_window=5, adjust="hfq")

    def compute(self, data):
        from zer0factor.core import to_factor_output

        return to_factor_output(data.close.rolling(5, min_periods=2).mean(), "close_ma5")


class RecordingProvider:
    def __init__(self, close: pd.DataFrame):
        self._close = close
        self.calls: list[str] = []

    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        self.calls.append(start_date)
        index = self._close.index
        mask = index >= pd.Timestamp(start_date)
        if end_date is not None:
            mask &= index <= pd.Timestamp(end_date)
        return FactorFrame({"close": self._close.loc[mask]})


def _close_panel() -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=12)
    return pd.DataFrame({"000001.SZ": [float(i) for i in range(1, 13)]}, index=index)


def test_compute_and_store_reads_lookback_but_writes_only_from_start_date(tmp_path):
    close = _close_panel()
    full_storage = FactorStorage(tmp_path / "full", tmp_path / "full.duckdb")
    FactorComputeService(RecordingProvider(close), full_storage).compute_and_store(
        (RollingMeanFactor(),), start_date="20240101", end_date=None, universe="all"
    )

    storage = FactorStorage(tmp_path / "inc", tmp_path / "inc.duckdb")
    provider = RecordingProvider(close)
    rows = FactorComputeService(provider, storage).compute_and_store(
        (RollingMeanFactor(),),
        start_date="20240111",
        end_date=None,
        universe="all",
        load_start_date="20240101",
    )

    assert provider.calls == ["20240101"]
    written = storage.read("close_ma5")
    assert sorted(written["trade_date"].astype(str).unique()) == ["20240111", "20240112", "20240115", "20240116"]
    assert rows == {"close_ma5": 4}
    expected = full_storage.read("close_ma5", start_date="20240111")
    pd.testing.assert_frame_equal(written.reset_index(drop=True), expected.reset_index(drop=True))


def test_compute_and_store_postprocess_sees_only_written_dates(tmp_path):
    close = _close_panel()
    storage = FactorStorage(tmp_path / "f", tmp_path / "f.duckdb")
    seen: list[set[str]] = []

    def postprocess(name, raw):
        seen.append(set(raw["trade_date"]))
        return {}

    FactorComputeService(RecordingProvider(close), storage).compute_and_store(
        (RollingMeanFactor(),),
        start_date="20240115",
        end_date=None,
        universe="all",
        load_start_date="20240101",
        postprocess=postprocess,
    )
    assert seen == [{"20240115", "20240116"}]


def test_resolve_load_start_full_history_when_lookback_unknown():
    from zer0factor.services.compute import resolve_load_start

    def no_calendar(date, n):
        raise AssertionError("calendar must not be used")

    assert (
        resolve_load_start(
            None, write_start="20260516", history_start="20160101", trading_days_before=no_calendar
        )
        == "20160101"
    )


def test_resolve_load_start_uses_trading_calendar_for_lookback():
    from zer0factor.services.compute import resolve_load_start

    calls = []

    def calendar(date, n):
        calls.append((date, n))
        return "20260401"

    assert (
        resolve_load_start(
            30, write_start="20260516", history_start="20160101", trading_days_before=calendar
        )
        == "20260401"
    )
    assert calls == [("20260516", 30)]


def test_resolve_load_start_never_before_history_start_or_after_write_start():
    from zer0factor.services.compute import resolve_load_start

    assert (
        resolve_load_start(
            30, write_start="20160105", history_start="20160101",
            trading_days_before=lambda d, n: "20151101",
        )
        == "20160101"
    )
    assert (
        resolve_load_start(
            0, write_start="20260516", history_start="20160101",
            trading_days_before=lambda d, n: "20260516",
        )
        == "20260516"
    )
    assert (
        resolve_load_start(
            None, write_start="20150101", history_start="20160101",
            trading_days_before=lambda d, n: d,
        )
        == "20150101"
    )


def test_trading_days_before_counts_open_days():
    from zer0factor.services.compute import trading_days_before

    class FakePro:
        def trade_cal(self, exchange, start_date, end_date, is_open):
            assert exchange == "SSE" and is_open == 1
            days = pd.bdate_range("2026-04-01", "2026-05-15")
            frame = pd.DataFrame({"cal_date": days.strftime("%Y%m%d")})
            return frame[(frame.cal_date >= start_date) & (frame.cal_date <= end_date)]

    # 2026-05-15 (Fri) back 3 open days -> 05-12 (Tue); start itself excluded
    assert trading_days_before(FakePro(), "20260515", 3) == "20260512"
    assert trading_days_before(FakePro(), "20260515", 0) == "20260515"
