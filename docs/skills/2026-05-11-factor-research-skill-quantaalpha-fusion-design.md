# 因子研究 Skill 融合设计文档

**日期：** 2026-05-11
**主题：** 以原因子研究 skill 为主流程，融合 QuantaAlpha 全套提示词能力
**目标：** 从研报或研究方向中提取、筛选、规范化、实现和归档可计算因子，保留人工检查点与断点续跑，同时吸收 QuantaAlpha 的假设生成、质量门和反馈能力，但将因子实现规范从 Qlib 表达式改为 zer0factor/zer0share 原生规范。

---

## 设计原则

本设计以现有 `2026-05-03-factor-research-skill-design.md` 为主线，不把 QuantaAlpha 的全自动系统整套搬入。原 skill 的核心价值是：

1. 文件驱动，所有中间结果可审查、可修改、可恢复。
2. 在关键节点加入人工检查点，避免黑盒自动化一路跑偏。
3. 先解决“能不能算、能不能实现”，再考虑回测和进化。

QuantaAlpha 的核心价值是：

1. 将“研究方向/研报内容”先转成可检验投资假设。
2. 将假设转成可审查的中间表达摘要，并约束最终代码遵循标准 `FactorSpec + FactorFrame + compute()` 接口。
3. 使用数据契约、窗口依赖、复杂度、重复度、一致性检查约束因子生成。
4. 使用反馈总结沉淀实现经验。

融合策略：

```text
rdagent skill 控制流程与检查点
QuantaAlpha prompt 提供假设层、质量门与反馈层
zer0factor 规范提供数据契约、窗口契约和代码接口
```

---

## 总体流程

```text
输入：PDF 研报 / 研究方向 / 已有 factors.json
    ↓
Step 0: 初始化工作目录与状态文件
    ↓
Step 1: 研报分类
    ↓
Step 2: 因子候选提取（可人工指定数量）
    ↓
Step 3: 候选去重与相关性筛查
    ↓
Step 4: 公式与变量提取
    ↓
Step 5: 投资逻辑与可检验假设生成
    ↓
Step 6: FactorSpec 与标准因子实现计划生成
    ↓
Step 7: 可行性 / 一致性 / 复杂度 / 重复度质量门
    ↓
Checkpoint 1: 用户审核 factors.json
    ↓
Step 8: 生成标准 Python 因子类/函数
    ↓
Step 9: 语法检查、执行检查、LLM 审查、最终判定
    ↓
Checkpoint 2: 失败熔断，用户选择跳过/提示/重试
    ↓
Step 10: 因子库归档、状态持久化、反馈总结
```

---

## 工作目录结构

```text
<work_dir>/
├── inputs/
│   └── reports/                         # PDF 或文本研报
├── factors.json                         # 主审核文件
├── approved.json                        # 用户审核后生成
├── status.json                          # 断点续跑状态
├── prompt_trace.jsonl                   # 每次 LLM 调用摘要，不保存敏感 key
├── code/
│   ├── <factor_name>.py
│   └── ...
├── specs/
│   ├── factor_spec_registry.json        # FactorSpec、窗口依赖、输入字段记录
│   └── factor_logic_registry.json       # 逻辑摘要/表达摘要去重记录
├── results/
│   ├── execution_feedback.json
│   └── factor_library.json
└── feedback/
    └── round_feedback.md
```

---

## factors.json 数据模型

融合后，`factors.json` 不只保存因子名称和公式，还保存投资逻辑、假设、标准数据依赖、窗口依赖、表达摘要和质量门结果。

```json
[
  {
    "name": "Volume_Adjusted_Momentum_20D",
    "description": "A 20-day momentum factor adjusted by recent trading volume expansion.",
    "source_pdf": "example_report.pdf",
    "source_pages": [12, 13],
    "investment_logic": "Momentum signals are more reliable when supported by abnormal trading participation.",
    "hypothesis": "Stocks with stronger 20-day returns accompanied by rising volume will have higher short-term future returns.",
    "expected_relation": "higher_factor_predicts_higher_return",
    "horizon": "short",
    "formulation": "\\text{Rank}(R_{20} \\times \\text{Rank}(V_5 / V_{20}))",
    "variables": {
      "R_20": "20-day return",
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
    "data_required": ["close", "volume"],
    "relevant": true,
    "relevance_reason": "Daily per-stock mathematical factor.",
    "viable": true,
    "viable_reason": "Uses only close and volume.",
    "consistency_ok": true,
    "complexity_ok": true,
    "duplicate_group": null,
    "logic_duplicate": false,
    "keep": true,
    "notes": ""
  }
]
```

