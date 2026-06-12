# Parallel Factor Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build-factors` fast by replacing the per-date parquet write loop with one partitioned dataset write, and parallelizing per-factor work across spawn-based worker processes behind a `--workers N` CLI option.

**Architecture:** `FactorStorage.write` is split into `write_partitions` (parquet only, worker-safe) and `register` (DuckDB, parent-only), with the partition write done by a single `pyarrow.dataset.write_dataset` call. `compute_raw_family_factors` and `preprocess_all_factors` gain `workers`; `workers == 1` keeps the existing inline path, `workers > 1` uses a `ProcessPoolExecutor` with the **spawn** context (fork is unsafe here: loguru runs an `enqueue=True` background thread). Workers reconstruct storage from paths with `init_db=False` and never touch DuckDB; the parent registers all names serially.

**Tech Stack:** pyarrow.dataset, concurrent.futures.ProcessPoolExecutor (spawn), DuckDB, click, pytest.

**Spec:** `docs/superpowers/specs/2026-06-12-parallel-factor-build-design.md`

---

### Task 1: Batch partitioned write in FactorStorage

**Files:**
- Modify: `zer0factor/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Add failing tests for overwrite semantics and legacy layout**

Append to `tests/test_storage.py`:

```python
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

    assert result["trade_date"].tolist() == ["20240101"]
    assert result["value"].tolist() == [1.5]

    stats = storage.factor_stats("legacy_factor")
    assert stats is not None
    assert stats.rows == 1
```

- [ ] **Step 2: Run the new tests and verify the overwrite test fails**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_storage.py -q`

Expected: `test_read_supports_legacy_data_parquet_files` PASSES (current layout *is* the legacy layout); `test_write_overwrites_partitions_on_rerun` PASSES too (per-date loop overwrites `data.parquet`). Both must KEEP passing after the rewrite — they pin the semantics. If both pass now, proceed; they are regression guards for Step 3.

- [ ] **Step 3: Replace the per-date write loop with `pyarrow.dataset.write_dataset`**

In `zer0factor/storage.py`, add the import:

```python
import pyarrow.dataset as ds
```

Replace the body of `write` (keep the DuckDB block at the end unchanged for now):

```python
    def write(self, factor_name: str, df: pd.DataFrame) -> None:
        required = {"trade_date", "ts_code", "value"}
        if not required.issubset(df.columns):
            raise ValueError(f"DataFrame must have columns: {required}")

        factor_path = self._factor_dir / factor_name
        factor_path.mkdir(parents=True, exist_ok=True)
        if not df.empty:
            frame = df[["ts_code", "value"]].reset_index(drop=True)
            frame["date"] = df["trade_date"].astype(str).to_numpy()
            ds.write_dataset(
                pa.Table.from_pandas(frame, preserve_index=False),
                base_dir=str(factor_path),
                format="parquet",
                partitioning=ds.partitioning(
                    pa.schema([("date", pa.string())]), flavor="hive"
                ),
                existing_data_behavior="delete_matching",
                basename_template="data-{i}.parquet",
            )

        with duckdb.connect(str(self._db_path)) as con:
            con.execute("""
                INSERT INTO factor_registry (factor_name) VALUES (?)
                ON CONFLICT (factor_name) DO UPDATE SET last_updated = now()
            """, [factor_name])
```

Update both globs from `date=*/data.parquet` to `date=*/*.parquet`:
- in `read`: the `pattern` string and the `factor_path.glob(...)` emptiness check
- in `factor_stats`: the `partitions` glob and the `pattern` string

In `factor_stats`, partitions may now contain several files per date directory, so dedupe:

```python
        dates = sorted({p.parent.name.split("=")[1] for p in partitions})
```

- [ ] **Step 4: Run the storage suite**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_storage.py -q`

Expected: PASS (all, including the two new regression guards).

- [ ] **Step 5: Run the full suite (storage is used everywhere)**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add zer0factor/storage.py tests/test_storage.py
git commit -m "perf: write factor partitions in one dataset call"
```

### Task 2: Split storage API into write_partitions / register

**Files:**
- Modify: `zer0factor/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Add failing tests for the split API**

Append to `tests/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run and verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_storage.py -q`

Expected: FAIL with `AttributeError: ... 'write_partitions'` / `TypeError: ... unexpected keyword argument 'init_db'`.

- [ ] **Step 3: Implement the split**

In `zer0factor/storage.py`:

```python
    def __init__(self, factor_dir: Path, db_path: Path, init_db: bool = True):
        self._factor_dir = Path(factor_dir)
        self._db_path = Path(db_path)
        self._factor_dir.mkdir(parents=True, exist_ok=True)
        if init_db:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
