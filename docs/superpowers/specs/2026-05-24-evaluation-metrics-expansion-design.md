# 因子评估指标扩展设计

## 背景

当前 zer0factor 的因子评估体系以 IC/ICIR 和分组 spread 为核心，属于统计预测力检验。
补充以回测视角为核心的收益类指标，使两类指标在同一次 evaluate 中同步输出，形成完整的因子评价体系。

## 目标

在 alphalens `clean_factor_data` 的数据结构上扩展，不引入新的核心数据依赖，
将以下四类新指标纳入 `build_summary` 的输出：

1. **IC 分频胜率 + 近远期比值**
2. **分组收益率时序指标**（年化/回撤/卡玛/夏普）
3. **换手率**（日均 + 年化，多头/空头）
4. **季度单调性稳定性统计**

同时支持可选的**指数超额收益**指标（需配置 `benchmark_index`）。

## 非目标

- 不替换 alphalens，不改变 clean_factor_data 的构造方式
- 不支持多股票池（multi-universe）并发评估
- 不实现组合优化或权重分配
- 不改变 Parquet artifacts 的目录结构

## 模块结构

现有 `zer0factor/eval/metrics.py` 拆分为子包：

```
zer0factor/eval/
├── metrics/
│   ├── __init__.py        # 对外统一导出 build_summary，下游导入路径不变
│   ├── ic.py              # IC 类指标
│   ├── returns.py         # 分组收益率时序指标
│   ├── turnover.py        # 换手率
│   └── monotonicity.py    # 全期 + 季度单调性
├── pipeline.py            # 调用各子模块，补充新指标列
├── loaders.py             # 新增 load_index_daily()
├── report.py              # 新列展示 + 可选新阈值
└── config.py              # EvaluationConfig 新增 benchmark_index
```

**约束：** `metrics/__init__.py` 保持 `build_summary`、`calculate_daily_ic`、
`calculate_quantile_returns` 的对外签名不变，现有调用方无需修改。

## 各模块设计

### `metrics/ic.py`

输入：`daily_ic: pd.DataFrame`（index=date，columns=periods）

新增输出列：

| 列名 | 计算方式 |
|---|---|
| `IC>0 %(W)` | 日 IC 按周重采样取均值，正值周数 / 总周数 × 100 |
| `IC>0 %(M)` | 日 IC 按月重采样取均值，正值月数 / 总月数 × 100 |
| `IC_near_far_ratio` | `IC_mean(最短 period) / IC_mean(最长 period)` |

现有列（IC Mean、IC Std、ICIR、t-stat、IC>0 %）保留不动。

### `metrics/returns.py`

输入：
- `clean_factor_data: pd.DataFrame`
- `daily_ic: pd.DataFrame`（用于自动检测方向）
- `index_returns: pd.Series | None`（index=trade_date，值为日收益率，来自 `pct_chg/100`）

**方向检测：** 由 `pipeline.py` 统一计算 `direction = +1 if daily_ic.mean().mean() >= 0 else -1`，作为参数传入 `returns.py` 和 `monotonicity.py`，不各自独立检测。

**数据来源：** `alphalens.performance.mean_return_by_quantile(clean_factor_data, by_date=True)`
→ 每日各分位组收益率

**构造三条曲线：**
- 多头组：direction=+1 时取最高分位，direction=-1 时取最低分位
- 空头组：反向
- 多空：多头日收益 - 空头日收益

**超额收益（demean）：**
- `alphalens.performance.mean_return_by_quantile(clean_factor_data, by_date=True, demeaned=True)`
- 同上构造多头超额、空头超额曲线

**指数超额（可选）：**
- 多头日收益 - `index_returns`（对齐日期后相减）
- 仅当 `benchmark_index` 不为 None 时计算

**每条曲线输出的指标：**

| 指标 | 公式 |
|---|---|
| 年化收益 | `(1 + r).prod() ** (252 / n) - 1` |
| 最大回撤 | 净值序列上的最大峰谷回撤比例 |
| 卡玛比率 | 年化收益 / abs(最大回撤)，回撤为 0 时输出 NaN |
| 夏普比率 | `mean(r) / std(r) * sqrt(252)`，std 为 0 时输出 NaN |

**输出列命名规则（每个 period 一组）：**

```
long_ann_ret, long_max_dd, long_calmar, long_sharpe
short_ann_ret, short_max_dd, short_calmar, short_sharpe
ls_ann_ret, ls_max_dd, ls_calmar, ls_sharpe
long_exc_ann_ret, long_exc_max_dd, long_exc_calmar, long_exc_sharpe   # demean
idx_exc_ann_ret, idx_exc_max_dd, idx_exc_calmar, idx_exc_sharpe       # 指数超额（可选）
ls_ann_ret_ratio                                                        # 多超年化 / 空超年化
```

