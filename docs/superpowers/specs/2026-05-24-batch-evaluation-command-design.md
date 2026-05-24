# Batch Evaluation Command Design

## Purpose

Add a single command that evaluates a list of stored factors from a TOML file
and generates the summary report automatically.

## Command

```text
uv run python main.py evaluate-batch --file config/evaluation_batch.example.toml
```

The command reuses the existing project config passed through `--config` for
storage paths, log path, default dates, and zer0share data location.

## Batch File

The batch TOML has two sections:

- `[evaluation]`: factor names and evaluation options.
- `[report]`: thresholds passed to `evaluate-summary` report generation.

Relative `output_dir` values follow the same behavior as the existing CLI: they
are relative to the current working directory.

Empty `start_date` or `end_date` values are treated as missing. Missing
`start_date` and `end_date` fall back to the main project config.

## Flow

1. Load the batch TOML.
2. Build an `EvaluationConfig`.
3. Run `evaluate_factors`.
4. Generate `report.md` and `ranked_summary.csv` for the new run.
5. Print the run directory, report paths, and a top-row preview.

## Scope

This does not add scheduling, parallel subprocesses, retries, or multiple
independent runs in one config. One batch file maps to one evaluation run.

## Tests

Cover:

- CLI registration.
- TOML values are passed into `EvaluationConfig`.
- Report thresholds are passed into `generate_evaluation_report`.
- The command prints the run and report outputs.
