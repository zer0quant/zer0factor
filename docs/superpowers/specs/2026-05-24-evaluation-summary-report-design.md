# Evaluation Summary Report Design

## Purpose

Add a lightweight interpretation layer for completed factor evaluation runs.
The feature reads an existing `summary.csv` and writes a ranked CSV plus a
Markdown report that helps decide which factors deserve more research.

## Scope

Version 1 reads a completed evaluation run. It does not recompute factors,
forward returns, IC, or figures.

Inputs:

- Default run directory: latest child directory under `data/evaluations`.
- Optional explicit run directory: `--run-dir data/evaluations/<run_id>`.
- Required input file: `summary.csv`.

Outputs in the run directory:

- `ranked_summary.csv`
- `report.md`

The CLI prints a short ranking preview.

## CLI

Add:

```bash
uv run python main.py evaluate-summary
```

Options:

```text
--run-dir
--evaluations-dir data/evaluations
--min-ic 0.02
--min-icir 0.3
--min-win-rate 52
--min-spread-bps 0
--min-sample-count 1000
```

`--run-dir` wins over `--evaluations-dir`. If neither is provided, use the
newest directory in `data/evaluations`.

## Rules

Each `factor_name + period` row receives a boolean `passed` flag.

Default pass thresholds:

- `IC Mean >= 0.02`
- `ICIR >= 0.3`
- `IC>0 % >= 52`
- `long_short_spread_bps > 0`
- `sample_count >= 1000`

Rows with missing required metrics fail.

## Score

Add a simple ranking score:

```text
score = IC Mean * 100 + ICIR + long_short_spread_bps / 10
```

This score is only a sorting aid. It is not an investment recommendation.

## Report

`report.md` contains:

- run path and generation time
- rule thresholds
- top ranked rows
- passed rows
- rejected rows
- PNG figure paths grouped by factor when available

Use Markdown tables so the report is readable in a terminal, editor, or GitHub.

## Module Boundary

Add:

```text
zer0factor/eval/report.py
tests/test_eval_report.py
```

`report.py` owns ranking, rule application, latest-run discovery, file writing,
and report rendering. `main.py` only parses CLI options and calls the public
API.

## Errors

Raise clear `ValueError` or `FileNotFoundError` for:

- no run directories under the evaluations directory
- missing `summary.csv`
- missing required summary columns

## Tests

Cover:

- rule evaluation and score sorting
- latest run directory selection
- writing `ranked_summary.csv` and `report.md`
- CLI registration and smoke output
