# QuantaAlpha Prompt Map

Use the archived prompts under:

```text
docs/quantaalpha-prompts/source/
```

Do not copy Qlib execution assumptions into generated code. Use these prompts
for reasoning structure, quality gates, and review language.

| Stage | Prompt Source | Use |
|---|---|---|
| classify report | `quantaalpha/factors/loader/prompts.yaml` | `classify_system_chinese`, `classify_system` |
| extract candidates | `quantaalpha/factors/loader/prompts.yaml` | `extract_factors_system`, `extract_factors_follow_user` |
| candidate duplicate | `quantaalpha/factors/loader/prompts.yaml` | `factor_duplicate_system` |
| relevance | `quantaalpha/factors/loader/prompts.yaml` | `factor_relevance_system` |
| formula extraction | `quantaalpha/factors/loader/prompts.yaml` | `extract_factor_formulation_system/user` |
| hypothesis | `quantaalpha/factors/prompts/prompts.yaml` | `potential_direction_transformation`, `hypothesis_gen` |
| spec planning | `quantaalpha/factors/prompts/prompts.yaml` | `hypothesis2experiment`, wrapped with zer0factor constraints |
| consistency | `quantaalpha/factors/regulator/consistency_prompts.yaml` | consistency check and expression correction |
| logic duplicate | `quantaalpha/factors/prompts/prompts.yaml` | `expression_duplication` |
| code generation | `quantaalpha/factors/coder/prompts.yaml` | implementation prompt, wrapped with zer0factor code rules |
| code feedback | `quantaalpha/factors/coder/qa_prompts.yaml` | evaluator feedback and final decision |
| feedback summary | `quantaalpha/factors/prompts/prompts.yaml` | `factor_feedback_generation` |

## zer0factor Wrapper For Spec Generation

```text
Generate a zer0factor-standard factor, not a Qlib expression.

The factor must be implemented against FactorFrame:
- data.open
- data.high
- data.low
- data.close
- data.volume
- data.amount
- data.return_

Do not use Qlib variables such as $close or Qlib functions such as TS_MEAN in
executable code. logic_expression is metadata only.

Declare spec.name, spec.inputs, spec.min_window, spec.recommended_window,
spec.frequency, spec.adjust, output_schema, implementation_plan, and
window_reason.
```

## zer0factor Wrapper For Code Generation

```text
Generate Python code for zer0factor, not Qlib.

Rules:
- Define a FactorSpec.
- Define a Factor subclass with compute(self, data: FactorFrame), or a
  compute(data: FactorFrame) function with an attached spec.
- Do not read files, parquet, DuckDB, or call zer0share APIs inside the factor.
- Access data only through FactorFrame fields declared in spec.inputs.
- Return trade_date, ts_code, value.
- Do not use future data or negative shifts.
- Use pandas vectorized operations.
- Keep the code deterministic and side-effect free.
```

