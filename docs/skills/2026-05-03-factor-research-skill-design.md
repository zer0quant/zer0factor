# 因子研究技能设计文档

**日期：** 2026-05-03
**主题：** 独立因子研究工作流技能（PDF → 因子提取 → 可行性筛查 → 代码生成，含人工检查点）

---

## 背景与动机

`rdagent fin_factor_report` 是全自动化的因子研究流程，但存在以下问题：

1. **数据依赖失败无法自愈** — 因子代码依赖不存在的数据文件（如 `st_status.h5`），迭代6轮仍失败，浪费约20分钟算力
2. **中断恢复机制脆弱** — `loop_n` 被减到0后无法通过 `--path` 恢复，需要手动修改 pickle
3. **全程无人工介入** — 提取了48个因子，但没有筛选机会，低质量因子全部进入编码流程
4. **结果可信度低** — PASS 只代表代码跑通，不代表逻辑正确

本技能复用 rdagent 的实际 prompt，构建**文件驱动、含人工检查点**的独立因子研究工作流，不依赖 Qlib 回测引擎。

---

## 整体架构

### 流程图

```
PDF 文件
    ↓
[Step 1: 提取]  ← classify_system_chinese + extract_factors_system + extract_factor_formulation_system
    ↓
factors.json（含 name/description/formulation/variables/keep）
    ↓
[Step 1b: 可行性筛查]  ← factor_viability_system（新增，解决 st_status.h5 问题）
    ↓  自动标注 viable=true/false + reason
    ↓
【检查点1：用户审核因子列表】
    ↓  用户确认后继续（可修改 keep / viable）
approved.json（筛选 keep=true 的因子）
    ↓
[Step 2: 逐因子代码生成]  ← 自定义 scenario + evolving_strategy_factor_implementation_v1_system
    每轮：生成 → ast.parse() → evaluator_code_feedback_v1 → evaluator_final_decision_v1
    最多3轮
    ↓ 失败超3次
【检查点2：用户决策 — 跳过/提供提示/继续重试】
    ↓
code/<factor_name>.py（每个成功因子一个文件）
status.json（断点续跑依据）
```

### 工作目录结构

```
<work_dir>/
├── factors.json        # 提取 + 可行性结果，用户可编辑
├── approved.json       # 确认后因子列表（自动生成）
├── status.json         # 流程状态（断点续跑依据）
└── code/
    ├── Ret20_0.py
    ├── MOM60.py
    └── ...
```

---

## Step 1：提取阶段（复用 rdagent 实际 prompt）

### 触发

用户提供：
- `work_dir`：工作目录路径
- PDF 文件路径（单个或目录下所有 PDF）
- `available_data`：当前可用数据（如 `["close", "open", "high", "low", "volume", "vwap"]`）

### Prompt 1.1：研报分类

来源：`scenarios/qlib/factor_experiment_loader/prompts.yaml` → `classify_system_chinese`

```
你是一个研报分类助手。用户会输入一篇金融研报。请按照要求回答：
因子指能够解释资产收益率或价格等的变量；而模型则指机器学习或深度学习模型，利用因子等变量来预测价格或收益率变化。

请你对研报进行分类，考虑两个条件：
    1. 是金工量化领域中选股（需与择时，选基等严格区分开）方面的研报;
    2. 涉及了因子或模型的构成，或者是测试了它们的表现。
如果研报同时满足上述两个条件，请输出1；若没有，请输出0。

请使用json进行回答。json key为：class
```

**用途：** 判断 PDF 是否为量化选股研报，不是则跳过

### Prompt 1.2：因子提取（多轮）

来源：`extract_factors_system` + `extract_factors_follow_user`