---

## zer0factor 标准因子规范

QuantaAlpha 的原始因子生成遵循 Qlib 表达式规范，例如 `$close`、`TS_MEAN()`、`RANK()`。本 skill 不直接沿用该规范，因为 zer0factor 的实际数据来自 zer0share，本地字段、复权方式、日期格式和存储方式都不同。

本 skill 采用：

```text
FactorSpec + FactorFrame + Python compute()
```

并把表达式降级为审查用的 `logic_expression` 元数据，不作为默认执行语言。

### 数据源与因子逻辑解耦

因子代码不能直接读取 parquet、DuckDB，也不能直接调用 `zer0share.pro.daily()`。所有数据访问都通过标准 Provider 完成。

```python
class FactorDataProvider:
    def history(
        self,
        fields: list[str],
        start_date: str,
        end_date: str,
        universe: str = "all",
        adjust: str = "hfq",
    ) -> "FactorFrame":
        ...
```

`Zer0ShareDataProvider` 负责把 zer0share 字段映射到标准字段：

| zer0share 字段 | 标准字段 |
|---|---|
| `ts_code` | `ts_code` |
| `trade_date` | `trade_date` |
| `open` | `open` |
| `high` | `high` |
| `low` | `low` |
| `close` | `close` |
| `vol` | `volume` |
| `amount` | `amount` |
| `pct_chg` 或计算值 | `return_` |
| `adj_factor` | 由 provider 用于复权处理，不直接暴露给普通因子 |

这样如果未来数据源改变，只需要替换 Provider，不需要修改因子逻辑。

### FactorFrame

AI 生成的因子逻辑只允许访问 `FactorFrame` 的标准字段。默认内部计算形态为 wide panel：

```text
index: trade_date
columns: ts_code
values: field value
```

示例：

```python
data.close      # pd.DataFrame[trade_date x ts_code]
data.volume     # pd.DataFrame[trade_date x ts_code]
data.amount     # pd.DataFrame[trade_date x ts_code]
data.return_    # pd.DataFrame[trade_date x ts_code]
```

因子输出必须统一回 long format，以适配当前 `FactorStorage.write()`：

```text
trade_date, ts_code, value
```

### FactorSpec

每个因子必须声明规范元数据：

```python
FactorSpec(
    name="volume_adjusted_momentum_20d",
    inputs=["close", "volume"],
    min_window=20,
    recommended_window=60,
    frequency="1d",
    adjust="hfq",
    output_schema=["trade_date", "ts_code", "value"],
)
```

字段含义：

| 字段 | 说明 |
|---|---|
| `name` | 稳定、唯一、snake_case 因子名 |
| `inputs` | 因子最小输入字段，不包含未使用字段 |
| `min_window` | 计算该因子理论上至少需要的历史交易日数量 |
| `recommended_window` | 推荐预热窗口，通常大于等于 `min_window` |
| `frequency` | 默认 `1d` |
| `adjust` | 默认 `hfq`，也可以是 `none` 或 `qfq` |
| `output_schema` | 必须是 `trade_date, ts_code, value` |

### 标准因子代码接口

默认生成 Python 类：

```python
class VolumeAdjustedMomentum20D(Factor):
    spec = FactorSpec(
        name="volume_adjusted_momentum_20d",
        inputs=["close", "volume"],
        min_window=20,
        recommended_window=60,
        frequency="1d",
        adjust="hfq",
        output_schema=["trade_date", "ts_code", "value"],
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        ret20 = data.close / data.close.shift(20) - 1
        vol_ratio = data.volume.rolling(5).mean() / (
            data.volume.rolling(20).mean() + 1e-8
        )
        value = ret20 * vol_ratio.rank(axis=1, pct=True)
        return to_factor_output(value, self.spec.name)
```

如项目尚未实现 `Factor` 基类，也允许第一阶段生成等价函数，但必须携带 `spec`：

```python
spec = FactorSpec(...)

def compute(data: FactorFrame) -> pd.DataFrame:
    ...
```

---

## Prompt 来源总览

本设计使用 QuantaAlpha prompt archive：

`docs/quantaalpha-prompts/source/`

