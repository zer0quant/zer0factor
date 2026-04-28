import pandas as pd

from src.storage import FactorStorage


def test_factor_storage_init(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    assert storage is not None


def test_write_and_read_factor(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240102"],
        "ts_code": ["000001.SZ", "000002.SZ"],
        "value": [0.5, -0.3],
    })
    storage.write("momentum_1m", df)

    result = storage.read("momentum_1m", start_date="20240101", end_date="20240131")
    assert len(result) == 2
    assert set(result.columns) == {"trade_date", "ts_code", "value"}


def test_list_factors_empty(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    assert storage.list_factors() == []