**第一轮 system prompt：**
```
用户会提供一篇金融工程研报，其中包括了量化因子和模型研究，请按照要求抽取以下信息:
1. 概述这篇研报的主要研究思路;
2. 抽取出所有的因子，并概述因子的计算过程，请注意有些因子可能存在于表格中，请不要遗漏，
   因子的名称请使用英文，不能包含空格，可用下划线连接，研报中可能不含有因子，若没有请返回空字典;
3. 抽取研报里面的所有模型，并概述模型的计算过程，研报中可能不含有模型，若没有请返回空字典;

Respond with your analysis in JSON format:
{
    "summary": "The summary of this report",
    "factors": { "Name": "Description", ... },
    "models": { "Name": "Description", ... }
}
```

**后续轮次 user prompt（继续提取未发现的因子）：**
```
Please continue extracting the factors. Please ignore factors appeared in former messages.
If no factor is found, please return an empty dict.
Notice: You should not miss any factor in the report! Some factors might appear several times.
Respond with your analysis in JSON format:
{ "factors": { "Name": "Description", ... } }
```

### Prompt 1.3：公式提取

来源：`extract_factor_formulation_system` + `extract_factor_formulation_user`

**System：**
```
I have a financial engineering research report and a list of factors extracted from it.
Tasks:
1. For each factor, extract its calculation formula in LaTeX format (variable names use underscores).
2. For each formula, provide explanations for variables and functions used (in English).

Available data sources:
1. Stock Trade Data Table: daily open, close, high, low, VWAP prices, volume, turnover.
2. Financial Data Table: balance sheet, income statement, cash flow statement.
3. Stock Fundamental Data Table: total shares, free float shares, industry, market classification.
4. High-Frequency Data: minute-level open, close, high, low, volume, VWAP.

Respond in JSON format:
{
    "factor_name": {
        "formulation": "latex formulation",
        "variables": { "var_name": "description", ... }
    }
}
```

**User：**
```
===========================Report content:=============================
{{ report_content }}
===========================Factor list in dataframe=============================
{{ factor_dict }}
```

---

## Step 1b：可行性筛查（新增，解决数据依赖问题）

### Prompt 1.4：因子可行性检查

来源：`factor_viability_system`（rdagent 内置，本技能首次在检查点前使用）

```
User has designed several factors in quant investment. Please help the user to check the viability of these factors.
These factors are used to build a daily frequency strategy in China A-share market.

User will provide a table containing:
1. The name of the factor
2. The simple description of the factor
3. The formulation in latex format
4. The description to the variables and functions

User has the following source data:
{{ available_data_description }}

A viable factor should satisfy:
1. The factor can be calculated at daily frequency
2. The factor can be calculated based on each stock
3. The factor can be calculated based ONLY on the source data provided

Please return true for viable factors and false for non-viable factors.
Respond in JSON format:
{
    "factor_name": {
        "viability": true/false,
        "reason": "reason for viability decision"
    }
}
```

**用途：** 提前识别需要不可用数据的因子（如 `st_status.h5`），在编码前标注 `viable: false`，避免浪费算力

**输出写入 `factors.json` 的 `viable` 和 `viable_reason` 字段**

### factors.json 格式（完整版）

```json
[
  {
    "name": "Ret20_0",
    "description": "过去20日收益率动量因子",
    "formulation": "\\frac{P_t - P_{t-20}}{P_{t-20}}",
    "variables": { "P_t": "当日收盘价", "P_{t-20}": "20日前收盘价" },
    "data_required": ["close"],
    "source_pdf": "国信证券_动量类因子.pdf",
    "viable": true,
    "viable_reason": "Only requires close price, which is available.",
    "keep": true
  },
  {
    "name": "ST_Filter_Mom",
    "description": "剔除ST股的动量因子",
    "formulation": "...",
    "variables": { "is_st": "ST股票标识" },
    "data_required": ["close", "st_status"],
    "source_pdf": "国信证券_动量类因子.pdf",
    "viable": false,
    "viable_reason": "Requires st_status data which is not available in current data environment.",
    "keep": true
  }
]
```

**用户审核时可操作的字段：**
- `keep: false` — 跳过此因子
- `viable` — 可手动覆盖系统判断