主流程只纳入 factor 研究相关 prompt，并用 zer0factor 标准因子规范包裹 QuantaAlpha 的生成约束。

| 分层 | QuantaAlpha 文件 | 用途 |
|---|---|---|
| 研报加载 | `quantaalpha/factors/loader/prompts.yaml` | 分类、提取、公式、相关性、可行性、候选去重 |
| 假设与规范化 | `quantaalpha/factors/prompts/prompts.yaml` | 研究方向转假设、假设转因子实现计划；借鉴表达式约束思想但替换为 zer0factor 规范 |
| 场景描述 | `quantaalpha/factors/prompts/experiment.yaml` | 仅作场景写法参考，不沿用 Qlib 数据接口 |
| 通用提案 | `quantaalpha/components/proposal/prompts.yaml` | 通用 hypothesis / experiment 生成框架 |
| 代码与执行修复 | `quantaalpha/factors/coder/prompts.yaml` | 标准 Python 因子代码生成、执行反馈、最终判定 |
| QA 代码修复 | `quantaalpha/factors/coder/qa_prompts.yaml` | 代码审查、最终判定、修复提示；不沿用 Qlib 表达式执行模板 |
| 一致性检查 | `quantaalpha/factors/regulator/consistency_prompts.yaml` | hypothesis-description-formulation-logic/code 一致性与修正 |
| 知识组件路由 | `quantaalpha/coder/costeer/prompts.yaml` | 任务匹配历史组件经验 |

---

## Step 0：初始化

输入可以是三类之一：

1. `reports/` 下的 PDF 或文本研报。
2. 用户给出的自然语言研究方向，例如“价量背离的短期反转因子”。
3. 已有 `factors.json`，用于继续审核、FactorSpec 生成或代码实现。

初始化创建：

```text
factors.json
status.json
prompt_trace.jsonl
code/
specs/
results/
```

状态文件示例：

```json
{
  "step": "extract_factors",
  "factors": {
    "Volume_Adjusted_Momentum_20D": {
      "status": "pending_spec",
      "attempts": 0
    }
  }
}
```

---

## Step 1：研报分类

Prompt：

- `classify_system_chinese`
- `classify_system`

来源：

`quantaalpha/factors/loader/prompts.yaml`

用途：

判断输入文档是否为量化选股研报。默认优先使用 `classify_system_chinese`，因为当前场景主要是中文金工研报。

输出：

```json
{ "class": 1 }
```

处理策略：

- `class = 1`：进入提取阶段。
- `class = 0`：记录为 skipped，并提示用户该文档不是默认目标类型。
- 用户可以手动强制继续。

---

## Step 2：因子候选提取（可人工指定数量）

Prompt：

- `extract_factors_system`
- `extract_factors_follow_user`

来源：

`quantaalpha/factors/loader/prompts.yaml`

用途：

从研报中提取：

1. 报告主研究思路。
2. 所有因子名称与计算过程摘要。
3. 所有模型名称与计算过程摘要。

### 人工介入与数量控制

Step 2 允许用户在提取前或提取中指定目标数量，避免一次性抽取过多候选导致 token、审核和后续实现成本失控。

用户可指定：

```json
{
  "target_factor_count": 10,
  "selection_mode": "top_representative",
  "priority": ["explicit_formula", "backtested_in_report", "data_available", "diverse_logic"]
}
```

支持的 `selection_mode`：

| 模式 | 行为 |
|---|---|
| `all` | 尽可能提取全部因子，适合完整复现研报 |
| `top_representative` | 提取最有代表性的 N 个因子，默认推荐 |
| `formula_only` | 只提取有明确公式/表格定义的因子 |
| `backtested_only` | 只提取研报中有测试结果的因子 |
| `user_named` | 只提取用户指定名称或主题相关的因子 |

如果用户没有指定数量，默认：

```json
{
  "target_factor_count": null,
  "selection_mode": "all"
}
```

如果用户指定了数量，提取 prompt 需要在 `extract_factors_system` 外层增加约束：

```text
The user only wants up to {{ target_factor_count }} factors.
Prioritize factors that are explicitly defined, formula-backed, representative, and diverse.
If the report contains more factors, do not list all of them; return the best {{ target_factor_count }} candidates.
```

如果研报本身因子数少于目标数量，则返回全部。

多轮策略：

