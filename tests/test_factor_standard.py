import pandas as pd
import pytest

from zer0factor.factor import (
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
        recommended_window=60,
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
        recommended_window=60,
        adjust="hfq",
    )
    assert spec.output_schema == ("trade_date", "ts_code", "value")

    with pytest.raises(ValueError, match="unknown input"):
        FactorSpec(name="bad", inputs=["st_status"], min_window=1)

    with pytest.raises(ValueError, match="recommended_window"):
        FactorSpec(name="bad_window", inputs=["close"], min_window=20, recommended_window=10)


def test_factor_frame_exposes_only_declared_standard_fields():
    close = _wide_frame()
    volume = _wide_frame() * 100
    frame = FactorFrame({"close": close, "volume": volume})

    assert frame.close.equals(close)
    assert frame.volume.equals(volume)
    with pytest.raises(AttributeError):
        _ = frame.open


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
    def stock_basic(self, list_status="L", fields=None):
        return pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"]})

    def pro_bar(self, ts_code, start_date, end_date, adj):
        assert adj == "hfq"
        dates = pd.date_range("2024-01-01", periods=2, freq="D").strftime("%Y%m%d")
        base = 1 if ts_code == "000001.SZ" else 10
        return pd.DataFrame(
            {
                "ts_code": [ts_code, ts_code],
                "trade_date": dates,
                "close": [base, base + 1],
                "vol": [base * 100, (base + 1) * 100],
            }
        )


def test_zer0share_provider_maps_local_api_to_factor_frame():
    provider = Zer0ShareDataProvider(FakeLocalPro())

    frame = provider.history(
        fields=["close", "volume"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
    )

    assert list(frame.close.columns) == ["000001.SZ", "000002.SZ"]
    assert frame.close.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 10
    assert frame.volume.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 200
