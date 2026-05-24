# Factor Registry 设计文档

**日期：** 2026-05-24  
**范围：** 方案 B —— 声明层 + 查询 + 校验，不含 factor-sync

---

## 背景

项目已从"单次运行脚本"进入"因子生产线"阶段。现有能力：

- 单因子评估
- 批量因子评估（手写因子名）
- 自动报告
- 方向调整和单调性筛选

最缺的是稳定的因子元数据管理，避免多处配置不一致、因子名散落在命令行参数里。

---

## 目标

用 `config/factors.toml` 作为全项目因子元数据注册表，驱动评估流程，并提供因子查询和存储校验命令。

**本轮交付：**
- `config/factors.example.toml` + schema
- `FactorRegistry` 类（声明层读取、过滤、校验）
- `evaluate-batch` 支持从 registry 选取因子
- `factor-list` 命令
- `factor-info <name>` 命令
- 注册/存储不一致校验输出

**本轮不做：**
- `factor-sync`（TOML → DuckDB 写入）
- DuckDB 元数据 schema 扩展
- 计算依赖图自动编排
- registry 驱动 compute / neutralize / preprocess 命令

---

## 架构

```
config/factors.toml          ← 人工维护，声明层（提交 git）
        ↓ 读取
FactorRegistry               ← Python 对象，过滤 / 查询 / 校验
    ↙           ↘
evaluate-batch    factor-list / factor-info
                      ↓ 只读对比
                 FactorStorage (DuckDB)  ← 机器状态层，不写
```

TOML 是唯一的人工元数据来源。DuckDB 只作为存储状态的只读参考，本轮不写入任何元数据。架构方向为 C（未来 `factor-sync` 可将 TOML 写入 DuckDB），本轮按 B 方式运行。

---

## TOML Schema

文件路径：`config/factors.toml`（用户从 `config/factors.example.toml` 复制）

```toml
[registry]
version = "1"

[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"          # built_in | stored | derived | neutralized
source_factor = "daily_return"       # 可选，依赖的原始因子（仅元信息，不驱动计算）
enabled = true
tags = ["momentum", "short-term"]
description = "Neutralized daily return factor"

[factors.evaluate]
default = true                       # 是否默认参与批量评估
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✓ | 因子唯一标识，对应 storage key |
| `category` | ✓ | 分类，如 `price`、`volume`、`fundamental` |
| `source_type` | ✓ | `built_in` / `stored` / `derived` / `neutralized` |
| `source_factor` | — | 依赖的原始因子名，仅元信息 |
| `enabled` | ✓ | 是否启用，驱动 `--enabled` 过滤 |
| `tags` | — | 自由标签列表 |
| `description` | — | 人类可读描述 |
| `[factors.evaluate]` | — | 因子级评估覆盖配置，缺省则用全局默认 |
| `evaluate.default` | — | 是否默认参与批量评估 |
| `evaluate.quantiles` | — | 分位数 |
| `evaluate.periods` | — | 评估周期列表 |
| `evaluate.return_type` | — | 收益类型 |

---

## FactorRegistry 类

**文件：** `zer0factor/registry.py`（独立模块，不依赖 eval 层）

### 数据模型

```python
@dataclass
class EvaluateMeta:
    default: bool
    quantiles: int
    periods: list[int]
    return_type: str

@dataclass
class FactorMeta:
    name: str
    category: str
    source_type: str
    source_factor: str | None
    enabled: bool
    tags: list[str]
    description: str
    evaluate: EvaluateMeta | None

@dataclass
class RegistryValidation:
    registered_missing: list[str]   # 注册了但 storage 没有
    orphan_stored: list[str]        # storage 有但没注册
```

### 接口

```python
class FactorRegistry:
    def __init__(self, path: Path): ...

    def all(self) -> list[FactorMeta]
    def get(self, name: str) -> FactorMeta        # 不存在抛 KeyError
    def filter(
        self,
        enabled: bool | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        evaluate_default: bool | None = None,
    ) -> list[FactorMeta]

    def validate(self, storage: FactorStorage) -> RegistryValidation
```

---

## evaluate-batch 集成

`settings.toml` 新增可选配置块：

```toml
[evaluation]
factor_source = "registry"           # "registry" | "explicit"（默认，行为不变）
registry_path = "config/factors.toml"
categories = ["price"]               # 可选，按 category 过滤
enabled_only = true                  # 可选，默认 true
```

- `factor_source = "explicit"`（或不配置）：行为与现在完全一致，`--factors` 参数照常工作
- `factor_source = "registry"`：从 registry 取因子名列表，替代手写 `--factors`
- 两种模式共存，互不干扰

---

## CLI 命令

### factor-list

```
uv run python main.py factor-list [--category CATEGORY] [--enabled] [--registered] [--orphan]
```

默认显示所有注册因子，附带存储状态：

```
NAME                    CATEGORY   TYPE          ENABLED   IN_STORAGE   ROWS        START       END
z_neu_daily_return      price      neutralized   ✓         ✓            1,240,000   2020-01-02  2024-12-31
z_neu_open_return       price      neutralized   ✓         ✗            —           —           —
daily_return            price      built_in      ✓         ✓            1,240,000   2020-01-02  2024-12-31
```

末尾自动附加校验摘要（非 `--orphan` 模式）：

```
⚠  registered but missing in storage: z_neu_open_return
⚠  stored but unregistered: old_momentum_raw
```

**选项：**
- `--orphan`：只显示 storage 有但 TOML 未注册的因子
- `--registered`：只显示已注册因子（过滤孤儿）
- `--category`：按 category 过滤
- `--enabled`：只显示 `enabled = true` 的因子

### factor-info

```
uv run python main.py factor-info <name>
```

输出：

```
── Registry ──────────────────────────────────
name:          z_neu_daily_return
category:      price
source_type:   neutralized
source_factor: daily_return
enabled:       true
tags:          momentum, short-term
description:   Neutralized daily return factor
evaluate:      quantiles=5  periods=[1,5,10]  return_type=open_t1

── Storage ───────────────────────────────────
status:        ✓ found
rows:          1,240,000
start_date:    2020-01-02
end_date:      2024-12-31
```

因子名不存在时：打印错误信息并以非零退出码退出，不抛异常堆栈。

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `config/factors.example.toml` | 新增，模板文件 |
| `config/factors.toml` | 新增，用户维护，提交 git |
| `zer0factor/registry.py` | 新增，`FactorMeta`、`EvaluateMeta`、`RegistryValidation`、`FactorRegistry` |
| `zer0factor/eval/batch.py` | 修改，支持 `factor_source = "registry"` |
| `main.py` | 修改，新增 `factor-list`、`factor-info` 命令 |

---

## 未来扩展路径

```
factor-sync     → 把 TOML 元数据写入 DuckDB，完成 C 架构
factor-list     → 接入 compute / neutralize 状态
factor-info     → 展示评估历史（run_id、最近报告）
compute         → 从 registry 读取 source_factor 驱动依赖计算
```
