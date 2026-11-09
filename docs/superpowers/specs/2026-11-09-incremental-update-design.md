# 因子增量更新与增量评估：设计方案

- 日期：2026-11-09
- 状态：**待确认，尚未实现**
- 需求条目：`docs/TODO.md` →「因子增量更新 + 增量评估」

## 1. 背景

2026-11-09 发现工作台的评估数据停在 20260515，行情已经到 20261106。各环节的截止日如下：

| 环节 | 截止日 | 位置 |
|---|---|---|
| 行情 daily_kline / daily_basic / adj_factor | 20261106 | `zer0share/data/stock/<表>/date=*` |
| 股票池 universe | 20260624（正在补） | `zer0share/data/stock/universe/name=*/date=*` |
| 因子 | 20260515 | `zer0factor/data/factors/<因子>/date=*` |
| 标准评估 | 20260515 | `data/evaluations/20261107_205716` |

股票池中断，下游跟着断，而且没有任何报警。现在只能全量补，约 3 小时，其中评估约 1 小时 40 分钟。

本方案分三部分：

1. 截止日一致性检查（§2）
2. 因子增量构建（§3）
3. 增量评估（§4）

§5 是实施顺序，§6 是需要确认的问题。

---

## 2. 截止日一致性检查（建议最先做）

### 2.1 根因修复（zer0share 仓库，另起任务）

zer0share 的 `build-universe` 不带参数时**已经是增量的**（`universe.py:_default_range_start`），它从已有股票池的最后一天续建到 `_latest_complete_source_date`。这个日期取 daily_kline、daily_basic、stock_st、suspend_d、stk_limit 五张表共同的最后一天。

问题只在于 `scheduler.py` 只做同步，从不调用它。建议在 zer0share 调度器里，五张表当天同步完成后追加一个 `build_universes_range(data_dir)` 任务，失败时走已有的 notifier 报警。这是另一个仓库的改动，单独开任务做。

### 2.2 zer0factor 侧的前置检查

新增命令 `zer0factor check-freshness`，并作为日更流水线的第一步。所有日期都通过列出 `date=*` 分区目录获得，不读数据，耗时在毫秒级。

| 检查项 | 取法 |
|---|---|
| 行情截止日 `T_mkt` | `min(daily_kline, daily_basic, adj_factor)` 的最后分区 |
| 股票池截止日 `T_univ` | `cfg.process_universe` 和 `[web.standard].universe` 各自的最后分区，取较小值 |
| 因子截止日 | 每个因子 `FactorStorage.last_date()`（见 §3.2），按族汇总，取族内最小值 |
| 评估截止日 | 最新标准 run 的 `summary.end_date` 最大值 |

判定规则：

- **目标截止日** `T = min(T_mkt, T_univ)`。
- `T_univ < T_mkt`：股票池落后，这正是本次的故障，**报警**。
  - 默认把 `T` 截到 `T_univ`，下游只补到股票池有的日期，不会产出被过滤空的分区。
  - 加 `--fix-universe` 时，调用 zer0share 的 `build_universes_range` 自动续建，然后重新检查。zer0factor 已经通过 LocalPro 依赖 zer0share，可以直接 import。
- 某个因子族截止日 `< T`：列为“待增量构建”。
- 评估截止日 `< 因子截止日`：列为“待增量评估”。
- 退出码：全部一致为 0；有落后为 1。定时任务据此决定是否继续，并通过已有的飞书 notifier 发摘要。

为什么默认截断而不是直接报错：股票池落后几天时，截断仍能把能补的部分补上；报警保证有人知道。

---

## 3. 因子增量构建

### 3.1 现状逐条分析

