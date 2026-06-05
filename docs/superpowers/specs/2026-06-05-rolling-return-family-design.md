# Rolling Return Family Design

## Context

`zer0factor` already has four built-in return factors:

- `daily_return`
- `open_return`
- `intraday_return`
- `overnight_return`

These daily-level factors are noisy and unstable when evaluated directly. The next step is to build rolling mean variants over common windows:

- `5, 10, 20, 30, 60, 90, 120, 180`

The resulting raw family has 32 factors. The design should migrate the useful family/profile/pipeline structure from `zer0alpha`, while keeping the `zer0factor` decision that rolling return raw factors are derived from already stored base return factors rather than recomputed from `open` and `close` market data.

## Goals

- Build 32 rolling mean return factors from stored base return factors.
- Use `min_periods = window // 2` for rolling means.
- Migrate `zer0alpha`'s four preprocessing profiles:
  - `z_`
  - `z_size_neu_`
  - `z_industry_neu_`
  - `z_size_industry_neu_`
- Add a family-based build workflow that can later support more factor families.
- Optionally append rolling return metadata to `config/factors.toml` without overwriting existing entries.

## Non-Goals

- Do not auto-run `compute-returns` when base return factors are missing.
- Do not migrate `zer0alpha` notifications, parallel evaluation, resume logic, or full analysis report tooling in this first version.
- Do not replace the existing `compute-returns`, `standardize-factor`, `neutralize-factor`, or evaluation commands.
- Do not default to evaluating raw rolling factors.

## Architecture

### Rolling Return Family

Add `zer0factor/factors/rolling_returns.py`.

This module defines:

- `WINDOWS = (5, 10, 20, 30, 60, 90, 120, 180)`
- Base factor names:
  - `daily_return`
  - `open_return`
  - `intraday_return`
  - `overnight_return`
- Raw rolling factor names:
  - `daily_return_ma5` through `daily_return_ma180`
  - `open_return_ma5` through `open_return_ma180`
  - `intraday_return_ma5` through `intraday_return_ma180`
  - `overnight_return_ma5` through `overnight_return_ma180`

Unlike `zer0alpha.factors.rolling_returns`, this module does not recompute returns from a `FactorFrame`. Instead, the raw stage reads the stored base factor, pivots it to a wide date-by-code panel, computes the rolling mean, and writes the standard long schema.

### Family Pipeline

Add a lightweight family pipeline module at `zer0factor/pipeline.py`.

Core types:

```python
@dataclass(frozen=True)
class PreprocessProfile:
    key: str
    prefix: str
    neutralize_method: str | None

    def output_name(self, raw_factor_name: str) -> str:
        return f"{self.prefix}{raw_factor_name}"


@dataclass(frozen=True)
class FactorFamily:
    name: str
    raw_names: Callable[[], tuple[str, ...]]

    def preprocess_output_names(self) -> list[str]:
        ...

    def all_factor_names(self) -> list[str]:
        ...
```

Profiles:

```python
PROFILES = (
    PreprocessProfile("z", "z_", None),
    PreprocessProfile("z_size_neu", "z_size_neu_", "size"),
    PreprocessProfile("z_industry_neu", "z_industry_neu_", "industry"),
    PreprocessProfile("z_size_industry_neu", "z_size_industry_neu_", "size_industry"),
)
```

Initial registry:

```python
FAMILIES = {
    "rolling_return": FactorFamily(...),
}
```

This mirrors `zer0alpha`'s family/profile model but omits unrelated orchestration until there is a concrete need.

## Data Flow

### Raw Stage

`build-factors --family rolling_return --stage raw`:

1. Resolve config, storage path, date range, and family.
2. For each base factor:
   - Read the stored long factor from `FactorStorage`.
   - Validate columns: `trade_date`, `ts_code`, `value`.
   - Fail if duplicated `trade_date/ts_code` pairs exist.
   - Pivot to a wide panel.
3. For each window:
   - Compute `panel.rolling(window=window, min_periods=window // 2).mean()`.
   - Convert back to standard long schema.
   - Write to storage under `<base>_ma<window>`.

The raw stage requires the four base factors to already be present. If any are missing, it fails fast with the missing factor name.

### Preprocess Stage

`build-factors --family rolling_return --stage preprocess`:

