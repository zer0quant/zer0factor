# Factor Evaluation Pipeline Design

## Purpose

Turn the working single-factor evaluation flow in
`notebooks/01_alphalens_pct_chg.ipynb` into a reusable zer0factor evaluation
pipeline.

The first version should make the notebook workflow repeatable from both Python
and CLI while keeping the implementation small enough to verify. It should also
leave clear extension points for the fuller `Single_Factor_Evaluate_Alens`
metric set.

## Scope

Version 1 supports:

- Python API and thin CLI commands.
- Batch evaluation for one or more stored factors.
- Factor input from `FactorStorage`.
- Return types `open_t1` and `close_t0`, defaulting to `open_t1`.
- Full-market evaluation by default, with optional universe filtering.
- Machine-readable artifacts and PNG figures.

Version 1 does not implement:

- Index excess returns.
- Long and short turnover.
- Full cross-section factor-weighted portfolio returns.
- Quarterly monotonicity stability.
- Automatic factor direction adjustment.
- HTML or Markdown report generation.

These excluded items are planned as stage-two extensions.

## Recommended Approach

Use a layered pipeline rather than directly wrapping the notebook or migrating
the entire legacy evaluator in one pass.

The layers are:

```text
config -> loaders -> alphalens adapter -> metrics -> plots -> artifacts -> pipeline
```

This keeps the first version close to the notebook behavior, but avoids a large
function that becomes hard to extend when turnover, benchmark excess returns,
and report generation are added later.

## Package Structure

Add the following modules under `zer0factor/eval/`:

```text
zer0factor/eval/
├── __init__.py
├── alphalens_adapter.py
├── artifacts.py
├── config.py
├── loaders.py
├── metrics.py
├── pipeline.py
└── plots.py
```

Module responsibilities:

- `config.py`: define `EvaluationConfig` and result dataclasses.
- `loaders.py`: read stored factors, prices, and optional universe panels.
- `alphalens_adapter.py`: convert zer0factor data into Alphalens inputs.
- `metrics.py`: calculate IC summary, quantile returns, and spread metrics.
- `plots.py`: save PNG figures from already-computed data.
- `artifacts.py`: write summary tables, intermediate data, metadata, and figures.
- `pipeline.py`: orchestrate single-factor and multi-factor evaluation.
- `__init__.py`: expose stable public API.

The existing `main.py` CLI should only parse arguments, construct dependencies,
and call the eval API.

## Public API

Define a configuration dataclass:

```python
EvaluationConfig(
    factor_names=("z_neu_daily_return",),
    start_date="20160101",
    end_date="20260401",
    periods=(1, 5, 10),
    quantiles=10,
    return_type="open_t1",
    max_loss=0.35,
    universe=None,
    output_dir=Path("data/evaluations"),
    rolling_ic_window=63,
)
```

Public functions:

```python
evaluate_factor(
    factor_name: str,
    storage: FactorStorage,
    pro,
    config: EvaluationConfig,
) -> FactorEvaluationResult

evaluate_factors(
    factor_names: Sequence[str],
    storage: FactorStorage,
    pro,
    config: EvaluationConfig,
) -> EvaluationRunResult
```

`FactorEvaluationResult` should include:

- `factor_name`
- `clean_factor_data`
- `summary`
- `daily_ic`
- `quantile_returns`
- `figure_paths`

`EvaluationRunResult` should include:

- `run_id`
- `output_dir`
- per-factor results
- combined summary
- metadata path

## CLI

Add a single-factor command:

```bash
uv run python main.py evaluate-factor z_neu_daily_return \
  --periods 1,5,10 \
  --return-type open_t1 \
  --output-dir data/evaluations
```

Add a batch command:

```bash
uv run python main.py evaluate-factors z_ret20_0 z_neu_daily_return \
  --periods 1,5,10
```

Supported options:

```text
--start-date 20160101
--end-date 20260401
--periods 1,5,10
--quantiles 10
--return-type open_t1
--universe zz500
--max-loss 0.35
--output-dir data/evaluations
```

Defaults should come from `config/settings.toml` where applicable:

- `factor_dir`
- `db_path`
- `zer0share.data_dir`
- `start_date`
- `end_date`

CLI options override config file values.

## Data Flow

```text
FactorStorage.read(factor_name)
        +
zer0share.pro_bar(open/close)
        +
optional universe panel
        |
        v
Alphalens input adapter
        |
        v
get_clean_factor_and_forward_returns()
        |
        v
metrics + plots
        |
        v
data/evaluations/<run_id>/<factor_name>/
```

## Artifact Layout

Write each run to a timestamped directory:

```text
data/evaluations/
└── 20260523_153000/
    ├── metadata.json
    ├── summary.csv
    ├── summary.parquet
    └── factors/
        └── z_neu_daily_return/
            ├── clean_factor_data.parquet
            ├── daily_ic.parquet
            ├── quantile_returns.parquet
            └── figures/
                ├── quantile_returns_1D.png
                ├── cumulative_ic.png
                └── rolling_ic_63D.png
```

The run directory prevents accidental overwrites and makes later comparison
across evaluation runs straightforward.

## Core Computation

### Factor Loading

Read stored factor data with:

```python
FactorStorage.read(factor_name, start_date, end_date)
```

Convert it to the Alphalens factor format:

```text
MultiIndex(date, asset) Series
```

Validation rules:

- Required columns are `trade_date`, `ts_code`, and `value`.
- `trade_date` is parsed from `YYYYMMDD` into pandas timestamps.
- The `(date, asset)` index must not contain duplicates.
- Missing factor values are allowed and are handled by Alphalens cleaning.

### Price Loading

Use `zer0share.LocalPro.pro_bar` to read prices.

Return type behavior:

- `open_t1`: build an `open` price matrix and call `shift(-1)` so a factor on
  date `T` maps to a buy price on `T+1`.
- `close_t0`: build a `close` price matrix with no shift.

The price read window should extend beyond the factor end date by at least
`max(periods) + 2` trading observations or a conservative calendar-day buffer.
This avoids losing the tail of the factor sample only because forward returns
cannot be calculated.

### Universe Filtering

`universe=None` means no filtering.

If `universe` is provided, read the universe panel and filter factor samples to
members on the corresponding date. Version 1 only filters factor observations;
it does not trim the price matrix columns.

### Alphalens Cleaning

Call:

```python
alphalens.utils.get_clean_factor_and_forward_returns(
    factor,
    prices,
    quantiles=config.quantiles,
    periods=config.periods,
    max_loss=config.max_loss,
)
```

Save the resulting clean factor data as `clean_factor_data.parquet`.

## Metrics

Version 1 writes the following per-factor data:

- `daily_ic`: from `alphalens.performance.factor_information_coefficient`.
- `quantile_returns`: from
  `alphalens.performance.mean_return_by_quantile(..., by_date=False)`.
- `summary`: one row per factor and period.

Summary columns:

```text
factor_name
return_type
period
sample_count
start_date
end_date
quantiles
IC Mean
IC Std
ICIR
t-stat
IC>0 %
mean_return_q1
mean_return_qN
long_short_spread
long_short_spread_bps
```

`long_short_spread` is fixed as highest quantile minus lowest quantile. Version
1 does not infer factor direction or flip signs automatically.

## Figures

Save these PNG figures for each factor:

- Quantile average return bar chart. Version 1 may save only the first period,
  using the period in the filename.
- Cumulative IC chart with all configured periods.
- Rolling IC chart with all configured periods and
  `config.rolling_ic_window`, defaulting to 63.

Plot functions should accept already-computed `DataFrame` or `Series` objects
and output paths. They should not read factors, prices, or config files.

## Coding Standards

- Keep core logic in `zer0factor/eval/`.
- Keep `main.py` as a thin CLI wrapper.
- Prefer functions and dataclasses over stateful evaluator classes.
- Use `pathlib.Path` for paths.
- Support `YYYYMMDD` strings at module boundaries and normalize internally.
- Do not hard-code local absolute paths.
- Keep Alphalens-specific conversions in `alphalens_adapter.py` and
  `metrics.py`.
- Make artifact-writing functions return the paths they wrote.

## Tests

Add focused tests for:

- Stored factor long table to Alphalens `Series` conversion.
- Duplicate `(date, asset)` factor rows are rejected.
- `open_t1` prices shift by one row and `close_t0` prices do not.
- Universe filtering keeps only in-universe factor observations.
- Summary fields are complete.
- Spread equals highest quantile return minus lowest quantile return.
- Artifact writers create the expected files.
- CLI smoke test with `click.testing.CliRunner`.

Tests should use small in-memory pandas fixtures and temporary directories.
They should not depend on a real zer0share data directory.

## Stage Two Extensions

The first version should leave explicit extension points for:

- `FactorLoader`: external CSV or Parquet factor input.
- `BenchmarkLoader`: index returns and benchmark excess metrics.
- `TurnoverMetrics`: long and short group turnover.
- `DirectionPolicy`: automatic direction detection and sign adjustment.
- `ReportRenderer`: HTML or Markdown reports.
- `FactorCorrelationPipeline`: factor correlation analysis.

These interfaces should not be fully implemented in version 1 unless needed by
the first pipeline. The first implementation should avoid speculative code and
only keep module boundaries clear enough for later additions.