| 命令 / 阶段 | 读入范围 | 写入 | 增量是否正确 |
|---|---|---|---|
| `compute-returns` | 行情从 `cfg.start_date`（2016）起 | 全部分区 | 没有 `--start-date`，只能全量 |
| `compute-market-cap` | 同上 | 全部分区，外加 z 分数版本 | 只能全量 |
| `build-factors`，派生族（rolling_return、zer0alpha 的 intraday_* 等，`uses_data_provider=False`）raw 阶段 | `_read_required_factor(storage, base, None, end)`，读**全部历史** | `_filter_long_by_date` 截到 `>= start_date`，`delete_matching` 只覆盖这些分区 | **正确**，可以直接复用 |
| `build-factors`，直接读行情的族（`uses_data_provider=True`，zer0alpha 的 amount_stats、ma_bias、ema_atr_bias、night_ret、turnover_rate_stats、intraday_vol、intraday_turn、idiosyncratic_vol、trades_stats 等）raw 阶段 | `provider.history(start_date=start_date)`，**不回看** | 写 `run_factor` 的全部结果 | **错误**，见下文 |
| preprocess 阶段（去极值、填充、标准化、中性化） | 读 raw 和市值因子 `>= start_date` | `>= start_date` | 全部是**按日截面**运算，增量正确 |

> ⚠️ **直接读行情的族用 `--start-date` 构建时，结果是错的。** 以 `amt_mean_60d`（`min_periods=30`）为例：从 start_date 开始的前 29 天全是 NaN，没有写出分区；第 30 到 59 天只用了半个窗口。EMA/ATR 类因子从起点重新做种子。如果这次补数据用 `build-factors --start-date 20260516` 跑了这些族，**20260516 之后的值需要全量重建**。标准评估的 129 个因子都来自 rolling_return 族，不受影响。

### 3.2 存储层：`FactorStorage.last_date()`

```python
def last_date(self, factor_name: str) -> str | None:
    """最后一个 date=YYYYMMDD 分区；不存在返回 None。只列目录，不读数据。"""

def dates(self, factor_name: str) -> list[str]:
    """全部分区日期，升序。用于按“交易日个数”回看。"""
```

- `factor_stats()` 已经在用 glob 取分区日期，提出来复用即可。
- 不在 DuckDB 的 `factor_registry` 里存 last_date，以分区目录为唯一事实来源，避免两处数据不一致。以后工作台需要展示时再加缓存。
- 分区写一半就崩溃的情况：`write_dataset` 按分区写，崩溃可能留下不完整的最后一个分区。缓解办法是增量起点默认**多重算最后 1 个已有日期**（见 §3.4 的 `--rebuild-tail`，默认 1）。

### 3.3 回看期

回看期按**交易日个数**计，不按自然日。

| 因子族 / 因子 | 计算 | 精确回看（交易日） | 建议 |
|---|---|---|---|
| daily_return、open_return、overnight_return | `x / x.shift(1)` | 1 | `lookback = 1` |
| intraday_return | `close / open`，当日 | 0 | 0 |
| log_total_market_cap、log_circulating_market_cap 及其 z 分数版本 | 当日，z 分数按日截面 | 0 | 0 |
| rolling_return（内置） | `rolling(W, min_periods=W//2).mean()`，W 最大 180 | 179 | 已经读全部历史，不需要处理；可以优化为只读 `W_max - 1` 天 |
| zer0alpha 滚动类，`uses_data_provider=True`（amount_stats、amt_per_trade、turnover_rate_stats、trades_stats、ma_bias、night_ret、intraday_vol、intraday_turn） | `rolling(W, min_periods=W//2)`，W 最大 180 | `W_max - 1 = 179`；含 `shift(1)` 的再加 1 | `lookback = max(windows)`，与 `spec.min_window` 一致 |
| idiosyncratic_vol | 滚动回归，W 最大 180 | 179 | 同上；另外依赖 ff3 的 `common_returns` 文件，必须先续建它 |
| ema_atr_bias | talib EMA/ATR，递归计算，记忆无限长 | 无精确值 | 整个族标记为**不支持增量，每次全量** |
| zer0alpha intraday_* base（分钟线脚本） | 每日一个值，只用当天分钟数据 | 0 | 脚本已有 `--start-date`；派生均线走 `uses_data_provider=False` 路径，已经正确 |

