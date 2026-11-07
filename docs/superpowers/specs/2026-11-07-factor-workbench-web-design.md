# 因子研究工作台（Web 只读版）设计

日期：2026-11-07
状态：待确认

## 1. 目的与背景

现在用 zer0factor 做研究，全程靠命令行：评估结果散落在 `data/evaluations/<run_id>/` 里，要么翻 CSV，要么看 `show-summary` 在终端打印出的转置大表。几百个因子之间无法方便地排序、筛选和对比，单个因子的 IC 和分组收益也只有几张静态 PNG。

目标是做一个浏览器里的因子研究工作台，形态参考常见的因子看板 + 单因子分析页（功能和信息布局可以参考，界面不仿照任何现有产品的外观和品牌）。**第一版只读**：只展示已经算好、评估好的结果；新因子仍然用命令行编写、计算和评估。

使用者只有用户一人。服务跑在研究服务器上，用户从自己电脑的浏览器访问。

## 2. 目标

1. **因子看板**：列出本地所有因子，显示标准设定下的评估指标，可以排序、搜索、筛选，可以勾选因子做对比。
2. **单因子详情页**：用交互式图表完整展示一个因子的一次评估结果，并能切换查看这个因子的历次评估。
3. **因子对比页**：对勾选的 2 到 8 个因子，展示指标并排表、多空累计收益叠加图和因子相关性热力图。
4. **架构为第二版留口子**：第二版要加“在网页里写因子代码、设参数、运行分析”，第一版的后端 API 和前端详情页布局不能挡这条路。

## 3. 非目标（第一版不做）

- 在网页里编辑因子代码、提交计算或评估任务，或者显示运行进度。
- 登录、权限、多用户。
- 3D 分组累计收益图、导出 PDF、“一键生成策略”、AI 优化。
- 修改 zer0share 或 zer0alpha。

## 4. 反目标（做了也算失败的情况）

- 看板上不同因子的数字来自不同的评估设定，却混在一起排序，误导选因子。
- 页面一打开就扫描全部评估结果，或者把几百 MB 的 `clean_factor_data.parquet` 读进内存，导致首屏要等几十秒。
- 网页服务对数据有任何写操作（第一版只读，派生缓存除外，见 6.4）。
- 为了做网页而改动现有评估指标的计算口径。

## 5. 约束和现状

### 5.1 现有数据（已核实）

- **因子值**：`data/factors/<factor_name>/date=YYYYMMDD/data.parquet`，Hive 分区，共 200 个因子，约 32G。通过 `zer0factor/storage.py` 的 `FactorStorage` 读写，元数据存在 `db/factor_meta.duckdb`。
- **因子登记表**：`config/factors.toml` 目前只登记了 1 个因子，但本地存储里有 200 个。所以**因子列表以存储为准**，登记表只用来补充分类、标签和描述。
- **评估结果**：`data/evaluations/<run_id>/`，共 35 次，约 49G。
  - `metadata.json`：run_id、factor_names、start_date、end_date、periods、quantiles、return_type、max_loss、universe、rolling_ic_window、transaction_cost_bps。
  - `summary.parquet`：每个（因子 × 持有期）一行，58 列，包括 `IC Mean`、`IC Std`、`adjusted_ICIR`、`adjusted_t-stat`、`directional_IC>0 %`、`monotonicity`、换手，以及多头、空头、多空、超额的年化收益、最大回撤、夏普和卡玛等。
  - `factors/<name>/daily_ic.parquet`：每日 IC，列为持有期（`1D`、`5D`、`10D`）。由 alphalens 的 `factor_information_coefficient` 计算，默认是 **Spearman 秩相关，也就是 Rank IC**。
  - `factors/<name>/quantile_returns.parquet`：**每组的平均收益，只有 10 行，不是每日序列**。
  - `factors/<name>/clean_factor_data.parquet`：以（date, asset）为索引，列为各持有期的远期收益、`factor`、`factor_quantile`。单个因子约 290MB、900 万行。
  - 部分旧 run 缺少 `summary.parquet`，或者目录是空的，需要容错跳过。
- **现成的标准 run**：`20260614_135227` 用 `univ_trade_base`、从 20160101 开始、10 组、持有期 1D、`open_t1`，评估了 129 个因子，正好符合下面定义的标准设定，看板一上线就有数据。

### 5.2 缺口

详情页要用的以下数据，现有结果里没有直接存：

| 需要的 | 现状 | 怎么补 |
|---|---|---|
| 每日分组收益序列（画分组累计收益、分组收益表） | 没有 | 由 `clean_factor_data` 按 date × factor_quantile 求平均 |
| 普通 IC（Pearson）每日序列 | 没有 | 由 `clean_factor_data` 按日算 Pearson |
| 最新一天的因子值排名 | 没有 | 读 `clean_factor_data` 的最后一天，或直接读因子存储 |

