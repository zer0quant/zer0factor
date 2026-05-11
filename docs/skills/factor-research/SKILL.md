---
name: factor-research
description: Use when extracting, reviewing, implementing, or validating stock factors from quant research reports, formulas, or natural-language investment ideas for zer0factor.
---

# Factor Research

## Overview

Use this skill to turn a PDF/text report or research direction into reviewable,
standard zer0factor factors. The workflow is file-driven: every intermediate
artifact must be written to disk so the user can inspect, edit, and resume.

The implementation target is always zer0factor native code:
`FactorSpec + FactorFrame + compute()`. Do not generate Qlib executable
expressions.

## Quick Start

1. Create or reuse a work directory. If starting fresh, run:

```bash
python docs/skills/factor-research/scripts/init_factor_research_workspace.py <work_dir>
```

2. Collect inputs in `<work_dir>/inputs/reports/` or accept a natural-language
research direction from the user.
3. Produce or update `<work_dir>/factors.json` through the workflow below.
4. Before generating code, validate contracts:

```bash
python docs/skills/factor-research/scripts/validate_factors_json.py <work_dir>/factors.json
```

5. Generate factor code under `<work_dir>/code/`, then run syntax/import/small
fixture checks before archiving.

## Workflow

### Step 0: Initialize

Create:

```text
inputs/reports/
factors.json
approved.json
status.json
prompt_trace.jsonl
code/
specs/
results/
feedback/
```

Record target extraction settings if the user specifies them:
`target_factor_count`, `selection_mode`, and priority rules.

### Step 1: Classify Report

Use QuantaAlpha loader prompts only as source material. Prefer
`classify_system_chinese` for Chinese sell-side quant reports. If a document is
not a stock factor report, mark it skipped unless the user explicitly wants to
continue.

### Step 2: Extract Candidate Factors

Extract candidate factors into `factors.json`. If the user specifies a count,
return at most that many factors and prioritize explicit formulas, report-tested
factors, available data, and diverse logic.

Supported selection modes:

- `all`
- `top_representative`
- `formula_only`
- `backtested_only`
- `user_named`

### Step 3: Deduplicate And Screen

Mark semantic duplicates without deleting them. Then classify each candidate:

- `relevant`: mathematically computable daily per-stock factor
- `viable`: computable from current zer0factor standard fields

### Step 4: Extract Formula And Variables

Add `formulation` and `variables`. Preserve factors with missing formulas, but
mark `formulation_missing: true`.

### Step 5: Generate Investment Hypothesis

For each kept candidate, add:

- `investment_logic`
- `hypothesis`
- `expected_relation`
- `horizon`
- concise knowledge/observation/justification/specification when useful

### Step 6: Generate FactorSpec And Implementation Plan

Generate a zer0factor-standard `spec`, `logic_expression`, and
`implementation_plan`. `logic_expression` is metadata for review and duplicate
checking only.

Read `references/zer0factor-standard.md` before this step.

### Step 7: Apply Quality Gates

Run these checks and write results back to `factors.json`:

- relevance and viability
- hypothesis/formula/logic/spec consistency
- data contract
- window contract
- complexity
- duplicate logic

Run `scripts/validate_factors_json.py` after automated or manual edits.

### Checkpoint 1: User Review

Pause before code generation. Summarize totals and ask the user to review
`factors.json`. Generate `approved.json` from factors where:

```text
keep=true
relevant=true
viable=true
consistency_ok=true
data_contract_ok=true
window_contract_ok=true
```

Do not silently discard user-edited fields.

### Step 8: Generate Code

Generate Python factor code only. Rules:

- define a `FactorSpec`
- implement `compute(self, data: FactorFrame)` or `compute(data: FactorFrame)`
- access data only through fields listed in `spec.inputs`
- do not read parquet, DuckDB, paths, or zer0share APIs inside the factor
- do not use future data or negative shifts
- use vectorized pandas
- return `trade_date, ts_code, value` via `to_factor_output`

Read `references/code-template.py` when writing factor code.

### Step 9: Verify Code

For each factor:

1. `ast.parse`
2. import/dry-run
3. small fixture execution
4. contract validation against the `FactorSpec`
5. final decision

After three failed attempts, pause and ask whether to skip, retry, or return to
FactorSpec generation.

### Step 10: Archive Feedback

Write implementation results to `results/factor_library.json` and summarize
lessons in `feedback/round_feedback.md`. If backtest results exist, include
whether the hypothesis was supported.

## References

- `references/zer0factor-standard.md`: factor interface and data contract
- `references/workflow-schema.md`: expected JSON artifacts
- `references/prompt-map.md`: QuantaAlpha prompt sources and when to use them
- `references/code-template.py`: canonical generated factor shape

