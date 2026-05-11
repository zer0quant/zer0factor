# zer0factor Standard Factor Contract

Generated factors must target zer0factor, not Qlib.

## Standard Fields

Allowed `FactorFrame` fields:

| Field | Meaning |
|---|---|
| `open` | adjusted open |
| `high` | adjusted high |
| `low` | adjusted low |
| `close` | adjusted close |
| `volume` | volume, mapped from zer0share `vol` |
| `amount` | turnover amount |
| `return_` | return series or mapped/calculated percent change |

Default adjustment is `hfq`.

## Required Spec

```python
FactorSpec(
    name="volume_adjusted_momentum_20d",
    inputs=["close", "volume"],
    min_window=20,
    recommended_window=60,
    frequency="1d",
    adjust="hfq",
)
```

Rules:

- `name` must be stable `snake_case`.
- `inputs` must contain only the minimal fields the factor reads.
- `min_window` must cover the longest rolling/shift/pct_change/correlation
  dependency.
- `recommended_window` must be greater than or equal to `min_window`.
- `output_schema` is always `trade_date, ts_code, value`.

## Data Separation

Factor code must not call zer0share, DuckDB, parquet readers, network APIs, or
local file paths. Data source changes belong in the provider layer.

Generated factor logic may use:

```python
data.close
data.volume
data.amount
```

Generated factor logic must return:

```python
to_factor_output(value, self.spec.name)
```

where `value` is a wide panel:

```text
index: trade_date
columns: ts_code
values: factor value
```

## Common Window Rules

- `x.shift(n)` requires at least `n + 1` rows when comparing current to shifted
  values, but declare `min_window=n` for conventional factor metadata unless a
  rolling window also needs more.
- `x.rolling(n)` requires `n`.
- `x.pct_change(n)` requires `n + 1` observations; declare `min_window=n`.
- Rolling correlation/covariance with `n` requires `n`.
- Combining windows uses the maximum required window.