ema_atr_bias 为什么不能用“长回看”近似：EMA 的误差按 `(1-α)^k` 衰减，`α = 2/(W+1)`。W=180、k=900 时误差约 5e-5，可以接受。但 ATR 用的是 Wilder 平滑，`α = 1/W`，k=900 时误差仍有约 0.7%，不可接受。

**契约改动：**

- `FactorSpec` 增加 `lookback: int | None`。默认取 `min_window`，对现有滚动类因子正好等于窗口长度。`None` 表示必须全量。
- `FactorFamily` 增加 `lookback` 属性。默认 `max(windows)`；派生族可以设为 0，因为它本来就读全部历史。
- ema_atr_bias 显式设为 `lookback = None`。
- 新写的族如果有递归或 expanding 计算，必须声明 `lookback = None`。这一条写进 `docs/factor-contract.md`。

### 3.4 增量命令

三个命令统一增加两个选项：

```
--incremental          起点 = 已有最后日期的下一个交易日（各输出 last_date 的最小值）
--rebuild-tail N       额外重算最后 N 个已有日期（默认 1），覆盖分区可能不完整、数据源修订的情况
```

`build-factors` 已有 `--start-date`，保留。`compute-returns` 和 `compute-market-cap` 补上 `--start-date / --end-date`。

**计算流程（以一个族为例）：**

1. `write_start` 有两种来源：显式 `--start-date`，或者 `--incremental` 时取族内所有输出（raw 加各 profile）`last_date` 的最小值，再按 `--rebuild-tail` 往前退 N 个交易日。
2. `load_start = write_start` 往前退 `lookback` 个交易日。交易日历取自 zer0share 的 `trade_cal`；也可以直接取已存日收益因子的 `dates()`，不需要额外依赖。
3. 读入 `[load_start, end]` 的数据，计算后把结果截到 `>= write_start`，再写入（`delete_matching` 只覆盖这些分区）。
4. `lookback is None` 时，`load_start` 取 `cfg.start_date`，相当于全量重算，但只覆盖写 `>= write_start` 的分区。

第 3 步的“截断后写”正是 `compute_and_store` 目前缺的一步，直接读行情的族的问题也是这样修复的。改动点是 `FactorComputeService.compute_and_store` 增加 `load_start` 参数，在 `run_factor` 之后执行 `_filter_long_by_date`。

**依赖顺序：**

```
compute-returns  ─┐
compute-market-cap ┼─> build-factors raw ─> build-factors preprocess
(ff3 common_returns)┘         （preprocess 依赖 z_log_circulating_market_cap 和股票池）
```

### 3.5 复权口径对增量的影响

| 口径 | zer0share 实现（`query/stock.py:pro_bar`） | 增量安全性 |
|---|---|---|
| `hfq`（绝大多数因子） | `price × adj_factor`，adj_factor 是从上市日起的累计因子 | **安全**。新的除权只影响之后的 adj_factor，历史上的 hfq 价格不变 |
| `None` / `none`（市值、成交额、换手率、笔数） | 原值 | 安全 |
| `qfq` | `adj_factor / 区间内最后一个 adj_factor` | **不安全**。基准是读入区间的最后一天，每次除权都会改变全部历史值，增量结果和全量结果会不一致。目前没有因子使用 qfq，实现时对 `adjust == "qfq"` 的族直接拒绝 `--incremental` |

还有两个边界情况：

1. `pro_bar` 对缺失的 adj_factor 做组内 `bfill`，然后 `dropna`。如果 adj_factor 表比 daily_kline 晚一天到，最后一天的行会被静默丢弃，不会写出错误值。增量起点按 last_date 计算，下次会自动补上，所以安全；§2 的检查已经把 adj_factor 计入 `T_mkt`。
2. `universe = "all"` 解析为 `stock_basic(list_status="L")`，即当前在市的股票。全量重建时，已退市股票的历史行会在 `delete_matching` 覆盖时消失；增量时旧分区保留不动。因此增量和全量在退市股上会有差异。这是现有的幸存者偏差问题，不是增量引入的，单独列为后续事项（§7）。

