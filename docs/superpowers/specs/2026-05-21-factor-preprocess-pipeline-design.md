# Factor Preprocess Pipeline Design

## Purpose

Add a standard cross-sectional factor preprocessing pipeline for zer0factor.
The pipeline prepares raw factor values for later evaluation and portfolio
construction while keeping raw factor computation separate from preprocessing.

The required processing order is fixed:

```text
winsorize -> impute -> standardize -> neutralize
```

Initial implementation scope:

- Implement winsorization.
- Implement cross-sectional missing value imputation.
- Implement cross-sectional standardization.
- Add a stable neutralization interface, but do not implement regression until
  reliable size and industry exposure data are available.

## Non-Goals

- Do not change `Factor.compute()` or the `run_factor()` contract.
- Do not automatically preprocess factors before storage.
- Do not implement industry median imputation until an industry panel source is
  available.
- Do not implement size or industry neutralization with placeholder data.
- Do not change existing storage layout.

## Module Layout

Add a new package:

```text
zer0factor/preprocess/
├── __init__.py
├── pipeline.py
├── winsorize.py
├── impute.py
├── standardize.py
└── neutralize.py
```

Responsibilities:

- `pipeline.py`: public config object and `FactorPreprocessPipeline`.
- `winsorize.py`: cross-sectional outlier handling.
- `impute.py`: missing value filling.
- `standardize.py`: z-score and rank normalization.
- `neutralize.py`: neutralization interface and validation errors.
- `__init__.py`: export the public API.

## Public API

```python
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig

config = PreprocessConfig(
    winsorize_method="mad",
    winsorize_n=5.0,
    impute_method="cross_section_median",
    standardize_method="zscore",
    neutralize_method=None,
)

processed = FactorPreprocessPipeline(config).transform(factor)
```

Supported factor input forms:

- Wide panel: `index=trade_date`, `columns=ts_code`, values are factor values.
- Standard long table: columns `trade_date`, `ts_code`, `value`.

Output format defaults to the input format. A long table input returns a long
table with the same standard columns. A wide input returns a wide panel.

## Configuration

`PreprocessConfig` fields:

```python
@dataclass(frozen=True)
class PreprocessConfig:
    winsorize_method: Literal["mad", "quantile", "none"] = "mad"
    winsorize_n: float = 5.0
    winsorize_lower_quantile: float = 0.01
    winsorize_upper_quantile: float = 0.99
    impute_method: Literal["cross_section_median", "industry_median", "none"] = (
        "cross_section_median"
    )
    standardize_method: Literal["zscore", "rank_pct", "none"] = "zscore"
    neutralize_method: Literal["size_industry", "none"] | None = None
```

Validation rules:

- `winsorize_n` must be positive.
- Quantile bounds must satisfy `0 <= lower < upper <= 1`.
- Unknown method names raise `ValueError`.
- `industry_median` requires an industry panel.
- `size_industry` requires exposure data and raises a clear error in the first
  implementation if regression is requested.

## Data Conversion

The pipeline normalizes input into a wide panel internally:

- Long input is pivoted by `trade_date` and `ts_code`.
- `trade_date` is parsed with `pandas.to_datetime`.
- Columns are sorted by `ts_code`; index is sorted by date.
- After processing, long input is converted back to
  `trade_date, ts_code, value` using the existing zer0factor schema.

This keeps the preprocessing functions simple: every core operation receives and
returns a wide `pandas.DataFrame`.

## Winsorization

Winsorization is applied independently for each trade date.

Supported methods:

- `mad`: median absolute deviation clipping.
- `quantile`: lower and upper quantile clipping.
- `none`: no operation.

MAD method:

```text
median = cross-sectional median
mad = median(abs(x - median))
lower = median - n * mad
upper = median + n * mad
```

Values outside `[lower, upper]` are clipped to the boundary.

Edge cases:

- If a row has no valid observations, return it unchanged.
- If `mad` is zero or NaN, skip clipping for that row.
- NaNs remain NaN; imputation happens in the next step.

## Missing Value Imputation

Imputation is applied independently for each trade date.

Initial supported methods:

- `cross_section_median`: fill NaNs with that date's cross-sectional median.
- `none`: leave NaNs unchanged.

Reserved method:

- `industry_median`: reserved for future work. If selected without an industry
  panel, raise `ValueError("industry_median imputation requires industry data")`.

Edge cases:

- If an entire row is NaN, it remains NaN.
- Infinite values are treated as missing before imputation.

## Standardization

Standardization is applied independently for each trade date.

Supported methods:

- `zscore`: `(x - mean) / std`.
- `rank_pct`: percentile rank between 0 and 1.
- `none`: no operation.

Z-score behavior:

- Use sample standard deviation, matching pandas default behavior.
- If a row has fewer than two valid observations, return NaN for that row.
- If the row standard deviation is zero or NaN, return NaN for that row.

Rank behavior:

- Use `rank(pct=True)` across each date.
- NaNs remain NaN.

## Neutralization Interface

The first implementation exposes the interface but does not perform regression.
This avoids producing false precision before zer0factor has reliable exposure
data.

Planned transform signature:

```python
processed = pipeline.transform(
    factor,
    exposures={
        "size": size_panel,
        "industry": industry_panel,
    },
)
```

If `neutralize_method="size_industry"` is configured in the initial
implementation, `transform()` raises:

```text
ValueError: neutralization requires implemented exposure regression support
```

Future implementation target:

- Regress each date's factor values on log size and industry dummies.
- Return residuals as neutralized factor values.
- Optionally add `post_neutralize_standardize=True` later, but keep it disabled
  in the first scope to preserve the strict documented order.

## Error Handling

Errors should be explicit and early:

- Invalid config values raise `ValueError` during config construction or
  pipeline initialization.
- Missing required columns in long input raise `ValueError`.
- Unsupported factor input types raise `TypeError`.
- Industry imputation without industry data raises `ValueError`.
- Neutralization requests raise a clear `ValueError` until regression support is
  implemented.

## Testing Plan

Add tests focused on behavior and data contracts:

- MAD winsorization clips an extreme cross-sectional value.
- Quantile winsorization clips to configured quantiles.
- Cross-sectional median imputation fills per date.
- Entirely missing rows remain missing.
- Z-score standardization produces cross-sectional mean near zero and sample
  standard deviation near one.
- Z-score returns NaN when standard deviation is zero.
- Rank standardization outputs percentile ranks in `(0, 1]`.
- Pipeline applies steps in the fixed order.
- Wide input returns wide output.
- Long input returns `trade_date, ts_code, value`.
- `industry_median` without industry data raises a clear error.
- `size_industry` neutralization raises a clear not-implemented error.

## Acceptance Criteria

- Existing tests continue to pass.
- New preprocessing tests pass.
- The public API is importable from `zer0factor.preprocess`.
- Raw factor computation and storage remain unchanged.
- No neutralized values are produced until exposure regression is actually
  implemented.