---

## 检查点1：用户审核因子列表

Claude 展示摘要后暂停，包含可行性分析结果：

```
已从 [文件名] 提取到 48 个因子，完成可行性分析，保存到 factors.json。

可行性摘要：
  ✓ 42个因子可实现（仅需 close/open/high/low/volume 等可用数据）
  ✗  6个因子不可实现（依赖不可用数据，详见 viable_reason 字段）

不可实现的因子：
  ST_Filter_Mom   — 需要 st_status（ST股票标识）
  ...

请打开 factors.json 审核：
- 将不需要的因子改为 "keep": false
- 不可实现的因子已标记 viable=false，建议一并改为 keep=false
- 审核完成后告诉我"继续"
```

---

## Step 2：代码生成阶段

### 自定义 Scenario（替换 Qlib 特定部分）

rdagent 的 `{{ scenario }}` 变量在本技能中替换为：

```
You are implementing quantitative investment factors for China A-share market.

Background:
A factor is a characteristic variable used in quant investment to explain asset returns.
Each factor value represents a numeric value per stock per day.

Available data (passed as pandas DataFrame arguments):
{{ available_data_description }}
(e.g., close: daily close price DataFrame, index=date, columns=stock_code)

Code interface requirement:
- Write a function named `calculate` 
- Function parameters are named after required data (e.g., def calculate(close, volume))
- Each parameter is a pd.DataFrame with index=date, columns=stock_code
- Return a pd.Series with index=stock_code (latest period factor values)
- Do NOT use try-except blocks

Example:
def calculate(close: pd.DataFrame) -> pd.Series:
    return close.pct_change(20).iloc[-1]

Important:
- Use only the data sources listed above
- Avoid time leakage (do not use future data)
- Each transformation step should be commented with data format
```

### Prompt 2.1：代码生成

来源：`evolving_strategy_factor_implementation_v1_system`（适配自定义 scenario）

```
User is trying to implement some factors in the following scenario:
{{ scenario }}
Your code is expected to align the scenario — get the exact factor values as expected.

To help you write correct code, the user might provide:
1. Correct code for similar factors (learn from these)
2. Failed former code and corresponding feedback (analyze and correct)
3. Suggestions based on similar failures

You must write code based on your former latest attempt — read it carefully
and must NOT modify the correct parts.

Respond in JSON format:
{ "code": "The Python code as a string." }
```

**User prompt 变量：**
```
----- Target factor information -----
Name: {{ factor_name }}
Description: {{ factor_description }}
Formulation: {{ factor_formulation }}
Variables: {{ factor_variables }}

{% if former_attempts %}
----- Your former latest attempt -----
Code: {{ former_attempts[-1].code }}
Feedback: {{ former_attempts[-1].feedback }}
{% endif %}
```

### Prompt 2.2：代码审查（每轮执行）

来源：`evaluator_code_feedback_v1_system` + `evaluator_code_feedback_v1_user`

**System：**
```
User is trying to implement some factors in the following scenario:
{{ scenario }}

Your job is to check whether user's code aligns with the factor and the scenario.
User will provide source code and execution feedback (if execution failed).

Your critics are sent to the coding agent to correct the code — do NOT ask user to check anything.
Do NOT include any code in your suggestions, just clear and short suggestions.
Point out only critical issues, ignore minor ones.

Format:
critic 1: message
critic 2: message
```

**User：**
```
----- Factor information -----
{{ factor_information }}
----- Python code -----
{{ code }}
----- Execution feedback -----
{{ execution_feedback }}
```

### Prompt 2.3：最终判定

来源：`evaluator_final_decision_v1_system` + `evaluator_final_decision_v1_user`

