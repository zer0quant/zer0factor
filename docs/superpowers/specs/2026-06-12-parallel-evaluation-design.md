# Parallel Factor Evaluation Design

**Date:** 2026-06-12
**Status:** Approved

## Problem

`evaluate_factors` evaluates factors serially. Each factor's evaluation (alphalens clean
factor computation, IC/quantile metrics, artifact + figure writing) is independent and
CPU-bound; evaluating the 160-factor rolling return family one at a time wastes a
128-core machine.

## Goals

Parallelize the per-factor loop in `evaluate_factors` behind a `workers: int = 1`
keyword, exposed as `--workers` on `evaluate-factors` and `evaluate-batch`.
`workers == 1` keeps the current serial path bit-for-bit.

## Non-Goals

- Parallelizing within a single factor's evaluation.
- Changing on-disk artifact layout or the report pipeline (both read from `run_dir`).

## Design

Same architecture as the parallel build (`2026-06-12-parallel-factor-build-design.md`):
spawn-based `ProcessPoolExecutor` (loguru `enqueue=True` in `main.py` makes fork
unsafe), shared data shipped once per worker via the pool initializer.

### Pipeline (`zer0factor/eval/pipeline.py`)

- Parent loads `price_data` and `universe_panel` once (unchanged), creates the run dir,
  then submits one task per factor name.
- Pool initializer receives `(storage, pro, config, run_dir, price_data,
  universe_panel)` and stores them in module globals in the worker. `FactorStorage`
  pickles as two paths and unpickling does not re-run `__init__`, so workers never
  touch DuckDB (evaluation only reads). `pro` must be picklable — `LocalPro` holds only
  a data dir; test fakes are module-level classes.
- Each worker task runs the existing `evaluate_factor(...)` (artifacts and figures are
  written to `run_dir/factors/<name>/` exactly as today, matplotlib is already Agg)
  and returns only `(factor_name, summary)` — the large frames
  (`clean_factor_data`, `daily_ic`, `quantile_returns`) are not pickled back.
- The parent assembles `FactorEvaluationResult`s in the original factor order with the
  returned summary, `output_dir` set, and empty DataFrames for the large fields
  (documented on the function). Disk artifacts are complete; CLI and report consumers
  only use `run_id` / `output_dir` / summary / artifact files.
- A worker exception propagates and fails the run, matching serial behavior.

### CLI (`main.py`)

`evaluate-factors` and `evaluate-batch` gain `--workers N` (default 1), threaded
through `_run_evaluation_job` into `evaluate_factors`.

## Testing

- Parallel-vs-serial equivalence: real tmp-dir `FactorStorage` + module-level fake pro,
  `workers=2`; assert identical summary frames (modulo row order) and identical artifact
  files on disk.
- `workers=1` path untouched — existing tests unchanged.
- CLI `--workers` passthrough tests for both commands.

## Expected outcome

Evaluation of N factors approaches `serial_time / min(workers, N)` plus the one-off
price load; the 160-factor family becomes evaluable in one run.