```

Split `write` into the three methods (the parquet part of `write` from Task 1 moves verbatim into `write_partitions`; the DuckDB block moves into `register`):

```python
    def write_partitions(self, factor_name: str, df: pd.DataFrame) -> None:
        required = {"trade_date", "ts_code", "value"}
        if not required.issubset(df.columns):
            raise ValueError(f"DataFrame must have columns: {required}")

        factor_path = self._factor_dir / factor_name
        factor_path.mkdir(parents=True, exist_ok=True)
        if df.empty:
            return
        frame = df[["ts_code", "value"]].reset_index(drop=True)
        frame["date"] = df["trade_date"].astype(str).to_numpy()
        ds.write_dataset(
            pa.Table.from_pandas(frame, preserve_index=False),
            base_dir=str(factor_path),
            format="parquet",
            partitioning=ds.partitioning(
                pa.schema([("date", pa.string())]), flavor="hive"
            ),
            existing_data_behavior="delete_matching",
            basename_template="data-{i}.parquet",
        )

    def register(self, factor_name: str) -> None:
        with duckdb.connect(str(self._db_path)) as con:
            con.execute("""
                INSERT INTO factor_registry (factor_name) VALUES (?)
                ON CONFLICT (factor_name) DO UPDATE SET last_updated = now()
            """, [factor_name])

    def write(self, factor_name: str, df: pd.DataFrame) -> None:
        self.write_partitions(factor_name, df)
        self.register(factor_name)
```

- [ ] **Step 4: Run the storage suite**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_storage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add zer0factor/storage.py tests/test_storage.py
git commit -m "feat: split factor storage writes from registry updates"
```

### Task 3: Parallel raw stage

**Files:**
- Modify: `zer0factor/pipeline.py`
- Test: `tests/test_build_rolling_return_factors.py`

- [ ] **Step 1: Add a failing parallel-vs-serial test**

Append to `tests/test_build_rolling_return_factors.py` (note: uses the real `FactorStorage`, because spawn workers reconstruct storage from paths — `FakeStorage` cannot cross a process boundary):

```python
from zer0factor.pipeline import FAMILIES
from zer0factor.storage import FactorStorage


def _seed_base_factors(storage) -> None:
    values = {
        "daily_return": [1.0, 2.0, 3.0, 4.0, 5.0],
        "open_return": [10.0, 20.0, 30.0, 40.0, 50.0],
        "intraday_return": [2.0, 4.0, 6.0, 8.0, 10.0],
        "overnight_return": [5.0, 4.0, 3.0, 2.0, 1.0],
    }
    for name, series in values.items():
        storage.write(name, _base_factor(series))


def test_compute_raw_family_factors_parallel_matches_serial(tmp_path) -> None:
    family = FAMILIES["rolling_return"]
    serial_storage = FactorStorage(tmp_path / "serial", tmp_path / "serial.duckdb")
    parallel_storage = FactorStorage(tmp_path / "parallel", tmp_path / "parallel.duckdb")
    _seed_base_factors(serial_storage)
    _seed_base_factors(parallel_storage)

    serial_rows = compute_raw_family_factors(
        family, storage=serial_storage,
        start_date=None, end_date=None, windows=(5,),
    )
    parallel_rows = compute_raw_family_factors(
        family, storage=parallel_storage,
        start_date=None, end_date=None, windows=(5,), workers=2,
    )

    assert parallel_rows == serial_rows
    for name in serial_rows:
        pd.testing.assert_frame_equal(
            parallel_storage.read(name), serial_storage.read(name)
        )
        assert name in parallel_storage.list_factors()


def test_compute_raw_family_factors_rejects_bad_workers() -> None:
    with pytest.raises(ValueError, match="workers must be >= 1"):
        compute_raw_family_factors(
            FAMILIES["rolling_return"], storage=FakeStorage(),
            start_date=None, end_date=None, workers=0,
        )
```

- [ ] **Step 2: Run and verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q`

Expected: FAIL with `TypeError: ... unexpected keyword argument 'workers'`.

- [ ] **Step 3: Implement the parallel raw stage**

In `zer0factor/pipeline.py`, add imports:

```python
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

