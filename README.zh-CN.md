# zer0factor

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Status](https://img.shields.io/badge/status-early--stage-orange)
![License](https://img.shields.io/badge/license-MIT-green)

面向 A 股本地数据的 AI 因子研究工作台。

`zer0factor` 负责把研报、投资逻辑、因子想法，整理成可以审核、可以运行、可以落盘的标准因子代码：

```text
研报 / 想法 -> FactorSpec -> Python compute() -> Parquet 因子值
```

它和 [zer0share](https://github.com/zer0quant/zer0share) 是配套关系：

- `zer0share`：负责本地 A 股数据采集、同步和查询
- `zer0factor`：负责因子规范、因子生成、因子计算和因子存储

项目还在早期阶段，更适合作为研究工作台使用，不是成熟的生产级因子平台。

## 核心能力

- 标准因子接口：`FactorSpec + FactorFrame + compute()`
- `zer0share` 数据适配：把本地行情转成标准宽表面板
- 标准输出：`trade_date, ts_code, value`
- 因子存储：Parquet 分区文件 + DuckDB 注册表
- `factor-research` Codex skill：从研报提取、审核、生成和归档因子
- 已包含一轮动量研报示例和生成出的因子代码

## 目录结构

```text
zer0factor/
├── zer0factor/
│   ├── config.py              # 配置读取
│   ├── storage.py             # Parquet + DuckDB 因子存储
│   └── factor/__init__.py     # 因子接口和 zer0share provider
├── docs/skills/factor-research/
├── workspaces/                # 每轮研究流程的产物
├── notebooks/
├── tests/
└── config/settings.example.toml
```

## 安装

```bash
git clone <your-repo-url>
cd zer0factor
uv sync
```

默认要求 `zer0share` 和本项目在同级目录：

```text
work/
├── zer0factor/
└── zer0share/
```

对应配置在 `pyproject.toml`：

```toml
[tool.uv.sources]
zer0share = { path = "../zer0share" }
```

如果你的 `zer0share` 在别的位置，先改这个路径。

## 配置

```bash
cp config/settings.example.toml config/settings.toml
```

```toml
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path    = "db/factor_meta.duckdb"
log_path   = "logs/factor.log"

[factor]
universe   = "all"
start_date = "20160101"
end_date   = ""
```

## 快速开始

跑核心测试：

```bash
uv run pytest tests/test_config.py tests/test_storage.py tests/test_factor_standard.py tests/test_factor_research_skill_scripts.py
```

查看因子库状态：

```bash
uv run python main.py --config config/settings.toml status
```

检查核心代码和 skill：

```bash
uv run ruff check zer0factor/factor/__init__.py docs/skills/factor-research tests/test_factor_standard.py tests/test_factor_research_skill_scripts.py
```

## CLI

| 命令 | 说明 |
|---|---|
| `uv run python main.py status` | 查看当前存储里有哪些已计算因子 |

后续会继续补充因子执行相关命令。

## 标准因子长什么样

```python
import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class Ret20_0(Factor):
    spec = FactorSpec(
        name="ret20_0",
        inputs=["close"],
        min_window=20,
        recommended_window=60,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.close / data.close.shift(20) - 1
        return to_factor_output(value, self.spec.name)
```

因子代码只应该访问 `FactorFrame`，不要自己读文件、查 DuckDB、或者直接调用 `zer0share`。

## 标准字段

| zer0factor 字段 | zer0share 来源 | 说明 |
|---|---|---|
| `open` | `open` | provider 负责复权 |
| `high` | `high` | provider 负责复权 |
| `low` | `low` | provider 负责复权 |
| `close` | `close` | provider 负责复权 |
| `volume` | `vol` | 统一改名，方便因子代码阅读 |
| `amount` | `amount` | 成交额 |
| `return_` | `pct_chg` 或计算收益率 | 避开 Python 关键字 `return` |

默认使用后复权：`hfq`。

## 因子存储

因子值按日期分区写入 Parquet：

```text
data/factors/
└── ret20_0/
    ├── date=20240102/data.parquet
    └── date=20240103/data.parquet

db/
└── factor_meta.duckdb
```

因子结果必须是三列：

```text
trade_date, ts_code, value
```

## factor-research Skill

Codex skill 位置：

```text
docs/skills/factor-research/
```

流程：

```text
PDF 研报 / 研究想法
  -> 候选因子
  -> 人工审核
  -> FactorSpec
  -> 质量门检查
  -> Python 因子代码
  -> 执行检查
  -> 归档
```

初始化工作区：

```bash
python docs/skills/factor-research/scripts/init_factor_research_workspace.py \
  workspaces/my-factor-run \
  --target-factor-count 5 \
  --selection-mode top_representative
```

校验因子元数据：

```bash
python docs/skills/factor-research/scripts/validate_factors_json.py \
  workspaces/my-factor-run/factors.json
```

## 示例流程

`workspaces/factor-research-guosen-momentum/` 里有一轮完整的动量研报示例：

- `factors.json`
- `approved.json`
- `code/*.py`
- `results/execution_feedback.json`
- `results/factor_library.json`
- `feedback/round_feedback.md`

生成出的因子：

- `ret20_0`
- `ret240_20_remove_up_limit`
- `rank_mom120_20`
- `smooth240_1`
- `overnight_mom20`

## 当前限制

- 当前主要围绕本地 A 股数据和 `zer0share`。
- `FactorFrame` 还没有暴露 ST、停牌、上市天数、精确涨停等字段。
- 公告日因子、指数超额因子、风格回归因子还需要扩展 provider。
- API 还处在实验阶段。


## 贡献

欢迎提交 issue 和 PR。当前比较适合贡献的方向：

- 扩展 provider 字段契约
- 补充因子执行 CLI
- 增加 `FactorSpec`、`FactorFrame`、`FactorStorage` 的测试
- 增加不包含第三方版权材料的示例
- 改进文档

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 免责声明

本项目仅用于研究和工程实验，不构成任何投资建议。仓库中的因子、示例和生成结果都需要自行验证后再使用。

## License

MIT。详见 [LICENSE](LICENSE)。
