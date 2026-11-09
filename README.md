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

## Web 工作台

浏览器界面，包含五个页面：**因子看板**（一行一个原始因子，只看主版本的方向和各项指标）、**因子主页**（按处理方式 × 周期切换版本，查看分组累计收益、核心指标、IC / Rank IC 四件套、分组收益、最新因子值）、**因子对比**（指标并排、多空曲线叠加、截面相关性热力图）、**因子族**（自动发现的因子族、构建、接着评估）、**任务**（后台任务的进度、日志、取消、重跑）。

```bash
# 首次使用：构建前端（需要 Node 18+）
cd web && npm install && npm run build && cd ..

# 启动（默认只监听 127.0.0.1:8600）
uv run python main.py serve

# 服务跑在远程服务器上时，在自己电脑上做端口转发，然后打开 http://localhost:8600
ssh -L 8600:localhost:8600 <服务器>

# 可选：预先为一次评估的所有因子生成图表缓存（首次打开单个因子约需 1–2 分钟）
uv run python main.py web-warm --run <run_id> --workers 12
```

- **统一评估口径**：看板的指标统一取自满足 `config/settings.toml` 中 `[web.standard]`（区间起点、分位数、持有期、成交价、股票池，且评估到最新）的最新一次评估；页面上股票池、成交价显示中文名（如 `univ_trade_base` 显示为“基础交易池”，`open_t1` 显示为“次日开盘成交”），悬停股票池旁的问号可查看过滤规则。
- **看板按原始因子组织**：因子名拆成“原始因子 × 处理方式（原始 / Z / 市值中性 / 行业中性 / 行业+市值中性）× 周期（`_maN`）”。看板一行一个原始因子，只看**主版本**（`[web.board] primary_prep`，默认行业+市值中性；市值类因子做不了市值中性，用 `industry_only_prep`，默认行业中性）：
  - **方向**：主版本各窗口评估方向一致时显示“正向”（因子值越大未来收益越高，红）或“反向”（绿）。不一致时显示“方向不一致”。
  - **ICIR（窗口中位数）**：主版本各窗口方向调整 ICIR 的中位数，衡量逻辑整体是否有效，而不是挑出最好的窗口。悬停可查看各窗口的值。
  - **其他指标**（方向调整 IC、t 值、IC 胜率、多头年化 / 回撤 / 夏普 / 超额、单调性、多头换手）同样取主版本各窗口的中位数；“列设置”可以隐藏或显示列。
  - 主版本还没有评估的显示“待评估”，存储里没有主版本的显示“待中性化”。这两种和“方向不一致”的都不给数字、不拿其他版本顶替，也不在看板表格里列出，收在标题旁的“另有 N 个待处理”里，点开可进入它们的主页。