from zer0factor.storage import FactorStorage
```

Add `workers` to `compute_raw_family_factors` and dispatch (the existing inline loop body stays exactly as-is for the serial path):

```python
def compute_raw_family_factors(
    family: FactorFamily,
    *,
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    windows: tuple[int, ...] | None = None,
    workers: int = 1,
) -> dict[str, int]:
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    windows = family.windows if windows is None else windows
    if workers > 1:
        return _compute_raw_parallel(
            family,
            storage=storage,
            start_date=start_date,
            end_date=end_date,
            windows=windows,
            workers=workers,
        )
    rows: dict[str, int] = {}
    for base_factor in family.base_factors:
        ...  # existing loop body unchanged
```

Add the parallel runner and the module-level worker (workers resolve the family by name via `get_family` — `FactorFamily` holds callables that may not pickle):

```python
def _storage_paths(storage: Any) -> tuple[Path, Path]:
    factor_dir = getattr(storage, "_factor_dir", None)
    db_path = getattr(storage, "_db_path", None)
    if factor_dir is None or db_path is None:
        raise TypeError("parallel build requires a FactorStorage")
    return Path(factor_dir), Path(db_path)


def _compute_raw_parallel(
    family: FactorFamily,
    *,
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    windows: tuple[int, ...],
    workers: int,
) -> dict[str, int]:
    factor_dir, db_path = _storage_paths(storage)
    tasks = [
        (family.name, base_factor, windows, str(factor_dir), str(db_path), start_date, end_date)
        for base_factor in family.base_factors
    ]
    rows: dict[str, int] = {}
    ctx = multiprocessing.get_context("spawn")
    max_workers = min(workers, len(tasks))
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as pool:
        for task_rows in pool.map(_compute_raw_base_factor_task, tasks):
            rows.update(task_rows)
    for output_name in rows:
        storage.register(output_name)
    return rows


def _compute_raw_base_factor_task(
    args: tuple[str, str, tuple[int, ...], str, str, str | None, str | None],
) -> dict[str, int]:
    family_name, base_factor, windows, factor_dir, db_path, start_date, end_date = args
    family = get_family(family_name)
    storage = FactorStorage(Path(factor_dir), Path(db_path), init_db=False)
    source = _read_required_factor(storage, base_factor, None, end_date)
    panel = _long_to_wide(source)
    rows: dict[str, int] = {}
    for window in windows:
        output_name = family.raw_name(base_factor, window)
        output = to_factor_output(family.derive(panel, window), output_name)
        output = _filter_long_by_date(output, start_date, end_date)
        if output.empty:
            LOGGER.warning("raw factor output is empty: %s", output_name)
        storage.write_partitions(output_name, output)
        rows[output_name] = len(output)
    return rows
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q`

Expected: PASS (the spawn test takes a few extra seconds for interpreter startup).

- [ ] **Step 5: Commit**

```bash
git add zer0factor/pipeline.py tests/test_build_rolling_return_factors.py
git commit -m "feat: parallelize raw factor stage with spawn workers"
```

### Task 4: Parallel preprocess stage

**Files:**
- Modify: `zer0factor/pipeline.py`
- Test: `tests/test_build_rolling_return_factors.py`

- [ ] **Step 1: Add a failing parallel-vs-serial preprocess test**

Append to `tests/test_build_rolling_return_factors.py`:

```python
class FakePro:
    """Parent-process-only stub; workers never see it."""

    def universe(self, *, universe, start_date, end_date, fields):
        codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"]
        return pd.DataFrame({
            "trade_date": ["20240101"] * 6,
            "universe": [universe] * 6,
            "ts_code": codes,
        })

    def index_member_all(self, *, fields):
        codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"]
        industries = ["801780.SI", "801780.SI", "801750.SI", "801750.SI", "801950.SI", "801950.SI"]
        return pd.DataFrame({
            "l1_code": industries,
            "ts_code": codes,
            "in_date": ["20200101"] * 6,
            "out_date": [None] * 6,
        })


def _seed_preprocess_inputs(storage) -> None:
    storage.write("daily_return_ma5", _cross_section_factor())
    storage.write(SIZE_FACTOR_NAME, _size_factor())