### `metrics/turnover.py`

输入：`clean_factor_data: pd.DataFrame`，`periods: tuple[int, ...]`

**数据来源：** `alphalens.performance.factor_turnover(clean_factor_data, period=p)`
→ 每日换手率 Series

alphalens `factor_turnover(clean_factor_data, period=p)` 接受 `quantile` 参数，
分别传入多头分位号（`q_long`）和空头分位号（`q_short`），各自得到一条每日换手率 Series，
取各自均值得日均换手率。`q_long` / `q_short` 由 `returns.py` 根据 `direction` 确定后透传。

| 输出列 | 公式 |
|---|---|
| `turnover_daily_long` | 多头组换手率序列均值 |
| `turnover_annual_long` | `turnover_daily_long × 252 / period` |
| `turnover_daily_short` | 空头组换手率序列均值 |
| `turnover_annual_short` | `turnover_daily_short × 252 / period` |

### `metrics/monotonicity.py`

现有全期单调性（spearman 相关系数）保留不动。

**新增季度稳定性：**

1. 从 `clean_factor_data` 提取每日分组收益率（`by_date=True`）
2. 按季度分组，每季度内各分位组累计收益（`(1+r).prod()-1`）
3. 对每季度的分位组累计收益计算 spearman 相关系数 × direction → 季度单调性序列
4. 汇总统计：

| 输出列 | 公式 |
|---|---|
| `monotonicity_q_mean` | 季度单调性均值 |
| `monotonicity_q_ir` | 均值 / 标准差 |
| `monotonicity_q_pos_rate` | >0 占比（%） |

季度数 < 2 时输出 NaN。

## 现有文件改动

### `config.py`

```python
@dataclass(frozen=True)
class EvaluationConfig:
    ...
    benchmark_index: str | None = None  # 新增，例如 "000300.SH"
```

### `loaders.py`

新增：

```python
def load_index_daily(
    pro,
    ts_code: str,
    start_date: str,
    end_date: str | None,
) -> pd.Series:
    """返回日收益率 Series，index 为 trade_date (datetime)，值为 pct_chg/100。"""
```

### `pipeline.py`

`evaluate_factor()` 新增步骤：
1. 若 `config.benchmark_index` 不为 None，调用 `load_index_daily()` 加载指数日收益
2. 调用各子模块计算新指标
3. 将新指标列 `pd.concat` 进 summary DataFrame
4. 新增指标写入 artifacts（`extended_metrics.parquet`）

### `report.py`

- `_display_columns` 新增关键新列：`long_sharpe`、`ls_calmar`、`turnover_annual_long` 等
- `ReportThresholds` 新增可选阈值（默认值不启用，不影响现有 passed 逻辑）：
  - `min_ls_sharpe: float = 0.0`
  - `min_ls_calmar: float = 0.0`
- `build_ranked_summary` 的 `adjusted_score` 公式暂不改变，避免破坏现有排名基准

### `main.py`

`evaluate-factor`、`evaluate-factors`、`evaluate-batch` 新增可选参数：

```
--benchmark-index TEXT  指数代码，如 000300.SH，用于计算多头指数超额收益
```

## 数据流

```
clean_factor_data (alphalens)
    │
    ├── ic.py          → IC 类指标列
    ├── returns.py     → 分组收益时序指标列（+ 可选指数超额）
    ├── turnover.py    → 换手率列
    └── monotonicity.py→ 全期单调性 + 季度稳定性列
            │
            └── build_summary() → 宽 DataFrame（所有列）
                    │
                    ├── pipeline.py → write_factor_artifacts()
                    └── report.py  → build_ranked_summary()
```

## 测试策略

- 每个子模块独立单元测试，使用合成 `clean_factor_data`（不依赖真实行情）
- 覆盖边界情况：全 NaN 因子值、单一分位、direction=-1、无 benchmark_index
- `pipeline.py` 集成测试复用现有 fixture，验证新列存在且类型为 float
- `report.py` 测试验证新列不破坏现有 `passed` 逻辑和排序稳定性
- 换手率测试验证年化换手率 = 日均 × 252 / period

## 向后兼容

- `metrics/__init__.py` 保持现有导出签名不变
- `EvaluationConfig` 新字段全部有默认值，现有调用方不需要改
- `build_summary` 输出只增列不减列
- `report.py` 新阈值默认不启用，`passed` 逻辑与现有一致
