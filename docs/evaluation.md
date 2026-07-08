# 因子评估

本文档描述 `zer0factor` 的因子评估工作流：因子注册表、单因子 / 批量评估、评估产物和 summary 指标口径。

## 因子注册表

因子注册表默认路径是 `config/factors.toml`，用于维护哪些因子参与批量评估：

```toml
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
source_factor = "daily_return"
enabled = true
tags = ["momentum", "short-term"]

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
```

常用命令：

```bash
uv run python main.py factor-list --enabled
uv run python main.py factor-info z_neu_daily_return
```

## 单因子评估

```bash
uv run python main.py evaluate-factor log_total_market_cap \
  --start-date 20160101 \
  --periods 1,5,10 \
  --quantiles 10 \
  --return-type open_t1
```

## 批量评估

```bash
uv run python main.py evaluate-batch --file config/evaluation_batch.toml
```

## 评估产物

评估结果写入 `data/evaluations/<run_id>/`：

```text
data/evaluations/<run_id>/
├── summary.csv
├── summary.parquet
├── metadata.json
└── factors/<factor_name>/
    ├── clean_factor_data.parquet
    ├── daily_ic.parquet
    ├── quantile_returns.parquet
    └── figures/
```

## 查看 summary

```bash
uv run python main.py show-summary
uv run python main.py show-summary --period 1D
uv run python main.py show-summary --all
```

summary 默认保留方向化后的 `adjusted_ICIR`、`adjusted_t-stat`、`directional_IC>0 %` 和 `long_short_spread`；容易误读的原始方向指标，例如 `ICIR`、`t-stat`、`raw_quantile_spread` 已不再输出。`show-summary --all` 可查看少量保留的原始诊断列。

## Summary 指标口径

| 指标组 | 字段示例 | 口径 |
|---|---|---|
| 基础信息 | `factor_name`, `period`, `sample_count`, `factor_direction` | 因子名、预测周期、有效样本量和自动识别方向 |
| IC | `IC Mean`, `IC Std`, `adjusted_ICIR`, `adjusted_t-stat`, `directional_IC>0 %` | IC 保留原始均值符号；ICIR、t-stat、胜率按因子方向调整，便于不同方向因子横向比较 |
| 分组收益 | `mean_return_q1`, `mean_return_qN`, `long_short_spread_bps` | q1/qN 是原始分组均值；多空 spread 按 long/short 方向计算 |
| 单调性 | `monotonicity`, `monotonicity_q_mean`, `monotonicity_q_ir`, `monotonicity_q_gt_50_rate` | 衡量分组收益是否随分组有稳定排序关系 |
| 换手 | `turnover_daily_long`, `turnover_annual_rebalance_long` | 日均单边换手和按调仓周期折算的年化换手 |
| 组合绩效 | `long_*`, `short_*`, `long_exc_*`, `short_exc_*`, `ls_*`, `full_*`, `idx_exc_*` | 使用 Alphalens `create_pyfolio_input` 生成组合收益，再用 Pyfolio 计算年化、回撤、Calmar 和 Sharpe |

多日预测周期（如 5D、10D）会先把 Alphalens 生成的周期收益转成日化等价收益，再计算组合指标；Sharpe 会进一步按重叠窗口的自相关做自动调整，字段名保持为 `*_sharpe`。