### 3.6 预期收益

`compute-returns` 和 `compute-market-cap` 从读 10 年行情降为读“1 天回看 + 新日期”。直接读行情的族从 10 年降为“180 天回看 + 新日期”。补一周数据，构建阶段预计从约 1 小时降到几分钟，但需要实测。

---

## 4. 增量评估

### 4.1 现状和耗时分布

`evaluate-factors` 的标准口径是 20160101 起、10 组、1D、open_t1、univ_trade_base。每个因子都会重新读全部因子值，构造 alphalens 输入，计算各项指标，并写出 `clean_factor_data.parquet`（每个因子约 150MB，一个 run 约 19GB）、`daily_ic`、`quantile_returns`、图表序列和图片。

2026-11-07 单因子串行运行的日志（z_daily_return_ma10，约 6 分钟）：

| 步骤 | 耗时 | 占比 |
|---|---|---|
| 读因子（1360 万行） | 12s | 3% |
| `factor_long_to_alphalens_series` + **`filter_factor_by_universe`** | **2m47s** | **46%** |
| alphalens `get_clean_factor_and_forward_returns` | 9s | 3% |
| 每日 IC 和分位收益 | 6s | 2% |
| summary（pyfolio、换手的 Python 循环、`calculate_period_sample_counts` 每个 period 再做一次 clean）、写产物、图表序列、图片 | **2m45s** | **46%** |

`filter_factor_by_universe`（`eval/alphalens_adapter.py`）对 1360 万行逐行调用 `universe.at[date, asset]`，这是纯 Python 循环。它**不属于指标定义**，改成向量化的 reindex/merge 后结果完全一致，可以从近 3 分钟降到几秒。这一项不做增量也能把全量评估缩短接近一半，性价比最高。

### 4.2 指标拆分：哪些可以按日拼接，哪些必须全量

以 `clean_factor_data` 为界：它的每一行属于某个日期，构造完以后所有 summary 指标都只依赖它（再加上基准收益）。

**可以按日拼接（逐日计算，与其他日期无关）：**

| 量 | 说明 |
|---|---|
| 分位划分 `factor_quantile` | alphalens `quantize_factor` 按日截面计算 |
| 每日 IC（Spearman，`factor_information_coefficient`）、每日 Pearson IC | 按日计算 |
| 每日分位收益（`mean_return_by_quantile(by_date=True)`、`quantile_daily_returns`） | 按日计算 |
| 单日换手 | 只依赖前一天的持仓集合 |
| 1D 组合日收益（long / short / ls，含成本） | 只依赖当天和前一天的持仓 |

**必须用全样本重算，但可以从已拼好的日序列廉价得到：**

| 量 | 原因 |
|---|---|
| IC Mean / Std / ICIR、HAC t 值、IC>0 % | 全样本统计 |
| 周、月胜率 | 最后一周、一个月不完整，需要重算尾部；全量重算也很便宜 |
| IC_near_far_ratio | 按序列长度对半切分，切分点会移动 |
| rolling IC（窗口 63） | 只在出图时计算（`figures.py`），每个点只依赖前 62 天；从 `daily_ic` 重算即可 |
| **因子方向 `factor_direction`** | `detect_direction` 用全样本平均 IC 判断。新数据可能让方向翻转，进而改变多空分位，换手和组合收益都要换成另一侧 |
| `quantile_returns`（全样本分位均值）、monotonicity、`long_short_spread` | 全样本池化均值 |
| 季度单调性 | 最后一个季度不完整 |
| 换手均值、年化换手 | 全样本均值 |
| pyfolio 指标（年化、夏普、回撤等） | 路径依赖。周期大于 1D 时，alphalens 用 N 个交错子组合，状态不能简单拼接 |

**alphalens 的一个全局统计（影响“精确一致”）：**
`compute_forward_returns` 默认 `filter_zscore=20`，按**每只股票的整段时间序列**的均值和标准差剔除异常前向收益。这是时间维度上的全局统计，所以：