- **因子主页** `/base/<原始因子>`：上面一排是处理方式标签页（默认主版本，没有主版本时退回已有的最深处理方式），下面一排是周期按钮（显示各自 ICIR，`h` / `l` 切换，默认最短的已评估窗口）。下方是所选版本的详情，可以重新评估此版本、一次评估全部未评估窗口、把此版本加入对比。旧链接 `/factor/<因子名>` 会跳到对应的主页和版本。
- **缓存**：详情页需要的日度序列会派生到 `data/web_cache/`，可随时删除重建；新的评估会直接写出这些序列。
- **界面**：右上角可切换配色（跟随系统 / 浅色 / 深色，选择保存在浏览器本地）；窄屏（手机）下侧边栏收进左上角菜单。详情页累计收益图默认隐藏空头曲线（点图例显示），可切换对数坐标；对比页热力图横轴用 `#1`、`#2` 编号，对应纵轴的因子名。
- **后台任务**：在网页上发起的评估、构建、基础因子计算、缓存预热都是后台任务。任务以独立进程运行（重启 `serve` 不会中断），记录和日志保存在 `[web] state_dir`（默认 `data/workbench/`）。评估、构建同时只跑 `[web.tasks] heavy_slots` 个（默认 1），其余排队；评估成功后会自动预热缓存并刷新看板。命令行直接运行的任务不在任务页里，也不计入并发上限。
- **新建评估**：从看板对比篮的“评估”、详情页的“重新评估”、因子族页的“接着评估”打开；“统一口径”开关打开时，结果会进入看板。
- **因子族自动发现**：`[families] packages = ["zer0alpha.factors"]` 会扫描这些包下导出 `FAMILY` 的子模块（`_` 开头的模块跳过），无需逐个登记；`[external_families]` 仍然兼容。加载失败的族会在因子族页标红并显示报错。模块可声明 `SOURCE = {"paper": ..., "url": ..., "formula": ...}` 记录来源。扫描和任务用 `[web.tasks] python` 指定的解释器执行（默认为服务自身），要构建 zer0alpha 的族时把它指向 zer0alpha 的 venv。
- **安全**：工作台没有鉴权，任何能访问服务地址的人都能发起任务；只在可信网络里绑定非本机地址。
- **前端开发**：先启动 `serve`，再在 `web/` 下运行 `npm run dev`（Vite 把 `/api` 代理到 8600 端口）。

## CLI 命令一览

| 命令 | 说明 |
|---|---|
| `status` | 查看当前存储里有哪些已计算因子 |
| `factor-list` | 对比注册表和本地存储里的因子状态 |
| `factor-info <name>` | 查看单个因子的注册信息和存储状态 |
| `check-freshness` | 检查行情、股票池、因子、评估的截止日是否一致（不一致时退出码为 1，`--notify` 发飞书） |
| `compute-returns` | 计算内置收益率因子并写入本地存储（`--incremental` 只补新日期） |
| `compute-market-cap` | 计算内置市值因子并写入本地存储（`--incremental` 只补新日期） |
| `build-factors --family <name>` | 按因子族批量计算并写入本地存储（`--incremental` 只补新日期） |
| `standardize-factor <name>` | 对已存因子做截面去极值、填充和标准化 |
| `neutralize-factor <name>` | 对已标准化因子做行业 / 市值中性化 |
| `evaluate-factor <name>` | 评估单个已存因子 |
| `evaluate-factors <name...>` | 评估多个已存因子（支持 `--workers`、`--run-id`） |
| `evaluate-batch --file <file>` | 按配置文件批量评估因子 |
| `evaluate-summary` | 汇总一次评估 run 的 summary |
| `analyze-evaluation` | 分析评估 summary 并输出分组诊断 |
| `serve` | 启动 Web 工作台（含后台任务调度） |
| `families [--json]` | 列出内置、自动发现和显式登记的因子族 |
| `web-warm --run <run_id>` | 预生成 Web 图表缓存 |
| `show-summary` | 查看最近一次评估的完整 summary |

所有命令通过 `uv run python main.py <命令>` 执行，加 `--help` 查看完整参数。

### 日常增量更新

行情更新后按以下顺序执行，每一步都只补新交易日：

```bash
uv run python main.py check-freshness            # 截止日不一致时先处理（股票池落后要在 zer0share 运行 build-universe）
uv run python main.py compute-returns --incremental
uv run python main.py compute-market-cap --incremental
uv run python main.py build-factors --family rolling_return --incremental
```

- `--incremental` 从各输出中截止日最早的那个开始续算，默认重算已有的最后 1 个日期（`--rebuild-tail N`）。任何输出从未构建过时，退回全量构建。
- 直接读行情的因子族（`uses_data_provider = True`）按 `FactorFamily.lookback` 往前多读若干交易日；没有声明时重读全部历史，结果正确但较慢。使用 qfq 价格的族不支持增量。
- 增量评估尚未实现，见 `docs/superpowers/specs/2026-11-09-incremental-update-design.md`。

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
