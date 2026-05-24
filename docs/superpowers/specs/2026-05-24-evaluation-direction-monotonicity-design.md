# Evaluation Direction And Monotonicity Report Design

## Purpose

Improve `evaluate-summary` so the report can recognize reverse-effective
factors and judge quantile monotonicity. The feature only reads completed
evaluation artifacts. It does not recompute factor evaluation.

## Scope

Enhance `ranked_summary.csv` and `report.md` with:

- `direction`
- `adjusted_spread_bps`
- `monotonicity`
- `adjusted_score`

Keep the existing raw `long_short_spread_bps` and `score` columns for debugging.

## Direction

Direction is inferred per `factor_name + period` row:

- `direction = 1` when `IC Mean >= 0`
- `direction = -1` when `IC Mean < 0`

This is intentionally simple for the first version. Later versions can infer a
factor-level direction across periods.

## Adjusted Spread

Use direction to make positive values mean useful separation:

```text
adjusted_spread_bps = long_short_spread_bps * direction
```

The report pass rule uses `adjusted_spread_bps`, not raw
`long_short_spread_bps`.

## Monotonicity

Read per-factor `quantile_returns.parquet` from:

```text
<run_dir>/factors/<factor_name>/quantile_returns.parquet
```

For each period, compute the Spearman correlation between quantile rank and
mean quantile return, then multiply by `direction`:

```text
monotonicity = spearman(quantile_number, quantile_return[period]) * direction
```

If the file, period, or enough quantile rows are missing, `monotonicity` is
missing and the row fails the monotonicity rule only if a minimum monotonicity
threshold is configured.

## Rules

Default pass thresholds become:

- `IC Mean` absolute direction is handled by `direction`
- `abs(IC Mean) >= 0.02`
- `ICIR >= 0.3`
- `IC>0 % >= 52`
- `adjusted_spread_bps > 0`
- `sample_count >= 1000`
- `monotonicity >= 0.3`

Add CLI option:

```text
--min-monotonicity 0.3
```

## Score

Keep existing `score` and add:

```text
adjusted_score = abs(IC Mean) * 100 + ICIR + adjusted_spread_bps / 10 + monotonicity
```

Sort reports by `passed` then `adjusted_score`.

## Tests

Cover:

- negative IC factors get `direction = -1` and positive adjusted spread when
  raw spread is negative
- monotonicity is loaded from quantile returns and direction-adjusted
- pass rules use adjusted spread and monotonicity
- CLI accepts `--min-monotonicity`
