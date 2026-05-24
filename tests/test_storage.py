import pandas as pd

from zer0factor.storage import FactorStats, FactorStorage


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


def test_write_and_read_empty_factor(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    df = pd.DataFrame(columns=["trade_date", "ts_code", "value"])

    storage.write("empty_factor", df)

    result = storage.read("empty_factor")
    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result.empty
    assert storage.list_factors() == ["empty_factor"]


def test_list_factors_empty(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    assert storage.list_factors() == []


def test_factor_stats_returns_none_for_missing_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    assert storage.factor_stats("nonexistent") is None


def test_factor_stats_returns_counts_and_dates(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240103", "20240103"],
        "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
        "value": [0.1, 0.2, 0.3],
    })
    storage.write("z_test", df)
    stats = storage.factor_stats("z_test")
    assert isinstance(stats, FactorStats)
    assert stats.rows == 3
    assert str(stats.start_date) == "20240102"
    assert str(stats.end_date) == "20240103"


def test_factor_stats_returns_none_for_empty_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame(columns=["trade_date", "ts_code", "value"])
    storage.write("z_empty", df)
    assert storage.factor_stats("z_empty") is None