def test_preprocess_all_factors_parallel_matches_serial(tmp_path) -> None:
    from zer0factor.pipeline import preprocess_all_factors

    serial_storage = FactorStorage(tmp_path / "serial", tmp_path / "serial.duckdb")
    parallel_storage = FactorStorage(tmp_path / "parallel", tmp_path / "parallel.duckdb")
    _seed_preprocess_inputs(serial_storage)
    _seed_preprocess_inputs(parallel_storage)

    serial_rows = preprocess_all_factors(
        ["daily_return_ma5"],
        storage=serial_storage, pro=FakePro(),
        start_date=None, end_date=None,
        process_universe="univ_trade_base",
    )
    parallel_rows = preprocess_all_factors(
        ["daily_return_ma5"],
        storage=parallel_storage, pro=FakePro(),
        start_date=None, end_date=None,
        process_universe="univ_trade_base",
        workers=2,
    )

    assert parallel_rows == serial_rows
    for name in serial_rows:
        pd.testing.assert_frame_equal(
            parallel_storage.read(name), serial_storage.read(name)
        )
        assert name in parallel_storage.list_factors()
```

- [ ] **Step 2: Run and verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py::test_preprocess_all_factors_parallel_matches_serial -q`

Expected: FAIL with `TypeError: ... unexpected keyword argument 'workers'`.

- [ ] **Step 3: Implement the parallel preprocess stage**

In `zer0factor/pipeline.py`, add `workers: int = 1` to `preprocess_all_factors` and dispatch after the industry panel is built (universe/panel loading stays shared between both paths):

```python
def preprocess_all_factors(
    raw_names: list[str],
    *,
    storage: Any,
    pro: Any,
    start_date: str | None,
    end_date: str | None,
    process_universe: str,
    profiles: tuple[PreprocessProfile, ...] = PROFILES,
    workers: int = 1,
) -> dict[str, int]:
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    ...  # existing universe / raw_panels / industry_panel code unchanged

    if workers > 1 and len(raw_names) > 1:
        return _run_preprocess_parallel(
            raw_names,
            storage=storage,
            universe=universe,
            industry_panel=industry_panel,
            start_date=start_date,
            end_date=end_date,
            profiles=profiles,
            workers=workers,
        )

    rows: dict[str, int] = {}
    ...  # existing serial loop unchanged
```

Add the parallel runner, the worker initializer (panels are shipped once per worker through `initargs`, not once per task), the parquet-only storage adapter, and the worker task:

```python
_WORKER_UNIVERSE: pd.DataFrame | None = None
_WORKER_INDUSTRY_PANEL: pd.DataFrame | None = None


def _init_preprocess_worker(universe: pd.DataFrame, industry_panel: pd.DataFrame) -> None:
    global _WORKER_UNIVERSE, _WORKER_INDUSTRY_PANEL
    _WORKER_UNIVERSE = universe
    _WORKER_INDUSTRY_PANEL = industry_panel


class _PartitionOnlyStorage:
    """Routes writes to write_partitions so workers never open DuckDB."""

    def __init__(self, storage: FactorStorage):
        self._storage = storage

    def read(self, factor_name, start_date=None, end_date=None):
        return self._storage.read(factor_name, start_date=start_date, end_date=end_date)

    def write(self, factor_name, df):
        self._storage.write_partitions(factor_name, df)


def _run_preprocess_parallel(
    raw_names: list[str],
    *,
    storage: Any,
    universe: pd.DataFrame,
    industry_panel: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
    profiles: tuple[PreprocessProfile, ...],
    workers: int,
) -> dict[str, int]:
    factor_dir, db_path = _storage_paths(storage)
    tasks = [
        (raw_name, str(factor_dir), str(db_path), start_date, end_date, profiles)
        for raw_name in raw_names
    ]
    rows: dict[str, int] = {}
    ctx = multiprocessing.get_context("spawn")
    max_workers = min(workers, len(tasks))
    with ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=ctx,
        initializer=_init_preprocess_worker,
        initargs=(universe, industry_panel),
    ) as pool:
        for task_rows in pool.map(_preprocess_factor_task, tasks):
            rows.update(task_rows)
    for output_name in rows:
        storage.register(output_name)
    return rows


def _preprocess_factor_task(
    args: tuple[str, str, str, str | None, str | None, tuple[PreprocessProfile, ...]],
) -> dict[str, int]:
    raw_name, factor_dir, db_path, start_date, end_date, profiles = args
    if _WORKER_UNIVERSE is None or _WORKER_INDUSTRY_PANEL is None:
        raise RuntimeError("preprocess worker is not initialized")
    storage = _PartitionOnlyStorage(
        FactorStorage(Path(factor_dir), Path(db_path), init_db=False)
    )
    return preprocess_one_factor(
        raw_name,
        storage=storage,
        industry_panel=_WORKER_INDUSTRY_PANEL,
        start_date=start_date,
        end_date=end_date,
        universe=_WORKER_UNIVERSE,
        profiles=profiles,
    )
```

