# Parallel Factor Build Design

**Date:** 2026-06-12
**Status:** Approved

## Problem

`build-factors --family rolling_return --stage all` runs single-process. Measured on real
data (20160101–latest, ~2500 trade dates, ~5300 stocks):

- Each factor write takes ~36s, dominated by `FactorStorage.write` looping over ~2500
  trade dates and writing one tiny parquet file per date.
- The 160-factor family (32 raw + 128 preprocessed) would take well over 2 hours on one
  core of a 128-core machine.

## Goals

1. Cut per-factor write cost by replacing the per-date write loop with a single
   partitioned dataset write.
2. Parallelize the independent per-factor work across processes, controlled by a
   `--workers N` CLI option (default 1 = current serial behavior).

## Non-Goals

- Changing the on-disk layout (`<factor>/date=YYYYMMDD/*.parquet`) or migrating data.
- Parallelizing evaluation commands.

## Design

### 1. Storage write optimization (`zer0factor/storage.py`)

Replace the per-date loop in `FactorStorage.write` with one
`pyarrow.dataset.write_dataset` call:

- Partition column `date` (values = `trade_date` strings), keeping the existing
  `<factor>/date=YYYYMMDD/` hive layout.
- `existing_data_behavior="delete_matching"` so reruns overwrite partitions, matching
  current semantics.
- `basename_template="data-{i}.parquet"`.
- `read()` and `factor_stats()` glob changes from `date=*/data.parquet` to
  `date=*/*.parquet`, which also still matches legacy `data.parquet` files — no
  migration needed.

### 2. Storage API split (`zer0factor/storage.py`)

The DuckDB registry is single-writer, so parallel workers must not touch it
(zer0alpha worked around this with a copy-pasted `_ParquetOnlyFactorStorage` subclass;
we split the API at the source instead):

- `write_partitions(name, df)` — parquet only; safe to call from worker processes.
- `register(name)` — DuckDB registry upsert; called serially by the parent.
- `write(name, df)` — both, signature unchanged; existing callers unaffected.
- `FactorStorage(..., init_db=False)` — skip the `CREATE TABLE` on init so concurrent
  worker processes never open the DuckDB file for write.

### 3. Process-pool parallelism (`zer0factor/pipeline.py`)

Both family build functions gain a `workers: int = 1` keyword. `workers == 1` keeps the
exact current inline code path; `workers > 1` uses a
`ProcessPoolExecutor(mp_context=multiprocessing.get_context("spawn"))`.

**spawn, not fork:** `main.py` configures loguru with `enqueue=True`, which starts a
background logging thread; forking a multi-threaded process risks deadlock in children.
spawn starts workers from a clean state. The cost — pickling shared panels once per
worker via the pool `initializer` — is acceptable (seconds, 251 GB RAM).

- `compute_raw_family_factors(family, ..., workers)`: parallel over `family.base_factors`
  (one task per base factor; each task reads its stored base factor, derives all
  windows, calls `storage.write_partitions`, returns `{name: rows}`).
- `preprocess_all_factors(..., workers)`: parent loads universe and industry panel once
  (as today), then submits one task per raw factor name. Panels reach workers through
  the pool initializer (module globals in the child), not per-task pickling. Each task
  runs `preprocess_one_factor` against an `init_db=False`, parquet-only storage handle
  and returns `{name: rows}`.
- The parent collects results and calls `storage.register(name)` for every written
  factor, serially.
- Worker task functions are module-level (spawn requires picklable callables).
- A worker exception propagates and fails the build (same as serial behavior).

### 4. CLI (`main.py`)

`build-factors` gains `--workers N` (default 1, same as zer0alpha), passed through
`run_build_stage` to both stages.

## Testing

- Storage: write→read roundtrip equivalence; rerun produces no duplicate rows
  (delete_matching); a hand-written legacy `date=*/data.parquet` file is still readable;
  `write_partitions` does not touch the registry, `register` does.
- Pipeline: existing `workers=1` tests unchanged; integration test with `workers=2`,
  a real tmp-dir `FactorStorage`, and spawn pool asserting results identical to the
  serial run (raw stage end-to-end; preprocess worker function tested in-process with
  initializer globals plus one spawn smoke test).
- CLI: `--workers` passthrough test.

## Expected outcome

Raw stage ~19 min → under 1 min; preprocess stage ~2 h → minutes. Single-process
(`workers=1`) behavior is preserved bit-for-bit.