### 5.2.1 收益口径（必须和 summary 保持一致）

summary 里的 `long_*`、`short_*`、`ls_*` 指标不是简单地拿“多头组均值减空头组均值”算出来的。它们由 `zer0factor/eval/metrics/returns.py` 构造：

- 先用 alphalens 的 `create_pyfolio_input` 构造组合：单边等权，多头组和空头组按 `factor_direction` 确定。
- 用估算的换手扣除单边 `transaction_cost_bps`（默认 10bps）。
- 持有期 n>1 时，用 `(1+r)^(1/n) - 1` 折算成日收益。

所以网页上的口径规定如下：

- **多头、空头、多空三条曲线**（详情页的分组累计收益图、对比页的叠加图）：直接复用 `returns.py` 的组合构造，得到扣费后的每日收益序列，保证曲线与指标卡的年化、回撤、夏普一致。实现方式是把 `returns.py` 内部已经算出的日收益序列暴露出来（重构为可单独调用的函数），**不改变任何数值**。要有测试保证重构前后 summary 的值完全一致。
- **各分组（1 到 N 组）曲线和分组收益表**：用 `clean_factor_data` 按 date × factor_quantile 求等权平均，得到毛收益（不扣费）。持有期 n>1 时同样用 `(1+r)^(1/n) - 1` 折成日收益后再累乘。图和表上都要标注“分组为等权毛收益；多空、多头、空头为扣费后组合收益”。
- 以上序列全部在 `write_factor_artifacts` 中新增写出，旧 run 由派生缓存补齐。

### 5.2.2 IC 的符号

summary 中 `IC Mean` 保留原始符号（`factor_direction = -1` 的因子 IC 为负），而 `adjusted_ICIR`、`adjusted_t-stat`、`directional_IC>0 %` 已经按方向调整过。网页统一按以下规则处理：

- 看板和对比页的主列是“方向调整 IC = `IC Mean` × `factor_direction`”，排序和最优值高亮都按这一列，与 ICIR、t 值的口径一致。
- 原始 `IC Mean` 只在详情页的指标卡里展示，并标注方向。
- 详情页的 IC 图表画原始符号的 IC，图上标注方向。

### 5.3 环境

服务器有 128 核、251G 内存，装了 Python 3.11（uv 管理的 `.venv`）和 Node 24 / npm 11。项目目前没有任何 Web 框架。

## 6. 方案

### 6.1 考虑过的做法

| 方案 | 做法 | 取舍 | 结论 |
|---|---|---|---|
| A. FastAPI + React 独立前端 | 后端在 zer0factor 里，提供 JSON API；前端单独放在 `web/` 目录，打包后由后端一起提供 | 代码量最大，要维护前端构建；但交互和效果最好，第二版加编辑器和任务队列不用重构 | **选用** |
| B. Streamlit 纯 Python | 一个 Python 脚本，用 plotly 画图 | 第一天就能出页面，但做不出产品级的交互；每次交互整页重跑，几百行表格会卡；第二版大概率要重写 | 不选 |
| C. 命令行生成静态 HTML | 评估后输出 HTML 报告 | 无法按需计算相关性，筛选和对比做不顺 | 不选 |

前端框架原本推荐 Vue 3，用户决定用 **React**。

### 6.2 技术栈

- **后端**：FastAPI + uvicorn，作为 zer0factor 包的一部分（`zer0factor/web/`）。新增依赖 `fastapi`、`uvicorn`。数据读取用 pandas、pyarrow 和 duckdb，都是现有依赖。
- **前端**：Vite + React 18 + TypeScript；组件库 Ant Design 5，负责表格、筛选、日期选择和布局；图表用 ECharts 5（通过 `echarts-for-react`）；路由用 React Router；数据请求和缓存用 TanStack Query。
- **启动**：新增 CLI 命令 `uv run python main.py serve [--host 127.0.0.1] [--port 8600]`，同时提供 API 和打包好的前端。默认只监听 127.0.0.1，用户通过 SSH 端口转发访问（`ssh -L 8600:localhost:8600 <服务器>`）；要在局域网里直接访问，可以加 `--host 0.0.0.0`。
- **开发**：前端用 `npm run dev`（Vite 开发服务器，把 `/api` 代理到后端）；`npm run build` 的产物输出到 `zer0factor/web/static/`，不提交到 git，所以首次使用前需要先构建一次。

### 6.3 目录结构

