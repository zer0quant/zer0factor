# Factor Neutralization Design

## Purpose

Implement cross-sectional factor neutralization now that size and industry data
are available locally. Neutralization removes broad size and industry exposure
from a preprocessed factor and stores the residual as a new factor.

Default neutralization target:

```text
factor -> size + SW L1 industry OLS -> residual
```

## Naming Standard

Neutralized factors use:

```text
neu_z_<factor_name>
```

Examples:

```text
z_ret20_0 -> neu_z_ret20_0
z_rank_mom120_20 -> neu_z_rank_mom120_20
```

The `z_` prefix means the source factor has already gone through standard
cross-sectional preprocessing. The `neu_` prefix means the stored value is the
neutralization residual.

## Default Exposures

Use these defaults:

- Size exposure: `z_log_circulating_market_cap`
- Industry exposure: SW L1 industry from `zer0share.LocalPro.index_member_all`

Rationale:

- `z_log_circulating_market_cap` is already stored in `data/factors`, so it is
  consistent with the project naming standard and avoids recomputing size.
- SW L1 is the default A-share industry neutralization choice.
- Circulating market cap better reflects tradable size than total market cap.

## Public API

Keep the existing preprocessing pipeline API:

```python
FactorPreprocessPipeline(
    PreprocessConfig(neutralize_method="size_industry")
).transform(
    factor,
    exposures={
        "size": size_panel,
        "industry": industry_panel,
    },
)
```

`factor` and `size` are wide panels:

```text
index: trade_date
columns: ts_code
values: numeric exposure/factor values
```

`industry` is a wide panel:

```text
index: trade_date
columns: ts_code
values: industry code, such as SW L1 l1_code
```

## OLS Behavior

Neutralization runs independently for each trade date.

For each date:

1. Align factor, size, and industry by `ts_code`.
2. Drop rows where the factor value is missing.
3. Drop rows where size or industry exposure is missing.
4. Build a design matrix with:
   - intercept
   - size exposure
   - industry one-hot dummies
5. Drop one industry dummy to avoid perfect collinearity with the intercept.
6. Solve least squares with `numpy.linalg.lstsq`.
7. Return residuals for stocks included in the regression.
8. Stocks excluded due to missing data remain `NaN`.

If a date does not have enough valid rows to estimate the model, return `NaN`
for that date.

Minimum row rule:

```text
valid_rows > number_of_regression_columns
```

This avoids fitting a saturated model with zero residual by construction.

## Industry Exposure Builder

Add a helper that converts zer0share industry membership history into a wide
daily industry panel.

Input source:

```python
pro.index_member_all(fields="l1_code,l1_name,ts_code,in_date,out_date,is_new")
```

Behavior:

- Default source is SW L1 via `index_member_all`.
- Each stock is assigned to an industry on dates where:

```text
in_date <= trade_date and (out_date is missing or trade_date <= out_date)
```

- The date index should come from the factor or size panel being neutralized,
  not from a separate calendar query.
- If multiple memberships match the same stock/date, choose the row with the
  latest `in_date`.
- Use `l1_code` as the industry exposure value.

## Storage Helper

Add a helper to neutralize an already stored factor:

```python
neutralize_stored_factor(
    factor_name="z_ret20_0",
    output_name="neu_z_ret20_0",
    storage=storage,
    pro=pro,
    start_date="20160101",
    end_date=None,
    size_factor_name="z_log_circulating_market_cap",
)
```

The helper:

1. Reads the source factor from `FactorStorage`.
2. Reads `z_log_circulating_market_cap` from `FactorStorage`.
3. Builds SW L1 industry exposure for the same dates and stock universe.
4. Calls the existing preprocessing pipeline with `neutralize_method="size_industry"`.
5. Stores the residual factor under `output_name`.
6. Returns the number of stored rows.

## CLI

Add a command:

```bash
uv run python main.py neutralize-factor z_ret20_0
```

Default output name:

```text
neu_<input_factor_name>
```

Example:

```bash
uv run python main.py neutralize-factor z_ret20_0
```

Stores:

```text
neu_z_ret20_0
```

Options:

```text
--output-name
--size-factor-name
--start-date
--end-date
```

Defaults:

- `--size-factor-name z_log_circulating_market_cap`
- `--start-date` uses config start date
- `--end-date` uses config end date

## Error Handling

- `neutralize(method="size_industry")` requires `exposures["size"]` and
  `exposures["industry"]`.
- Missing size factor in storage raises `FileNotFoundError`.
- Missing industry data raises the zer0share `FileNotFoundError` with its
  existing message.
- Unknown neutralization method still raises `ValueError`.
- Dates with insufficient valid rows return `NaN` rather than raising.

## Tests

Add tests for:

- Size-only synthetic neutralization through a helper or direct `neutralize`
  call.
- Size + industry synthetic neutralization where residuals are orthogonal to
  size and industry dummies.
- Missing size or industry exposure raises a clear `ValueError`.
- Insufficient rows return all `NaN` for that date.
- Pipeline `neutralize_method="size_industry"` calls the implemented
  neutralizer and preserves long-table output.
- Industry membership history converts to a daily date x stock panel, including
  `in_date/out_date` handling and overlapping membership resolution by latest
  `in_date`.
- Stored-factor helper reads source and size factors, writes `neu_z_*`, and
  returns a row count.
- CLI command is registered and derives `neu_<input_factor_name>` by default.

## Acceptance Criteria

- `neutralize(method="size_industry")` no longer raises the previous
  not-implemented error when valid exposures are supplied.
- Existing preprocessing tests continue to pass.
- A stored `z_` factor can be neutralized against
  `z_log_circulating_market_cap` and SW L1 industry, then written as
  `neu_z_*`.
- Market-cap factors themselves are not automatically neutralized.
