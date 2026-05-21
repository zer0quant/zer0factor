import pandas as pd
import pytest

from zer0factor.core import (
    Factor,
    FactorFrame,
    FactorSpec,
    Zer0ShareDataProvider,
    run_factor,
    to_factor_output,
)
from zer0factor.storage import FactorStorage


class VolumeAdjustedMomentum20D(Factor):
    spec = FactorSpec(
        name="volume_adjusted_momentum_20d",
        inputs=["close", "volume"],
        min_window=20,
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        ret20 = data.close / data.close.shift(20) - 1
        vol_ratio = data.volume.rolling(5).mean() / (data.volume.rolling(20).mean() + 1e-8)
        value = ret20 * vol_ratio.rank(axis=1, pct=True)
        return to_factor_output(value, self.spec.name)


def _wide_frame(rows: int = 25) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="D")
    return pd.DataFrame(
        {
            "000001.SZ": range(1, rows + 1),
            "000002.SZ": range(2, rows + 2),
        },
        index=idx,
    )


def test_factor_spec_requires_standard_inputs_and_windows():
    spec = FactorSpec(
        name="momentum_20d",
        inputs=["close"],
        min_window=20,
        adjust="hfq",
    )
    assert spec.output_schema == ("trade_date", "ts_code", "value")

    with pytest.raises(ValueError, match="unknown input"):
        FactorSpec(name="bad", inputs=["st_status"], min_window=1)


def test_factor_spec_accepts_market_cap_fields():
    spec = FactorSpec(
        name="log_total_market_cap",
        inputs=["total_mv", "circ_mv"],
        min_window=1,
        adjust=None,
    )

    assert spec.inputs == ("total_mv", "circ_mv")


def test_factor_frame_exposes_only_declared_standard_fields():
    close = _wide_frame()
    volume = _wide_frame() * 100
    frame = FactorFrame({"close": close, "volume": volume})

    assert frame.close.equals(close)
    assert frame.volume.equals(volume)
    with pytest.raises(AttributeError):
        _ = frame.open


def test_factor_frame_exposes_market_cap_fields():
    total_mv = _wide_frame()
    circ_mv = _wide_frame() * 10
    frame = FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})

    assert frame.total_mv.equals(total_mv)
    assert frame.circ_mv.equals(circ_mv)


def test_to_factor_output_converts_wide_panel_to_storage_schema():
    value = _wide_frame(rows=2).astype(float)
    result = to_factor_output(value, "demo")

    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result.to_dict("records") == [
        {"trade_date": "20240101", "ts_code": "000001.SZ", "value": 1.0},
        {"trade_date": "20240101", "ts_code": "000002.SZ", "value": 2.0},
        {"trade_date": "20240102", "ts_code": "000001.SZ", "value": 2.0},
        {"trade_date": "20240102", "ts_code": "000002.SZ", "value": 3.0},
    ]


def test_run_factor_computes_and_writes_storage(tmp_path):
    close = _wide_frame(rows=25).astype(float)
    volume = (_wide_frame(rows=25) * 100).astype(float)
    frame = FactorFrame({"close": close, "volume": volume})
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")

    result = run_factor(VolumeAdjustedMomentum20D(), frame, storage=storage)

    assert set(result.columns) == {"trade_date", "ts_code", "value"}
    assert result["trade_date"].min() == "20240121"
    assert storage.list_factors() == ["volume_adjusted_momentum_20d"]


