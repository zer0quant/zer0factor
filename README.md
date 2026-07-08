# zer0factor

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Status](https://img.shields.io/badge/status-early--stage-orange)
![License](https://img.shields.io/badge/license-MIT-green)

简体中文 | [English](README.en.md)

面向 A 股本地数据的 AI 因子研究工作台。`zer0factor` 负责把研报、投资逻辑、因子想法，整理成可以审核、可以运行、可以落盘的标准因子代码：

```text
研报 / 想法 -> FactorSpec -> Python compute() -> Parquet 因子值
```

它和 [zer0share](https://github.com/zer0quant/zer0share) 是配套关系：

- `zer0share`：负责本地 A 股数据采集、同步和查询
- `zer0factor`：负责因子规范、因子生成、预处理、评估和存储

> 项目还在早期阶段，更适合作为研究工作台使用，不是成熟的生产级因子平台。

## 核心能力

- 标准因子接口：`FactorSpec + FactorFrame + compute()`，输出统一为 `trade_date, ts_code, value`
- `zer0share` 数据适配：把本地行情转成标准宽表面板
- 因子存储：Parquet 分区文件 + DuckDB 注册表
- 因子注册表：用 `config/factors.toml` 管理待评估因子、标签和默认评估参数
- 因子预处理：截面去极值、标准化和行业 / 市值中性化
- 因子评估：基于 Alphalens / Pyfolio 生成 IC、分组收益、换手、单调性和组合绩效指标
- `factor-research` skill：从研报提取、审核、生成和归档因子，已包含一轮动量研报示例

## 安装

前置要求：

- Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)
- 已经用 `zer0share` 同步好的本地 A 股数据

默认要求 `zer0share` 和本项目在同级目录：

```text
work/
├── zer0factor/
└── zer0share/
```

如果你的 `zer0share` 在别的位置，先改 `pyproject.toml` 里的路径：

```toml
[tool.uv.sources]
zer0share = { path = "../zer0share" }
```

然后：

```bash
git clone https://github.com/zer0quant/zer0factor.git
cd zer0factor
uv sync
```

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

以内置市值因子为例，从计算到评估走一遍最小流程：

```bash
# 查看因子库当前状态
uv run python main.py --config config/settings.toml status

# 计算内置市值因子并写入本地存储
uv run python main.py compute-market-cap

# 评估因子并查看结果
uv run python main.py evaluate-factor log_total_market_cap
uv run python main.py show-summary
```

评估结果写入 `data/evaluations/<run_id>/`，指标口径详见 [docs/evaluation.md](docs/evaluation.md)。

## CLI 命令一览

| 命令 | 说明 |
|---|---|
| `status` | 查看当前存储里有哪些已计算因子 |
| `factor-list` | 对比注册表和本地存储里的因子状态 |
| `factor-info <name>` | 查看单个因子的注册信息和存储状态 |
| `compute-returns` | 计算内置收益率因子并写入本地存储 |
| `compute-market-cap` | 计算内置市值因子并写入本地存储 |
| `build-factors --family <name>` | 按因子族批量计算并写入本地存储 |
| `standardize-factor <name>` | 对已存因子做截面去极值、填充和标准化 |
| `neutralize-factor <name>` | 对已标准化因子做行业 / 市值中性化 |
| `evaluate-factor <name>` | 评估单个已存因子 |
| `evaluate-factors <name...>` | 评估多个已存因子 |
| `evaluate-batch --file <file>` | 按配置文件批量评估因子 |
| `evaluate-summary` | 汇总一次评估 run 的 summary |
| `analyze-evaluation` | 分析评估 summary 并输出分组诊断 |
| `show-summary` | 查看最近一次评估的完整 summary |

所有命令通过 `uv run python main.py <命令>` 执行，加 `--help` 查看完整参数。

## 标准因子长什么样

```python
import pandas as pd

from zer0factor.core import Factor, FactorFrame, FactorSpec, to_factor_output


class Ret20_0(Factor):
    spec = FactorSpec(
        name="ret20_0",
        inputs=["close"],
        min_window=20,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.close / data.close.shift(20) - 1
        return to_factor_output(value, self.spec.name)
```

因子代码只应该访问 `FactorFrame`，不要自己读文件、查 DuckDB、或者直接调用 `zer0share`。字段契约和存储格式详见 [docs/factor-contract.md](docs/factor-contract.md)。

## 目录结构

```text
zer0factor/
├── main.py                # CLI 入口
├── zer0factor/
│   ├── core/              # FactorSpec / FactorFrame / Factor 接口
│   ├── factors/           # 内置因子（收益率、市值等）
│   ├── cli/               # CLI 命令实现
│   ├── preprocess/        # 去极值、标准化、中性化
│   ├── eval/              # 因子评估、summary 和 report
│   ├── registry.py        # 因子注册表
│   └── storage.py         # Parquet + DuckDB 因子存储
├── config/                # settings.example.toml、factors.toml
├── docs/skills/factor-research/   # 研报到因子的 skill
├── workspaces/            # 每轮研究流程的产物
├── notebooks/
└── tests/
```

## 文档

- [因子契约](docs/factor-contract.md)：标准字段、输出格式和存储布局
- [因子评估](docs/evaluation.md)：注册表、评估命令、产物结构和指标口径
- [factor-research skill](docs/skills/factor-research/)：从研报提取、审核、生成和归档因子的完整流程
- [开发笔记](docs/devlog.md)：记录设计过程和踩坑的系列文章目录
- 示例：`workspaces/factor-research-guosen-momentum/` 包含一轮完整的动量研报因子生成记录

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

开发环境和提交规范详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 交流

我持续记录这个项目的设计过程、踩坑记录和后续扩展：

- [开发笔记目录](docs/devlog.md)：所有文章的索引，跟踪开发进度从这里开始
- 知乎：[我用 Codex，把"投资研报到股票因子"的流程做成了一个 Skill](https://zhuanlan.zhihu.com/p/2037505179373806287) / [我用 Codex + Alphalens，搭了一套适配 A 股的因子评估流水线](https://zhuanlan.zhihu.com/p/2044174825103610007)
- 微信公众号「极客投研笔记」：同步更新，欢迎关注

如果你对 AI + 量化投研、本地股票数据系统、因子研究工作流感兴趣，欢迎交流。

## 免责声明

本项目仅用于研究和工程实验，不构成任何投资建议。仓库中的因子、示例和生成结果都需要自行验证后再使用。

## License

MIT。详见 [LICENSE](LICENSE)。
