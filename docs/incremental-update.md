# 增量更新

日常把因子和评估更新到最新交易日，不必每次全量重算。设计取舍见 [增量更新方案](superpowers/specs/2026-11-09-incremental-update-design.md)。

## 前置：同步数据

在 `zer0share` 目录下：

```bash
uv run python main.py sync --stock
uv run python main.py build-universe   # 股票池不会随行情自动更新
```

需要排查数据时，可以检查缺失的交易日和行数异常的分区（例如单日只有 5000 行，可能是接口分页截断）：

```bash
uv run python main.py quality check --market stock --mode full --start-date <起始日> --end-date <截止日>
```

## 一条命令：`update-daily`

```bash
uv run python main.py update-daily --notify             # 每个交易日
uv run python main.py update-daily --full-eval --notify # 每月一次：评估改为全量对账
```

- 先检查截止日，目标截止日取行情和股票池中较早的一个。股票池落后时照常更新到股票池的截止日，并发飞书提醒。
- 依次执行 `compute-returns`、`compute-market-cap`、各因子族的 `build-factors`（默认 `rolling_return`，可以用 `--family` 多次指定），都带 `--incremental`；最后对最新标准 run 的全部因子做增量评估。
- 任一步失败即停止，退出码为 1。`--skip-eval` 只构建，`--dry-run` 只列出计划。
- zer0alpha 的因子族要在能 import zer0alpha 的环境里运行。

## 分步执行

```bash
uv run python main.py check-freshness            # 截止日不一致时退出码为 1，--notify 发飞书，--json 给脚本读取
uv run python main.py compute-returns --incremental
uv run python main.py compute-market-cap --incremental
uv run python main.py build-factors --family rolling_return --incremental
```

- `--incremental` 从各输出中截止日最早的那个开始续算，默认重算已有的最后 1 个日期（`--rebuild-tail N`）。任何输出从未构建过时，退回全量构建。
- 直接读行情的因子族（`uses_data_provider = True`）按 `FactorFamily.lookback` 往前多读若干交易日；没有声明时重读全部历史，结果正确但较慢。使用 qfq 价格的族不支持增量。
- 评估的截止日本来就比因子晚几天（最后几天还算不出前向收益）：1D、`open_t1` 的标准口径允许晚 2 个交易日，`check-freshness` 不算落后。

## 增量评估

```bash
uv run python main.py evaluate-factors <因子...> --periods 1 --universe univ_trade_base --incremental --workers 8
```

- `--incremental` 以 `--output-dir` 下最新的同口径 run 为底（起始日、持有期、分组数、收益口径、股票池、max_loss 必须一致）；`--base-run <run_id>` 手动指定底 run。找不到底 run 时退回全量。
- 只重算底 run 的最后几个交易日和新日期，再用全部明细重算汇总指标；新 run 的 `metadata.json` 标 `"mode": "incremental"` 和 `base_run_id`，仍是标准口径的 run，会进入 Web 看板。只支持单一持有期。
- 逐日明细 `clean_factor_data.parquet` 是按年拆分的目录，`pd.read_parquet` 照常读取；没变的年份硬链接到底 run，每次只多占当年的数据量。
- 与全量的差别：alphalens 按每只股票全段历史剔除极端收益（`filter_zscore`），全量重跑时历史行会随新数据小幅变化，增量保持底 run 的历史不变。实测单因子汇总指标相对差异 < 0.02%。按设计每月跑一次全量对账。