- 只对新日期块单独 clean 时，块内的剔除阈值和全量计算不同。
- 全量重跑时，新数据也会反过来改变旧日期是否被剔除，所以全量结果本身每天都在小幅变化。
- 实际影响很小（20 倍标准差的阈值几乎只命中数据错误），但做不到逐位一致。

另外，`max_loss`（35%）是对整体丢弃比例的检查，增量块需要单独检查，再按合并后的总数复核一次。

### 4.3 可选方案

**方案 A：拼接 `clean_factor_data`，summary 全量重算（推荐）**

1. 找基准 run：最新的同口径标准 run（`web/runs.py:is_standard` 的判定条件），读每个因子已有的 `clean_factor_data`，取它的最后日期 `E_old`。
2. 新日期块起点 `S = E_old` 往前退 `max(periods) + 1` 个交易日。旧 run 尾部这些日期当时还没有完整的前向收益，已被 dropna，需要补回。
3. 只读 `[S - 回看, T]` 的因子值、价格和股票池，对这个块跑现有的 `clean_factor_and_forward_returns`，然后丢掉 `< S` 的部分。
4. 合并：旧 clean 中 `< S` 的行，加上新块。
5. 把合并后的 clean 交给**现有的** `build_summary`、`build_chart_series` 和图表。指标代码一行不改。

- 优点：
  - 不改 `eval/` 的指标定义。
  - 方向翻转、季度、HAC、pyfolio 全部自动正确。
  - 除 `filter_zscore` 的差异外，与全量结果一致，可以写测试验证（同一份数据，增量结果等于全量结果，只放宽 zscore 剔除行的容差）。
- 缺点：summary 那 2m45s 仍是全量开销。需要先做 profiling，看 pyfolio、换手循环、`calculate_period_sample_counts` 各占多少：
  - `calculate_period_sample_counts` 也可以改成只对新块计数再加上旧计数。
  - 换手循环改成向量化不改变定义，但涉及 `eval/metrics/`，需要你确认后才做。

**方案 B：保存充分统计量，指标增量更新（不推荐）**

保存每日 IC、分位的和与计数、上一日持仓等状态，按日更新各项汇总值。

- 理论上每次只算新日期，最快。
- 但方向翻转、季度单调性、近远期比、HAC、多日周期的 pyfolio 都要单独写增量公式，相当于把 `eval/metrics` 重写一遍，违反“不改指标定义”的约束，也容易和全量口径悄悄出现偏差。

**方案 C：全量评估提速（与 A 互补，建议先做）**

- 向量化 `filter_factor_by_universe` 和 `_parse_trade_date`（逐元素 `.map`），预计单因子少约 45%。
- `max_factor_trade_date` 在 `end_date` 为空时会把每个因子完整读一遍，只为取最大日期；改用 `FactorStorage.last_date()`。
- 标准口径的看板不读 PNG，图表序列已经单独存了，图片可以改为可选。

### 4.4 推荐路径和 run 的组织方式

**合并进已有 run，还是生成新 run：建议生成新 run，内容以基准 run 为底合并而成。**

- 不原地修改：工作台正在读旧 run（`SummaryCache` 按 mtime 缓存），原地改写会出现半新半旧的状态，也失去了可复现性。
- 新 run 的 `metadata.json` 口径与标准一致，保持 `end_date: null`，这样 `is_standard` 能识别。另外增加：

  ```json
  "mode": "incremental",
  "base_run_id": "20261107_205716",
  "data_end_date": "20261106"
  ```

- 看板继续“取最新标准 run”，逻辑不用改。web 侧可以选择展示“增量自 xxx”，这部分留给 web 会话。

**磁盘：** 每个 run 约 19GB，每天一个新 run 无法接受。有两种办法：