```text
zer0factor/
├── zer0factor/web/
│   ├── app.py            # FastAPI app，挂载 /api 和静态文件
│   ├── catalog.py        # 因子目录：存储 + 登记表 + 各 run 的 summary 合并
│   ├── runs.py           # 评估 run 的扫描、元数据解析、标准 run 匹配
│   ├── charts.py         # 详情页图表数据（由 artifacts 派生，带缓存）
│   ├── correlation.py    # 因子相关性计算
│   └── static/           # 前端构建产物（git 忽略）
├── web/                  # React 前端源码
│   ├── src/pages/{Board,FactorDetail,Compare}.tsx
│   └── ...
└── config/settings.toml  # 新增 [web] 段
```

### 6.4 标准设定和数据来源

在 `config/settings.toml` 中新增配置：

```toml
[web]
cache_dir = "data/web_cache"

[web.standard]          # 看板“标准设定”
start_date  = "20160101"
quantiles   = 10
period      = "1D"
return_type = "open_t1"
universe    = "univ_trade_base"
```

- **标准 run 的判定**：metadata 中的 start_date、quantiles、return_type、universe 与上面的配置一致，`periods` 包含 `period`，而且 `end_date` 为空（代表评估到最新）。
- **看板每个因子显示的结果**：在所有标准 run 中，取包含这个因子的 run_id 最大（也就是最新）的那次，从中取 `period == "1D"` 的那一行 summary。没有标准结果的因子显示“未评估”，排序时排在最后。
- **派生缓存**：5.2 中缺的数据，在第一次访问某个（run, 因子）时，从 `clean_factor_data.parquet` 计算出来，写到 `data/web_cache/<run_id>/<factor>/`（体积小的 parquet）。之后直接读缓存。这是网页服务唯一的写操作，删掉缓存目录可以安全重建。
- **评估流程顺带生成**：在 `write_factor_artifacts` 里同时写出每日分组收益和 Pearson 每日 IC，新的评估结果就不用再派生了。这只是新增文件，不改动任何现有文件和指标。
- **增加一个预热命令**：`main.py web-warm --run <run_id>`，提前为一个 run 的全部因子生成缓存，可以多进程并行，避免第一次打开详情页时等待。
- **run 列表缓存**：后端启动时扫描 `data/evaluations/*/metadata.json`，只读这些小文件，不读 summary。summary 按需读取，并按文件 mtime 缓存在内存中。页面上提供“刷新”按钮，重新扫描。

## 7. 页面

### 7.1 因子看板 `/`

- **表格列**：勾选框、因子名、分类、标签、描述，以及标准设定下的指标：方向调整 Rank IC 均值（见 5.2.2）、ICIR、t 值、IC>0 比例、多空年化、多空最大回撤、多空夏普、多头超额年化、单调性、多头换手、样本区间、评估 run 和评估时间。
- **列取值说明**：
  - 指标都取自 summary 中 `period == "1D"` 的那一行。
  - 收益类指标（多头、空头、多空）在评估时已经按 `factor_direction` 确定了多空方向，直接展示 summary 的原值。IC 均值按 5.2.2 显示方向调整后的值。每行都显示方向标记。
  - 分类、标签、描述来自 `config/factors.toml`，未登记的因子留空。
- **交互**：
  - 每列都可以排序。
  - 顶部搜索框按名称模糊匹配。
  - 筛选项：分类、标签、“只看已评估”、名称前缀（原始、`z_`、`z_neu_`、`z_size_neu_`）。
  - 分页或虚拟滚动，200 行以内一页显示完也可以。
- **对比入口**：勾选后底部出现悬浮条“已选 N 个 · 开始对比”，支持 2 到 8 个因子。勾选状态保存在 URL 里，方便刷新和收藏。
- **其他**：右上角显示当前的标准设定，以及数据最后扫描的时间。

### 7.2 单因子详情页 `/factor/:name?run=<run_id>&period=1D`

- **页头**：因子名、分类、描述、标签、方向。有一个评估 run 下拉框，列出包含这个因子的所有 run，每项写明 run_id、区间、股票池、组数、持有期，标准 run 加徽标；默认选中标准 run，没有就选最新的。有多个持有期时，可以切换持有期。
- **布局**：左右两栏，左栏放评估参数（只读展示），右栏放结果。第二版会把左栏换成代码编辑器加可编辑参数，所以这里要先预留成独立组件。
- **右栏内容**：
  1. **分组累计收益**：每组一条线，再加上多空组合（多头组减空头组）。数据来自每日分组收益的累乘。
  2. **核心指标卡片**：Rank IC 均值、IC 标准差、ICIR、t 值、IC>0 比例、多空、多头和空头的年化收益、最大回撤、夏普、单调性、换手。全部取自 summary。
  3. **分组收益表**：每组一行，列为年化收益、超额年化（相对全市场平均）、最大回撤、年化波动、夏普；再加一行多空组合。由每日分组收益计算。
  4. **IC 分析**，分 Rank IC 和 IC 两组，每组四张图：
     - IC 序列：每日柱状图叠加累计 IC 折线；数据点太多时按月聚合，图上要注明。
     - IC 分布：直方图加正态拟合曲线。
     - IC 自相关：滞后 0 到 23 阶，带 95% 置信区间。
     - IC 衰减：滞后 1 到 20 日的 IC。如果持有期数据不够算，就用 run 里已有的各持有期（`1D`、`5D`、`10D`）IC 均值代替，并在图上说明。
  5. **最新因子值**：评估区间最后一天的因子值，按从高到低排序，分页，显示股票代码、名称、因子值和所在分组。股票名称从 zer0share 的 `stock/basic` 读取。

