# Market Cap Factor Preprocess Design

## Purpose

Add total market cap and circulating market cap as first-class zer0factor
factors. Market cap is both a useful standalone style factor and future
neutralization exposure data, so it must be computed, preprocessed, and stored
like other factors instead of existing only as hidden regression input.

## Naming Standard

Use short, stable prefixes for processing state:

- Raw factor: no processing-state prefix.
- Z-scored standard preprocessing result: `z_`.
- Future neutralized result: `neu_z_`.

Do not encode every preprocessing detail in the factor name. MAD winsorization
and missing-value imputation are part of the standard preprocessing contract,
not part of the semantic factor identity.

Market cap factors to store:

```text
log_total_market_cap
log_circulating_market_cap
z_log_total_market_cap
z_log_circulating_market_cap
```

## Data Source

Use `zer0share.LocalPro.daily_basic`.

Required source fields:

```text
ts_code, trade_date, total_mv, circ_mv
```

Field meanings:

- `total_mv`: total market cap.
- `circ_mv`: circulating market cap.

Both source values are treated as numeric market cap values from zer0share. The
factor layer does not rescale units; it applies natural log consistently to the
source values.

## FactorFrame Fields

Extend `zer0factor.core.STANDARD_FIELDS` with:

```text
total_mv
circ_mv
```

Provider behavior:

- Existing OHLCV and amount fields continue to load through `pro_bar`.
- `total_mv` and `circ_mv` load through `daily_basic`.
- A single `history()` call may request both market data fields and market cap
  fields. The provider returns one `FactorFrame` containing all requested wide
  panels.

## Built-In Factors

Add a new module:

```text
zer0factor/factors/market_cap.py
```

Add two factor classes:

```python
class LogTotalMarketCap(Factor):
    spec = FactorSpec(
        name="log_total_market_cap",
        inputs=["total_mv"],
        min_window=1,
        frequency="1d",
        adjust=None,
    )


class LogCirculatingMarketCap(Factor):
    spec = FactorSpec(
        name="log_circulating_market_cap",
        inputs=["circ_mv"],
        min_window=1,
        frequency="1d",
        adjust=None,
    )
```

Computation rule:

```text
log(value) when value > 0
NaN when value <= 0 or missing
```

Use natural log.

## Preprocessed Factors

Preprocessed market cap factors are created from the raw log factors, not from
raw `total_mv` or `circ_mv`.

Processing configuration:

```python
PreprocessConfig(
    winsorize_method="mad",
    winsorize_n=5.0,
    impute_method="cross_section_median",
    standardize_method="zscore",
    neutralize_method=None,
)
```

Output names:

```text
z_log_total_market_cap
z_log_circulating_market_cap
```

No neutralization is applied to market cap factors. Market cap is the size style
factor itself; neutralizing it against size would remove the intended signal.

## CLI

Add a command:

```bash
uv run python main.py compute-market-cap
```

The command:

1. Loads `total_mv` and `circ_mv` through `Zer0ShareDataProvider`.
2. Computes and stores `log_total_market_cap`.
3. Computes and stores `log_circulating_market_cap`.
4. Applies the standard preprocessing pipeline to each raw log factor.
5. Stores `z_log_total_market_cap`.
6. Stores `z_log_circulating_market_cap`.

This command is separate from `compute-returns` to keep the data-source and
factor-family behavior explicit.

## Storage Behavior

Use the existing `FactorStorage.write()` format:

```text
trade_date, ts_code, value
```

Raw log factors and z-scored factors are stored as separate factor names. This
keeps auditability: raw factor definitions remain available when investigating
or changing preprocessing settings.

## Error Handling

- If `daily_basic` does not return a requested market cap column, raise
  `ValueError("zer0share result missing source column: <column>")`, matching
  existing provider behavior.
- Non-positive market cap values become missing factor values before output.
- The preprocessing pipeline keeps its current behavior for all-NaN rows and
  zero-variance rows.

## Testing Plan

Add tests for:

- `FactorSpec` accepts `total_mv` and `circ_mv`.
- `FactorFrame` exposes `total_mv` and `circ_mv`.
- `Zer0ShareDataProvider.history()` loads market cap fields from
  `daily_basic`.
- A mixed request such as `["close", "total_mv"]` combines `pro_bar` and
  `daily_basic` panels.
- `LogTotalMarketCap` computes natural log for positive values and omits
  non-positive values from standard factor output.
- `LogCirculatingMarketCap` computes natural log from `circ_mv`.
- The market cap storage helper or CLI path writes all four factor names:
  `log_total_market_cap`, `log_circulating_market_cap`,
  `z_log_total_market_cap`, and `z_log_circulating_market_cap`.
- Existing tests continue to pass.

## Acceptance Criteria

- Market cap data is available as standard `FactorFrame` fields.
- Raw log total and circulating market cap factors can be computed and stored.
- Z-scored versions can be computed through the existing preprocessing pipeline
  and stored under the approved `z_` naming convention.
- Existing return factor behavior is unchanged.