**System：**
```
User is trying to implement some factors in the following scenario:
{{ scenario }}

Analyze all feedback and give a final decision.

Decision logic (no ground truth available):
1. Code executes successfully AND aligns with factor description → correct
2. Execution failed for any reason (including actively raised exceptions) → FAIL
3. Code feedback must align with scenario and factor description

Respond in JSON format:
{
    "final_decision": true/false,
    "final_feedback": "message"
}
```

**User：**
```
----- Factor information -----
{{ factor_information }}
----- Execution feedback -----
{{ execution_feedback }}
----- Code feedback -----
{{ code_feedback }}
```

### 迭代流程

每个因子最多3轮：

```
Round N:
  1. 调用 Prompt 2.1 生成/修改代码
  2. ast.parse() 语法检查（本地，零成本）
  3. 调用 Prompt 2.2 代码审查（execution_feedback 填入语法检查结果或"syntax OK"）
  4. 调用 Prompt 2.3 最终判定
  5. final_decision=true → 保存到 code/<name>.py，标记 done
     final_decision=false → 进入下一轮
```

### 检查点2：失败熔断

```
⚠️  因子 [ST_Filter_Mom] 连续失败3次
最后一次失败原因：代码依赖 st_status 数据，当前数据环境不可用

请选择：
1. 跳过这个因子
2. 提供修复提示（例如：去掉ST过滤，直接计算动量）
3. 再给3次机会自动重试
```

### status.json 格式

```json
{
  "Ret20_0":    {"status": "done",    "file": "code/Ret20_0.py", "attempts": 1},
  "MOM60":      {"status": "done",    "file": "code/MOM60.py",   "attempts": 2},
  "ST_Filter":  {"status": "skipped", "reason": "user_skip"},
  "RankMom120": {"status": "pending", "attempts": 0}
}
```

**断点续跑：** 重新触发时读取 `status.json`，跳过 `done` 和 `skipped`，从 `pending` 和 `failed` 继续。

---

## Prompt 完整映射表

| 步骤 | Prompt 来源 | 作用 |
|------|------------|------|
| 1.1 分类 | `classify_system_chinese` | 判断是否为量化选股研报 |
| 1.2 提取（第1轮） | `extract_factors_system` | 提取因子名称和描述 |
| 1.2 提取（后续轮） | `extract_factors_follow_user` | 继续提取未发现的因子 |
| 1.3 公式 | `extract_factor_formulation_system/user` | 提取 LaTeX 公式和变量说明 |
| 1b 可行性 | `factor_viability_system` | 检查因子是否可用现有数据实现 |
| 2.1 代码生成 | `evolving_strategy_factor_implementation_v1_system`（适配） | 生成/修复因子代码 |
| 2.2 代码审查 | `evaluator_code_feedback_v1_system/user` | 审查代码逻辑和数据依赖 |
| 2.3 最终判定 | `evaluator_final_decision_v1_system/user` | 决定是否通过 |

所有 prompt 原文来自 rdagent 安装包，路径：
- `scenarios/qlib/factor_experiment_loader/prompts.yaml`
- `components/coder/factor_coder/prompts.yaml`

---

## 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 是否接 Qlib 回测 | 否 | 降低依赖，先验证代码质量 |
| Prompt 来源 | 复用 rdagent 实际 prompt | 避免重复造轮子，prompt 已经过验证 |
| 执行测试方式 | ast.parse + LLM 代码审查 | 无需任何运行环境 |
| 可行性检查时机 | 编码前（检查点1之前） | 提前拦截注定失败的因子，节省算力 |
| 失败阈值 | 3次 | 平衡自动化程度与资源浪费 |
| 代码接口 | 统一 `calculate()` | 方便后续接入任意回测引擎 |
| 状态持久化 | `status.json` | 支持断点续跑，解决 rdagent 最大痛点 |

---

## 超出范围（本版本不包含）

- Qlib 回测集成
- 因子有效性验证（IC、IR 等指标）
- 因子去重（rdagent 有 `factor_duplicate_system`，可在后续版本加入）
- 多因子组合优化
- Web UI 界面
- 并行代码生成（当前串行）