```text
第 1 轮：extract_factors_system
第 2-N 轮：extract_factors_follow_user
停止条件：
  - 连续一轮返回空 factors
  - 或已达到 target_factor_count
  - 或达到 max_extract_rounds
  - 或 token budget 不足
```

多轮提取时，如果已指定 `target_factor_count`，每轮都需要带上剩余数量：

```text
Already extracted: {{ extracted_factor_count }}
Remaining quota: {{ remaining_factor_count }}
Do not exceed the remaining quota.
```

写入 `factors.json` 初始字段：

```json
{
  "name": "...",
  "description": "...",
  "source_pdf": "...",
  "keep": true
}
```

如果使用数量限制，需要额外写入：

```json
{
  "selection_reason": "Selected because it has an explicit formula and represents the report's momentum family.",
  "extraction_rank": 1
}
```

---

## Step 3：候选去重与相关性筛查

Prompt：

- `factor_duplicate_system`
- `factor_relevance_system`

来源：

`quantaalpha/factors/loader/prompts.yaml`

### 3.1 候选去重

`factor_duplicate_system` 用于识别研报提取阶段产生的重复因子。

重复标准：

1. 名称、描述、公式可能不同，但本质是同一因子。
2. 如果 horizon 不同，例如 5 日和 20 日，则不合并。
3. 只有高度确定才归为重复组。

输出写入：

```json
{
  "duplicate_group": "group_001",
  "canonical_name": "Momentum_20D"
}
```

默认不自动删除重复因子，只在 Checkpoint 1 让用户决定。

### 3.2 相关性筛查

`factor_relevance_system` 判断候选是否是真正可计算的量化投资因子。

它和可行性不同：

- `relevant`：这个东西是不是数学可计算的日频逐股票因子。
- `viable`：这个东西是否能用当前可用数据算出来。

写入：

```json
{
  "relevant": true,
  "relevance_reason": "Daily per-stock mathematical factor."
}
```

---

## Step 4：公式与变量提取

Prompt：

- `extract_factor_formulation_system`
- `extract_factor_formulation_user`

来源：

`quantaalpha/factors/loader/prompts.yaml`

用途：

为每个因子提取：

1. LaTeX 公式。
2. 变量和函数解释。
3. 与输入因子名一致的 key。

写入：

```json
{
  "formulation": "...",
  "variables": {
    "var_name": "description"
  }
}
```

注意：

- LaTeX 反斜杠必须正确 JSON 转义。
- 如果因子数量过多，允许分批处理。
- 保留未能解析公式的因子，但标记 `formulation_missing: true`。

---

## Step 5：投资逻辑与可检验假设

Prompt：

- `potential_direction_transformation`
- `hypothesis_gen`
- `hypothesis_output_format`
- `factor_hypothesis_specification`
- 通用备用：`components/proposal/prompts.yaml` 的 `hypothesis_gen`

来源：

`quantaalpha/factors/prompts/prompts.yaml`

用途：

把研报因子描述或用户研究方向转成结构化投资假设。

对于研报因子，输入包含：

```text
factor name
factor description
report summary
formulation
variables
source excerpts if available
```

对于用户自然语言方向，先使用：

```text
potential_direction_transformation
```

输出扩展为：

```json
{
  "investment_logic": "The economic or behavioral mechanism behind the factor.",
  "hypothesis": "A single testable hypothesis.",
  "concise_knowledge": "...",
  "concise_observation": "...",
  "concise_justification": "...",
  "concise_specification": "...",
  "expected_relation": "higher_factor_predicts_higher_return",
  "horizon": "short"
}
```

本 skill 对 QuantaAlpha 原输出做两个增强：

1. 增加 `investment_logic`，方便人工理解。
2. 增加 `expected_relation` 和 `horizon`，方便后续回测解释。

---

## Step 6：生成 FactorSpec 与标准实现计划

Prompt：

- `hypothesis2experiment`
- `factor_experiment_output_format`
- `function_lib_description`（只借鉴约束思路，不直接沿用 Qlib 函数名）

来源：

`quantaalpha/factors/prompts/prompts.yaml`

用途：

把投资假设转换为 zer0factor 标准因子规范，包括 `FactorSpec`、`logic_expression` 和实现计划。

默认不要求 LLM 输出可执行 DSL，而是输出可审查的实现计划：