1. 推荐：`clean_factor_data` 改为按年分区的 parquet 数据集，例如 `clean_factor_data/year=2016/…`。新 run 对没有变化的年份用**硬链接**指向基准 run，只重写当年分区。每次新增约等于一年的数据量。读取方（`web/charts.py`、`web/app.py`）用 `pd.read_parquet(目录)` 同样能读，但这是 web 侧的改动，需要和 web 会话协调。
2. 退一步：只保留最近 K 个 run 的 `clean_factor_data`，更早的 run 只留 summary 和图表序列。

**定期全量对账：** 每月（或每次改动评估代码后）跑一次全量标准 run，修正 `filter_zscore` 的漂移和数据源的历史修订。CLI 提供 `evaluate-factors --incremental [--base-run <id>]`，不带 `--incremental` 时保持全量。

**预期收益：** 做完 C 再做 A，单因子从约 6 分钟降到约 2 至 3 分钟，主要剩下 summary 的耗时。129 个因子的评估预计从 1 小时 40 分钟降到 30 至 40 分钟。summary 部分进一步优化后才能降到 10 分钟级别。以上是估算，实施前先做 profiling。

---

## 5. 实施顺序（建议）

1. **check-freshness**：§2.2。只读、低风险，能立刻防止“断了没人知道”。同时另起任务，在 zer0share 调度器里加 build-universe（§2.1）。
2. **修复直接读行情的族的回看**：§3.4 第 3 步，`compute_and_store` 增加 `load_start` 并截断后写入。这是正确性修复，不只是性能优化。修好后重建受影响族 20260516 之后的数据。
3. **存储与契约**：`FactorStorage.last_date()/dates()`、`FactorSpec.lookback`、`FactorFamily.lookback`，ema_atr_bias 设为 `None`；更新 `docs/factor-contract.md`。
4. **增量构建 CLI**：`compute-returns`、`compute-market-cap`、`build-factors` 的 `--incremental / --rebuild-tail`。测试用例：同一份数据，增量结果等于全量结果。
5. **评估提速**：方案 C，先 profiling，再向量化股票池过滤。
6. **增量评估**：方案 A，`--incremental`、新 run 元数据、`clean_factor_data` 按年分区和硬链接（和 web 会话协调读取方式）。
7. **日更命令** `update-daily`：串起检查 → 增量构建（按依赖顺序）→ 增量评估 → 飞书摘要，再接入定时任务。

每一步单独提交、单独验证。第 2 步和第 5 步不依赖其他步骤，可以先做。

## 6. 需要确认的问题

1. ~~股票池落后时，默认截断到股票池截止日并报警，还是直接失败？~~ **已定（2026-11-09）**：默认截断到股票池截止日并报警，下游照常更新到股票池有的日期，不直接失败。`--fix-universe` 自动续建是否要做，还没定，先不实现。
2. ~~增量评估选方案 A（与全量一致，只有 `filter_zscore` 的微小差异，summary 仍是全量开销），是否接受？~~ **已定（2026-11-09）**：采用方案 A，逐日明细只算新日期再拼接，汇总指标用全部明细重算，并定期跑全量对账。
3. ~~新 run 加硬链接，`clean_factor_data` 改为按年分区：web 侧读取方式需要跟着调整，是否同意？还是先用“只保留最近 K 个 run”的方式？~~ **已定（2026-11-09）**：`clean_factor_data` 按年分区，没有变化的年份用硬链接共用基准 run 的文件。web 侧（`web/charts.py`、`web/app.py`）的读取方式需要和 web 会话协调修改。
4. ~~全量对账的频率：每月，还是每周？~~ **已定（2026-11-09）**：每月跑一次全量标准评估对账。改过评估代码或数据源修订过历史数据时，另外手动全量跑一次。
5. 换手循环、`calculate_period_sample_counts` 的提速涉及 `eval/metrics/` 的实现（不改定义），是否允许？

## 7. 后续事项（不在本次范围）

- `universe = "all"` 只取当前在市股票，全量重建时会抹掉已退市股的历史因子值，存在幸存者偏差。
- idiosyncratic_vol 依赖的 ff3 `common_returns` 文件同样需要增量续建（zer0alpha）。
