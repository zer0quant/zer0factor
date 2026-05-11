# QuantaAlpha Prompt Archive

Source project: `localserver:/data/QuantaAlpha_start`

Extracted files are stored under `source/` with their original project-relative paths.

## Files

| File | Lines | Notes |
|---|---:|---|
| `source/quantaalpha/coder/costeer/prompts.yaml` | 9 | CoSTEER component analysis prompt |
| `source/quantaalpha/components/proposal/prompts.yaml` | 48 | Generic hypothesis and experiment proposal prompts |
| `source/quantaalpha/contrib/model/coder/one_shot/prompt.yaml` | 27 | One-shot model code implementation prompts |
| `source/quantaalpha/contrib/model/coder/prompts.yaml` | 167 | Model formulation, coding, evaluator prompts |
| `source/quantaalpha/contrib/model/prompts.yaml` | 481 | Model/factor-style hypothesis, expression, feedback prompts |
| `source/quantaalpha/core/prompts.py` | 19 | Prompt loader utility |
| `source/quantaalpha/factors/coder/prompts.yaml` | 204 | Factor code generation and evaluator prompts |
| `source/quantaalpha/factors/coder/qa_prompts.yaml` | 456 | QuantaAlpha factor expression repair/evaluation prompts and function library |
| `source/quantaalpha/factors/loader/prompts.yaml` | 225 | Report classification, factor extraction, formulation, viability, relevance, duplicate prompts |
| `source/quantaalpha/factors/prompts/__init__.py` | 0 | Package marker |
| `source/quantaalpha/factors/prompts/experiment.yaml` | 238 | Qlib factor/model scenario descriptions |
| `source/quantaalpha/factors/prompts/prompts.yaml` | 481 | Main factor mining prompts: hypothesis, expression, feedback, duplication |
| `source/quantaalpha/factors/prompts/proposal.yaml` | 48 | Generic factor hypothesis and experiment proposal prompts |
| `source/quantaalpha/factors/regulator/consistency_prompts.yaml` | 145 | Hypothesis-description-formula-expression consistency and correction prompts |
| `source/quantaalpha/pipeline/prompts/__init__.py` | 0 | Package marker |
| `source/quantaalpha/pipeline/prompts/evolution_prompts.yaml` | 268 | Mutation, crossover, orthogonality, trajectory summary prompts |
| `source/quantaalpha/pipeline/prompts/planning_prompts.yaml` | 22 | Initial direction expansion prompts |

## Key Prompt Groups

- Planning: `pipeline/prompts/planning_prompts.yaml`
- Evolution: `pipeline/prompts/evolution_prompts.yaml`
- Main factor mining: `factors/prompts/prompts.yaml`
- Scenario descriptions: `factors/prompts/experiment.yaml`
- Report-to-factor extraction: `factors/loader/prompts.yaml`
- Expression/code generation: `factors/coder/prompts.yaml`, `factors/coder/qa_prompts.yaml`
- Consistency checks: `factors/regulator/consistency_prompts.yaml`
- Model experiment prompts: `contrib/model/prompts.yaml`, `contrib/model/coder/prompts.yaml`

## Notable Prompt Keys

- `potential_direction_transformation`
- `hypothesis_and_feedback`
- `hypothesis_output_format`
- `factor_hypothesis_specification`
- `function_lib_description`
- `factor_experiment_output_format`
- `factor_feedback_generation`
- `hypothesis_gen`
- `hypothesis2experiment`
- `expression_duplication`
- `extract_factors_system`
- `extract_factor_formulation_system`
- `factor_viability_system`
- `factor_relevance_system`
- `factor_duplicate_system`
- `evolving_strategy_factor_implementation_v1_system`
- `evolving_strategy_factor_implementation_v2_user`
- `evaluator_code_feedback_v1_system`
- `evaluator_final_decision_v1_system`
- `consistency_check_system`
- `expression_correction_system`