```json
{
  "factor_name": {
    "description": "...",
    "formulation": "...",
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
      "Cross-sectionally rank volume ratio by date.",
      "Multiply momentum by ranked volume expansion."
    ],
    "window_reason": "20-day return and 20-day average volume require at least 20 observations."
  }
}
```

### 标准化生成约束

在 QuantaAlpha `hypothesis2experiment` prompt 外层增加 zer0factor 约束：

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

Do not use Qlib variables such as $close or Qlib functions such as TS_MEAN in executable code.
You may include a concise logic_expression for human review, but it is metadata only.

You must declare:
- spec.name
- spec.inputs
- spec.min_window
- spec.recommended_window
- spec.frequency
- spec.adjust
- spec.output_schema
- window_reason
```

本 skill 的策略：

1. 对研报已有公式：要求 `logic_expression` 和 `implementation_plan` 尽量忠实复现公式。
2. 对用户研究方向：允许生成 1-3 个 `FactorSpec` 候选。
3. 对输入字段过多、窗口声明不清、逻辑和公式不一致的结果，进入 Step 7 修正。

---

## Step 7：质量门

质量门按顺序执行，所有结果写回 `factors.json`。

### 7.1 可行性检查

Prompt：

- `factor_viability_system`

来源：

`quantaalpha/factors/loader/prompts.yaml`

判断因子是否能用可用数据实现。

输出：

```json
{
  "viable": true,
  "viable_reason": "Uses only close and volume."
}
```

### 7.2 一致性检查

Prompt：

- `consistency_check_system`
- `consistency_check_user`
- `expression_correction_system`
- `expression_correction_user`

来源：

`quantaalpha/factors/regulator/consistency_prompts.yaml`

检查：

```text
hypothesis
description
formulation
logic_expression
implementation_plan
FactorSpec
variables
```

是否表达同一个因子逻辑。

如果不一致，先尝试自动修正 `logic_expression`、`implementation_plan` 或 `spec`。修正后重新检查。

### 7.3 数据契约与窗口检查

这是 zer0factor 新增质量门，用于替代 Qlib 表达式可解析性检查。

检查项：

```text
1. spec.inputs 是否只使用标准字段
2. compute 计划是否只引用 spec.inputs 中的字段
3. min_window 是否覆盖所有 rolling/shift/pct_change/corr 等窗口
4. recommended_window 是否 >= min_window
5. output_schema 是否为 trade_date, ts_code, value
6. 因子逻辑是否直接依赖 zer0share API 或 parquet 路径
```

输出：

```json
{
  "data_contract_ok": true,
  "window_contract_ok": true,
  "min_window": 20,
  "recommended_window": 60,
  "contract_reason": "Uses close and volume only; longest rolling window is 20."
}
```

### 7.4 复杂度检查

Prompt/规则来源：

- `hypothesis2experiment` 中的 complexity constraints
- `factor_regulator.py` 的检查思想

默认阈值：

```json
{
  "symbol_length_threshold": 250,
  "target_symbol_length": "50-150",
  "base_features_threshold": 6,
  "free_args_ratio_threshold": 0.5
}
```

输出：

```json
{
  "complexity_ok": true,
  "logic_length": 42,
  "base_features": ["close", "volume"],
  "complexity_reason": "Simple and interpretable."
}
```

### 7.5 逻辑重复度检查

Prompt：

- `expression_duplication`

来源：

`quantaalpha/factors/prompts/prompts.yaml`

用途：

如果 `logic_expression` 或 `implementation_plan` 和历史因子有重复结构，要求 LLM 用结构不同但经济含义相近的方式改写。

与 Step 3 的候选去重不同：

```text
Step 3: 因子候选语义去重
Step 7.5: 因子逻辑结构去重
```

---

## Checkpoint 1：用户审核

展示摘要：

```text
已完成因子提取与质量门：

总候选：48
相关：44
可行：39
一致性通过：36
复杂度通过：34
重复组：5

建议跳过：
- ST_Filter_Momentum: 依赖 st_status
- News_Sentiment_Reversal: 依赖自然语言新闻情绪，当前数据不可用

