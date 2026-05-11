# Workflow Schema

## Work Directory

```text
<work_dir>/
├── inputs/reports/
├── factors.json
├── approved.json
├── status.json
├── prompt_trace.jsonl
├── code/
├── specs/
├── results/
└── feedback/
```

## factors.json Item

```json
{
  "name": "Volume_Adjusted_Momentum_20D",
  "description": "A 20-day momentum factor adjusted by recent volume expansion.",
  "source_pdf": "example_report.pdf",
  "source_pages": [12, 13],
  "investment_logic": "Momentum is more reliable when supported by participation.",
  "hypothesis": "Stocks with stronger 20-day returns and rising volume will outperform.",
  "expected_relation": "higher_factor_predicts_higher_return",
  "horizon": "short",
  "formulation": "Rank(R_20 * Rank(V_5 / V_20))",
  "variables": {
    "R_20": "20-day close return",
    "V_5": "5-day average volume",
    "V_20": "20-day average volume"
  },
  "logic_expression": "ret20 * rank_cs(volume_ma5 / volume_ma20)",
  "spec": {
    "name": "volume_adjusted_momentum_20d",
    "inputs": ["close", "volume"],
    "min_window": 20,
    "recommended_window": 60,
    "frequency": "1d",
    "adjust": "hfq",
    "output_schema": ["trade_date", "ts_code", "value"]
  },
  "implementation_plan": [
    "Compute 20-day close return.",
    "Compute 5-day and 20-day average volume ratio.",
    "Cross-sectionally rank the volume ratio by date.",
    "Multiply momentum by ranked volume expansion."
  ],
  "window_reason": "The longest dependency is 20 trading days.",
  "relevant": true,
  "viable": true,
  "consistency_ok": true,
  "data_contract_ok": true,
  "window_contract_ok": true,
  "complexity_ok": true,
  "keep": true
}
```

## approved.json

`approved.json` is an array copied from `factors.json` after user review. Only
include factors selected for code generation. Preserve manual edits exactly.

## status.json

```json
{
  "step": "initialized",
  "config": {
    "target_factor_count": null,
    "selection_mode": "all",
    "max_extract_rounds": 3,
    "max_code_attempts": 3
  },
  "factors": {}
}
```

## prompt_trace.jsonl

Each line should summarize an LLM interaction without storing secrets:

```json
{"step": "extract", "prompt": "extract_factors_system", "input": "report.pdf", "output_count": 5}
```