1. Load the process universe from `cfg.process_universe`.
2. Load all raw rolling factor panels and filter them to the process universe.
3. Build the SW level-1 industry panel for the raw factor date/code coverage.
4. Load the size exposure factor `z_log_circulating_market_cap`.
5. For each raw factor:
   - Apply MAD winsorization.
   - Apply cross-section median imputation.
   - Apply z-score standardization. This writes `z_<raw>`.
   - Neutralize the standardized panel by size, industry, and size+industry.
   - Re-standardize each residual and write:
     - `z_size_neu_<raw>`
     - `z_industry_neu_<raw>`
     - `z_size_industry_neu_<raw>`

`--stage preprocess` does not compute missing raw factors. Users can run `--stage all` to execute raw then preprocess.

### All Stage

`build-factors --family rolling_return --stage all` runs raw first, then preprocess.

## CLI

Add a unified family build command:

```bash
uv run python main.py build-factors --family rolling_return --stage all
uv run python main.py build-factors --family rolling_return --stage raw
uv run python main.py build-factors --family rolling_return --stage preprocess
```

Options:

- `--family rolling_return`: factor family to build.
- `--stage raw|preprocess|all`: build stage, default `all`.
- `--start-date`: override `settings.toml`.
- `--end-date`: override `settings.toml`; empty config value means latest.
- `--registry config/factors.toml`: registry file to update when requested.
- `--update-registry`: append missing rolling return entries to the registry.

The first version stays single-process. A future `--workers` option can reuse the parallel preprocessing pattern from `zer0alpha` once the single-process path is stable.

## Registry

`config/factors.example.toml` should include generated rolling return registry entries as documentation and a ready-to-copy example.

When `--update-registry` is provided, `config/factors.toml` is updated by appending missing entries only. Existing entries are not overwritten.

Registration rules:

- Raw factors are registered with `enabled = false` and `evaluate.default = false`.
- Profile factors are registered with `enabled = true` and `evaluate.default = true`.
- `z_<raw>` uses `source_type = "derived"`.
- Neutralized profiles use `source_type = "neutralized"`.
- `source_factor = "<raw>"`.
- `category = "price"`.
- Tags include:
  - `rolling_return`
  - base factor name, such as `daily_return`
  - `ma`
  - window tag, such as `ma20`
  - profile key, such as `z_size_industry_neu`

Default evaluation config for profile factors:

```toml
[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
```

Raw factors either omit evaluation config or set:

```toml
[factors.evaluate]
default = false
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
```

## Error Handling

- Missing base return factor: fail with `required factor missing: <name>`.
- Duplicate long factor rows: fail with `factor data contains duplicate trade_date/ts_code`.
- Empty process universe: fail with `process universe returned no rows`.
- Missing raw factor during preprocess: fail with `required factor missing: <raw>`.
- Missing size factor during neutralization: fail with `required factor missing: z_log_circulating_market_cap`.
- Empty rolling output: write zero rows and log a warning with the output name.
- Unknown family: fail with the list of known families.
- Invalid stage: let Click enforce `raw`, `preprocess`, or `all`.
- Registry update conflicts: append missing names only; never rewrite existing entries.

## Testing

Add focused tests:

- `tests/test_rolling_return_family.py`
  - `rolling_return` has 32 raw names.
  - It expands to 128 profile names and 160 total family names.
  - First and last raw names match `zer0alpha`: `daily_return_ma5`, `overnight_return_ma180`.
  - `z_size_industry_neu_overnight_return_ma180` is present.

- `tests/test_build_rolling_return_factors.py`
  - Raw rolling factors are derived from stored base factor panels.
  - `min_periods = window // 2`.
  - Long-to-wide conversion rejects duplicate rows.
  - Missing base factor fails fast.

- `tests/test_factor_pipeline.py`
  - Four profiles produce the expected output names.
  - `preprocess_one_factor` writes `z_`, `z_size_neu_`, `z_industry_neu_`, and `z_size_industry_neu_`.
  - Neutralized outputs use size and industry exposures.

- `tests/test_main.py`
  - `build-factors --family rolling_return --stage raw` dispatches raw only.
  - `--stage preprocess` dispatches preprocess only.
  - `--stage all` dispatches raw then preprocess.
  - Unknown family fails clearly.
  - `--update-registry` appends missing entries and does not overwrite existing entries.

Run existing regression tests around:

- base return factors
- storage
- preprocessing
- neutralization
- registry
- batch evaluation

## Future Extensions

This design deliberately leaves room for later families:

- volatility-adjusted return factors
- cross-section rank return factors
- intraday volatility factors
- MA bias factors

Those should reuse the same `FactorFamily`, `PreprocessProfile`, `build-factors`, and optional registry update flow.