Note `workers > 1 and len(raw_names) > 1`: the test above passes a single raw name, so it exercises the serial fallback for the parallel call — `parallel_rows == serial_rows` still validates equivalence, and the spawn path itself is covered by Task 3's raw-stage test plus the multi-name run in Task 6's real build. To cover the spawn preprocess path in tests too, seed a second raw factor copy and pass both names:

```python
def test_preprocess_all_factors_spawn_path_with_two_factors(tmp_path) -> None:
    from zer0factor.pipeline import preprocess_all_factors

    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    _seed_preprocess_inputs(storage)
    storage.write("open_return_ma5", _cross_section_factor())

    rows = preprocess_all_factors(
        ["daily_return_ma5", "open_return_ma5"],
        storage=storage, pro=FakePro(),
        start_date=None, end_date=None,
        process_universe="univ_trade_base",
        workers=2,
    )

    assert len(rows) == 8
    assert all(name in storage.list_factors() for name in rows)
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add zer0factor/pipeline.py tests/test_build_rolling_return_factors.py
git commit -m "feat: parallelize preprocess stage with spawn workers"
```

### Task 5: Wire workers through run_build_stage and the CLI

**Files:**
- Modify: `zer0factor/pipeline.py`
- Modify: `main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Add a failing CLI passthrough test**

Append to `tests/test_main.py` (reuses the settings.toml fixture pattern from the existing build-factors tests):

```python
def test_build_factors_command_passes_workers(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.toml"
    config_path.write_text(
        f"""
[zer0share]
data_dir = "{tmp_path / 'share'}"

[paths]
factor_dir = "{tmp_path / 'factors'}"
db_path = "{tmp_path / 'factor.duckdb'}"
log_path = "{tmp_path / 'factor.log'}"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20240101"
end_date = ""
""".lstrip(),
        encoding="utf-8",
    )
    calls = []

    def fake_run_build_stage(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr("main.run_build_stage", fake_run_build_stage)

    result = CliRunner().invoke(
        cli,
        [
            "--config", str(config_path),
            "build-factors", "--family", "rolling_return",
            "--stage", "raw", "--workers", "16",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["workers"] == 16
```

- [ ] **Step 2: Run and verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_main.py::test_build_factors_command_passes_workers -q`

Expected: FAIL (`--workers` is not a recognized option → exit_code 2, or KeyError on `workers`).

- [ ] **Step 3: Thread workers through run_build_stage**

In `zer0factor/pipeline.py`:

```python
def run_build_stage(
    family_name: str,
    stage: str,
    *,
    storage: Any,
    pro: Any | None = None,
    start_date: str | None,
    end_date: str | None,
    process_universe: str | None = None,
    workers: int = 1,
) -> dict[str, int]:
```

and pass `workers=workers` to both the `compute_raw_family_factors` and `preprocess_all_factors` calls inside it.

- [ ] **Step 4: Add the CLI option**

In `main.py`, on `build_factors_command` add:

```python
@click.option("--workers", type=int, default=1, show_default=True,
              help="Parallel worker processes (1 = serial)")
```

add `workers` to the function signature, and pass `workers=workers` in the `run_build_stage(...)` call.

- [ ] **Step 5: Run the CLI tests**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_main.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add zer0factor/pipeline.py main.py tests/test_main.py
git commit -m "feat: add workers option to factor build command"
```

### Task 6: Final verification and real build

- [ ] **Step 1: Lint the touched files**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run ruff check zer0factor/storage.py zer0factor/pipeline.py main.py tests/test_storage.py tests/test_build_rolling_return_factors.py tests/test_main.py`

Expected: PASS (pre-existing violations in untouched files are out of scope).

- [ ] **Step 2: Run the full test suite**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests -q`

Expected: PASS.

- [ ] **Step 3: Run the real build with timing**

Run: `time uv run python main.py build-factors --family rolling_return --stage all --update-registry --workers 16`

Expected: completes in minutes (raw <1 min, preprocess a few min); prints 160 `name: rows` lines and `registry entries added: N`. Record the wall time in the final report.

- [ ] **Step 4: Verify the output**

Run: `ls data/factors | grep -c "_ma"` → expected `160`; spot-check `uv run python main.py factor-list --orphan` shows no rolling-return orphans.

- [ ] **Step 5: Commit any leftover source changes**

Run: `git status --short` — commit source changes if any remain (config/factors.toml updated by `--update-registry` stays uncommitted for the user to review).