### 7.3 因子对比页 `/compare?f=a,b,c`

- 所有因子都用各自的标准 run（没有的话页面提示，并显示它们最新的 run，同时标出口径不一致）。
- **指标并排表**：行是指标，列是因子，每行的最优值高亮。
- **多空累计收益叠加图**：每个因子一条线。
- **相关性热力图**：
  - 抽样区间取所选因子在各自标准 run 中样本区间的交集，在其中均匀抽取 60 个交易日。
  - 每个抽中的交易日，只保留当天 `univ_trade_base` 的成分股，与评估口径一致。成分股从 zer0share 的 `stock/universe/name=univ_trade_base/date=YYYYMMDD/` 分区读取。
  - 读取各因子当天的值，计算两两截面 Spearman 相关，再按日期平均。
  - |ρ| ≥ 0.7 的格子高亮，并在图下列出这些因子对，提示“疑似重复”。
  - 因子值通过 `FactorStorage` 或 DuckDB，只读抽中日期的分区。
  - 结果按（因子集合排序后的组合, 区间）缓存在内存中。
  - 目标耗时：8 个因子在 10 秒以内。

## 8. API（草案）

所有接口都在 `/api` 下，返回 JSON；日期统一用 `YYYY-MM-DD`。

- `GET /api/meta`：标准设定、run 列表摘要、最后扫描时间。
- `POST /api/refresh`：重新扫描 runs 和存储。
- `GET /api/factors`：看板数据，每个因子一行。
- `GET /api/factors/{name}`：因子基础信息，以及包含它的 run 列表。
- `GET /api/factors/{name}/runs/{run_id}?period=1D`：详情页的全部数据，包括 summary 行、分组日收益（累计）、分组收益表、IC 和 Rank IC 序列、分布、自相关、衰减。
- `GET /api/factors/{name}/runs/{run_id}/latest?page=&size=`：最新因子值，分页。
- `GET /api/compare?f=a,b,c`：指标表和多空曲线。
- `GET /api/compare/correlation?f=a,b,c`：相关矩阵。

## 9. 错误处理

- run 目录缺文件或损坏时，扫描阶段跳过这个 run，并记录日志，不能让整个服务崩掉。
- 详情页某个派生数据算不出来（比如 `clean_factor_data` 缺失）时，对应图表显示“该 run 缺少原始数据”，其余部分照常显示。
- 后端出错时返回带说明的错误码，前端的每个卡片单独显示错误，不能整页白屏。

## 10. 测试

- **后端**：用 pytest 给 `runs.py`、`catalog.py`、`charts.py`、`correlation.py` 写单元测试，用 `tmp_path` 构造小型的假 run 目录和因子分区。用 FastAPI TestClient 对每个接口做冒烟测试，沿用现有 tests 的风格。
- **派生计算**：用小数据和手算结果对比，比如分组日均收益、累计收益、Pearson IC、自相关。
- **前端**：TypeScript 类型检查加构建通过。不写端到端测试，用真实数据在浏览器里手动走一遍三个页面。

## 11. 交给实现者决定的

- 前端的具体视觉风格（配色、间距），要求简洁，支持中文数字格式和涨红跌绿。
- 详情页图表的具体排布。
- 数据点很多时的降采样细节。
- 缓存文件的具体格式。

## 12. 审阅后补充的决定（Claude 的判断，请用户核对）

1. **收益口径（5.2.1）**：多头、空头、多空曲线复用 summary 的组合构造，扣费、等权、按方向确定多空，保证曲线和指标卡对得上。各分组曲线用等权毛收益，并在图上注明。为此需要把 `returns.py` 中的日收益序列暴露出来；这是一次重构，数值不变，要有测试保证。
2. **IC 符号（5.2.2）**：看板和对比页按“方向调整 IC”显示和排序；详情页保留原始符号并标注方向。
3. **相关性的股票池和区间（7.3）**：只在 `univ_trade_base` 成分股内计算；抽样区间取所选因子标准 run 样本区间的交集。
4. **标准设定的 universe**：沿用 `univ_trade_base`。已核实，目前只有 run `20260614_135227` 符合标准设定，覆盖 200 个因子中的 129 个；其余 71 个因子在看板上显示“未评估”，要补一次 `evaluate-batch` 才会有数字。
