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


def test_factor_stats_returns_stats_for_single_date_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240102"],
        "ts_code": ["000001.SZ", "000002.SZ"],
        "value": [0.1, 0.2],
    })
    storage.write("z_single_date", df)
    stats = storage.factor_stats("z_single_date")
    assert stats is not None
    assert stats.rows == 2
    assert str(stats.start_date) == "20240102"
    assert str(stats.end_date) == "20240102"

def test_write_overwrites_partitions_on_rerun(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    first = pd.DataFrame({
        "trade_date": ["20240101", "20240101", "20240102"],
        "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ"],
        "value": [1.0, 2.0, 3.0],
    })
    second = pd.DataFrame({
        "trade_date": ["20240101", "20240101", "20240102"],
        "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ"],
        "value": [10.0, 20.0, 30.0],
    })

    storage.write("dup_check", first)
    storage.write("dup_check", second)
    result = storage.read("dup_check")

    assert len(result) == 3
    assert sorted(result["value"].tolist()) == [10.0, 20.0, 30.0]


def test_read_supports_legacy_data_parquet_files(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    partition = tmp_path / "factors" / "legacy_factor" / "date=20240101"
    partition.mkdir(parents=True)
    table = pa.Table.from_pandas(
        pd.DataFrame({"ts_code": ["000001.SZ"], "value": [1.5]}),
        preserve_index=False,
    )
    pq.write_table(table, partition / "data.parquet")

    result = storage.read("legacy_factor")

    assert result["trade_date"].astype(str).tolist() == ["20240101"]
    assert result["value"].tolist() == [1.5]

    stats = storage.factor_stats("legacy_factor")
    assert stats is not None
    assert stats.rows == 1

def test_write_partitions_skips_registry_and_register_adds_it(tmp_path):
    db_path = tmp_path / "meta.duckdb"
    storage = FactorStorage(tmp_path / "factors", db_path)
    df = pd.DataFrame({
        "trade_date": ["20240101"],
        "ts_code": ["000001.SZ"],
        "value": [1.0],
    })

    storage.write_partitions("split_check", df)
    assert storage.read("split_check")["value"].tolist() == [1.0]
    assert "split_check" not in storage.list_factors()

    storage.register("split_check")
    assert "split_check" in storage.list_factors()


def test_init_db_false_never_touches_duckdb(tmp_path):
    db_path = tmp_path / "meta.duckdb"
    worker_storage = FactorStorage(tmp_path / "factors", db_path, init_db=False)
    df = pd.DataFrame({
        "trade_date": ["20240101"],
        "ts_code": ["000001.SZ"],
        "value": [2.0],
    })

    worker_storage.write_partitions("worker_factor", df)

    assert worker_storage.read("worker_factor")["value"].tolist() == [2.0]
    assert not db_path.exists()