请审核 factors.json：
- keep=false 跳过
- 修改 logic_expression / FactorSpec 可手工覆盖
- 修改 viable/relevant 可手工覆盖
审核完成后回复“继续”
```

审核后生成：

```text
approved.json
```

筛选条件：

```text
keep=true
relevant=true
viable=true
consistency_ok=true
data_contract_ok=true
window_contract_ok=true
```

复杂度不通过的因子默认不进入代码生成，除非用户手动保留。

---

## Step 8：生成标准 Python 因子类/函数

默认生成 `FactorSpec + Python compute()`。`logic_expression` 只作为审查和去重用元数据，不作为默认执行语言。

### 默认模式：FactorSpec + Python compute

Prompt：

- `evolving_strategy_factor_implementation_v1_system`
- `evolving_strategy_factor_implementation_v2_user`

来源：

`quantaalpha/factors/coder/prompts.yaml`
`quantaalpha/factors/coder/qa_prompts.yaml`

在 prompt 外层增加 zer0factor 代码接口约束：

```text
Generate Python code for zer0factor, not Qlib.

Rules:
- Define a FactorSpec named `spec`.
- Define either a Factor subclass with compute(self, data: FactorFrame) or a compute(data: FactorFrame) function.
- Do not read files, parquet, DuckDB, or call zer0share APIs inside the factor.
- Access data only through FactorFrame fields declared in spec.inputs.
- Return a DataFrame with columns: trade_date, ts_code, value.
- Do not use future data or negative shifts.
- Use pandas vectorized operations.
- Keep the code deterministic and side-effect free.
- Include no network calls, no randomness, no try/except hiding errors.
```

生成示例：

```python
class VolumeAdjustedMomentum20D(Factor):
    spec = FactorSpec(
        name="volume_adjusted_momentum_20d",
        inputs=["close", "volume"],
        min_window=20,
        recommended_window=60,
        frequency="1d",
        adjust="hfq",
        output_schema=["trade_date", "ts_code", "value"],
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        ret20 = data.close / data.close.shift(20) - 1
        vol_ratio = data.volume.rolling(5).mean() / (
            data.volume.rolling(20).mean() + 1e-8
        )
        value = ret20 * vol_ratio.rank(axis=1, pct=True)
        return to_factor_output(value, self.spec.name)
```

优点：

1. 可以直接适配 zer0share 数据。
2. 数据源和因子逻辑解耦。
3. 每个因子显式声明最小窗口和输入字段。
4. 复杂因子不受 DSL 表达能力限制。
5. 后续仍可从常见代码模式沉淀轻量 DSL。

---

## Step 9：代码审查、执行检查与最终判定

Prompt：

- `evaluator_code_feedback_v1_system`
- `evaluator_code_feedback_v1_user`
- `evaluator_output_format_system`
- `evaluator_final_decision_v1_system`
- `evaluator_final_decision_v1_user`

来源：

`quantaalpha/factors/coder/prompts.yaml`
`quantaalpha/factors/coder/qa_prompts.yaml`

检查顺序：

```text
1. ast.parse()
2. import / dry-run
3. small fixture execution
4. LLM code feedback
5. final decision
```

最终判定：

```json
{
  "final_decision": true,
  "final_feedback": "Code executes and matches factor definition."
}
```

每个因子最多尝试 3 轮。超过阈值进入 Checkpoint 2。

---

## Checkpoint 2：失败熔断

触发条件：

```text
attempts >= 3
或一致性/规范修正连续失败
或代码执行持续无 result
```

用户选项：

```text
1. 跳过该因子
2. 提供修复提示
3. 再给 3 次自动重试
4. 回到 FactorSpec 阶段重写
```

状态写入：

```json
{
  "FactorName": {
    "status": "failed_waiting_user",
    "attempts": 3,
    "last_feedback": "Requires unavailable data st_status."
  }
}
```

---

## Step 10：因子库归档与反馈总结

Prompt：

- `factor_feedback_generation`

来源：

`quantaalpha/factors/prompts/prompts.yaml`

输出：

```json
{
  "factor_id": "...",
  "factor_name": "...",
  "logic_expression": "...",
  "spec": {
    "inputs": ["close", "volume"],
    "min_window": 20,
    "recommended_window": 60
  },
  "factor_implementation_code": "...",
  "factor_description": "...",
  "factor_formulation": "...",
  "metadata": {
    "hypothesis": "...",
    "investment_logic": "...",
    "source_pdf": "...",
    "created_at": "..."
  },
  "quality_gate": {
    "relevant": true,
    "viable": true,
    "consistency_ok": true,
    "data_contract_ok": true,
    "window_contract_ok": true,
    "complexity_ok": true
  },
  "feedback": {}
}
```

如果有回测结果，`factor_feedback_generation` 用于总结：

1. 假设是否被支持。
2. 哪种构造方式有效。
3. 下一轮应如何改进。
4. 是否替换当前最佳结果。

如果没有回测结果，只生成实现反馈总结。

---

## CoSTEER 知识组件 prompt 的用途

Prompt：

- `analyze_component_prompt_v1_system`

来源：

`quantaalpha/coder/costeer/prompts.yaml`

用途：

把当前任务匹配到历史经验组件，例如：

```text
rolling window
cross-sectional ranking
unavailable data
look-ahead bias
pandas index alignment
factor logic too complex
```

本 skill 可选使用它来检索历史失败与修复经验。默认不阻塞主流程。

---

## Prompt 映射表

| 阶段 | 默认 Prompt | 备用/增强 Prompt |
|---|---|---|
| 研报分类 | `classify_system_chinese` | `classify_system` |
| 因子提取 | `extract_factors_system` | `extract_factors_follow_user` |
| 候选去重 | `factor_duplicate_system` | 无 |
| 相关性筛查 | `factor_relevance_system` | 无 |
| 公式提取 | `extract_factor_formulation_system/user` | 无 |
| 假设生成 | `hypothesis_gen` | `components/proposal/hypothesis_gen` |
| 方向转假设 | `potential_direction_transformation` | 无 |
| 规范生成 | `hypothesis2experiment` | `factor_experiment_output_format` 经 zer0factor 外层约束改写 |
| 数据/算子约束 | zer0factor 标准因子规范 | `function_lib_description` 仅作约束思路参考 |
| 可行性筛查 | `factor_viability_system` | 无 |
| 一致性检查 | `consistency_check_system/user` | `expression_correction_system/user` |
| 逻辑重复 | `expression_duplication` | `factor_duplicate_system` 仅用于候选语义重复 |
| 代码生成 | `evolving_strategy_factor_implementation_v1_system` | `evolving_strategy_factor_implementation_v2_user` |
| 代码审查 | `evaluator_code_feedback_v1_system/user` | 无 |
| 最终判定 | `evaluator_final_decision_v1_system/user` | `evaluator_output_format_system` |
| 反馈总结 | `factor_feedback_generation` | 无 |
| 历史经验路由 | `analyze_component_prompt_v1_system` | 无 |

---

## 与旧版 skill 的主要差异

| 旧版 | 融合版 |
|---|---|
| PDF -> 因子 -> 公式 -> 可行性 -> 代码 | PDF/方向 -> 因子 -> 假设 -> FactorSpec -> 质量门 -> 标准 Python 因子 |
| 只检查可行性 | 增加相关性、一致性、数据契约、窗口契约、复杂度、逻辑重复 |
| 直接生成普通 Python 为主 | 默认生成 `FactorSpec + compute(data: FactorFrame)` 标准因子 |
| 因子去重放在后续版本 | 纳入 Step 3 |
| 反馈只来自代码失败 | 可扩展为实现反馈 + 回测反馈 + 轨迹总结 |

---

## 默认执行策略

为避免过度自动化，默认配置如下：

```json
{
  "max_extract_rounds": 3,
  "target_factor_count": null,
  "selection_mode": "all",
  "factors_per_hypothesis": 1,
  "max_spec_candidates": 3,
  "max_code_attempts": 3,
  "enable_consistency_correction": true,
  "enable_logic_duplication_check": true,
  "enable_candidate_duplicate_check": true,
  "default_code_mode": "factor_spec_python"
}
```

---

## 超出当前版本范围

以下能力保留接口，但不作为默认必做项：

1. Qlib 全量回测。
2. 多因子组合优化。
3. Web UI。
4. 自动提交或发布 skill。

---

## 后续落地建议

1. 先实现文档型 skill：按本流程指导 Codex 做研报因子提取与审核。
2. 再实现脚本辅助：JSON 合并、重复组处理、FactorSpec 校验、窗口依赖校验、逻辑复杂度统计。
3. 最后接入执行后端：`Zer0ShareDataProvider -> FactorFrame -> compute() -> FactorStorage.write()`。

推荐第一阶段只做：

```text
loader prompts
hypothesis2experiment
consistency prompts
quality gate
人工审核
```

等这条链路稳定后，再考虑是否接入回测评价。