class FakeLocalPro:
    def __init__(self):
        self.pro_bar_calls = 0
        self.daily_basic_calls = 0
        self.expected_daily_basic_fields = "ts_code,trade_date,total_mv,circ_mv"

    def stock_basic(self, list_status="L", fields=None):
        return pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"]})

    def pro_bar(self, ts_code, start_date, end_date, adj):
        self.pro_bar_calls += 1
        assert ts_code == "000001.SZ,000002.SZ"
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert adj == "hfq"
        dates = pd.date_range("2024-01-01", periods=2, freq="D").strftime("%Y%m%d")
        frames = []
        for code, base in [("000001.SZ", 1), ("000002.SZ", 10)]:
            frames.append(
                pd.DataFrame(
                    {
                        "ts_code": [code, code],
                        "trade_date": dates,
                        "close": [base, base + 1],
                        "vol": [base * 100, (base + 1) * 100],
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)

    def daily_basic(self, ts_code=None, start_date=None, end_date=None, fields=None):
        self.daily_basic_calls += 1
        assert ts_code == "000001.SZ,000002.SZ"
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert fields == self.expected_daily_basic_fields
        dates = pd.date_range("2024-01-01", periods=2, freq="D").strftime("%Y%m%d")
        frames = []
        for code, total_base, circ_base in [
            ("000001.SZ", 1000, 500),
            ("000002.SZ", 2000, 1000),
        ]:
            frames.append(
                pd.DataFrame(
                    {
                        "ts_code": [code, code],
                        "trade_date": dates,
                        "total_mv": [total_base, total_base + 100],
                        "circ_mv": [circ_base, circ_base + 50],
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)


def test_zer0share_provider_maps_local_api_to_factor_frame():
    pro = FakeLocalPro()
    provider = Zer0ShareDataProvider(pro)

    frame = provider.history(
        fields=["close", "volume"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
    )

    assert pro.pro_bar_calls == 1
    assert list(frame.close.columns) == ["000001.SZ", "000002.SZ"]
    assert frame.close.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 10
    assert frame.volume.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 200


def test_zer0share_provider_loads_market_cap_fields_from_daily_basic():
    pro = FakeLocalPro()
    provider = Zer0ShareDataProvider(pro)

    frame = provider.history(
        fields=["total_mv", "circ_mv"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
    )

    assert pro.pro_bar_calls == 0
    assert pro.daily_basic_calls == 1
    assert frame.total_mv.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 1000
    assert frame.circ_mv.loc[pd.Timestamp("2024-01-02"), "000002.SZ"] == 1050


def test_zer0share_provider_combines_price_and_market_cap_fields():
    pro = FakeLocalPro()
    pro.expected_daily_basic_fields = "ts_code,trade_date,total_mv"
    provider = Zer0ShareDataProvider(pro)

    frame = provider.history(
        fields=["close", "total_mv"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
    )

    assert pro.pro_bar_calls == 1
    assert pro.daily_basic_calls == 1
    assert frame.close.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 2
    assert frame.total_mv.loc[pd.Timestamp("2024-01-02"), "000002.SZ"] == 2100


def test_zer0share_provider_uses_stable_daily_basic_field_order():
    pro = FakeLocalPro()
    provider = Zer0ShareDataProvider(pro)

    frame = provider.history(
        fields=["circ_mv", "total_mv"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
    )

    assert pro.daily_basic_calls == 1
    assert frame.circ_mv.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 500
    assert frame.total_mv.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 2000


class EmptyUniverseLocalPro(FakeLocalPro):
    def stock_basic(self, list_status="L", fields=None):
        return pd.DataFrame({"ts_code": []})

    def pro_bar(self, ts_code, start_date, end_date, adj):
        raise AssertionError("pro_bar should not be called for an empty universe")

    def daily_basic(self, ts_code=None, start_date=None, end_date=None, fields=None):
        raise AssertionError("daily_basic should not be called for an empty universe")


def test_zer0share_provider_returns_empty_panels_for_empty_universe():
    pro = EmptyUniverseLocalPro()
    provider = Zer0ShareDataProvider(pro)
    progress_calls = []

    frame = provider.history(
        fields=["close", "total_mv"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
        progress=lambda index, total, code: progress_calls.append((index, total, code)),
    )

    assert frame.close.empty
    assert frame.total_mv.empty
    assert progress_calls == [(0, 0, ""), (0, 0, "")]
