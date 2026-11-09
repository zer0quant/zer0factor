# 因子主页版本总览 + 简化详情 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 因子主页顶部改成“处理方式 × 周期”版本表格，下面是叠加曲线，选中版本的详情按方案 A 简化。默认 run 改用最新一次统一口径评估。

**Architecture：**
- 后端：
  - `runs.py` 的标准判断加入“最新数据日”。
  - `bases.base_versions` 给每个版本带上 `metrics`。
  - `charts.py` 新增只读缓存的单版本曲线函数，`app.py` 新增 `/api/bases/{base}/curves`。
- 前端：
  - 新组件 `VersionMatrix`、`VersionCurves`、`GroupBars`。
  - `BaseHome` 用版本表格取代标签页和周期按钮。
  - `VersionDetail` 改成方案 A 布局。

**Tech Stack：** FastAPI、pandas、pytest；React 18 + antd 5 + ECharts + react-query。

**Spec：** `docs/superpowers/specs/2026-11-08-base-home-overview-design.md`

## Global Constraints

- 不改 `zer0factor/eval/` 下任何文件；不做鉴权；不动 8600、8611、8621、8631 端口。
- 不在 `/data/projects/zer0quant/zer0factor` 写任何东西；不跑构建因子或评估任务。
- 测试：`PYTHONPATH=$PWD /data/projects/zer0quant/zer0factor/.venv/bin/python -m pytest …`（在 worktree 根目录运行）。
- 前端：在 `web/` 下运行 `npm run build`。`web/node_modules` 是软链接，不要提交。
- 界面文案全中文。表格不用色阶，不标“最好”。
- 格子文案：数字 /“未评估”/“无数字”/“—”。
- 指标切换项依次为：ICIR（默认）、多头超额、多头年化、单调性、IC 胜率。
- 曲线种类：`long_excess`（默认，“多头超额”）/ `ls`（“多空”）。
- 详情区的 5 个核心数字依次为：ICIR（方向调整）、方向调整 IC、多头年化、多头超额、单调性。
- 分层收益柱状图默认显示“超额年化”，可切换为“年化收益”。

## Review Focus

1. 只有 `end_date` 为空的旧 run、没有任何 summary 的目录：最新数据日为 None 时，只有 `end_date` 为空才算标准。→ Task 1 `test_latest_data_end_none_without_summaries`。
2. 版本没有缓存或没有评估：curves 把它放进 `missing`，不报错、不重新计算。→ Task 2 `test_base_curves_missing_when_uncached`。
3. `win=none`（市值类因子只有无窗口的版本）：curves 按周期模式能取到这个版本。→ Task 2 `test_base_curves_by_window_none`。
4. 版本表格某一格没有版本（某个处理方式缺某个周期）：显示“—”且不可点击。→ Task 3 Step 3 手工检查 `daily_return`。
5. 切换版本后按浏览器后退：回到上一个版本。→ Task 3 Step 3 手工检查。

---

### Task 1: 标准口径识别“结束日 = 最新数据日”的 run

**Files:**
- Modify: `zer0factor/web/runs.py`（`is_standard`、`standard_rows`，新增 `latest_data_end`）
- Modify: `zer0factor/web/catalog.py`（新增 `Catalog.is_standard(run)`，`standard_rows` 传入最新数据日）
- Modify: `zer0factor/web/app.py:57`（`_run_summary` 改用 `catalog.is_standard(run)`）
- Test: `tests/web/test_runs.py`

**Interfaces:**
- Produces：
  - `runs.latest_data_end(runs: list[RunInfo], cache: SummaryCache) -> str | None`：所有带 summary 的 run 中 summary `end_date` 列的最大值，格式统一为 `YYYYMMDD`。
  - `runs.is_standard(run, std, latest_end: str | None = None) -> bool`：`end_date` 为空，或者 `latest_end` 不为空且 `run.end_date >= latest_end`。其他条件不变。
  - `runs.standard_rows(runs, std, cache)`：内部计算 `latest_end`，并传给 `is_standard`。
  - `Catalog.is_standard(run: RunInfo) -> bool`。

- [ ] **Step 1: 写失败测试**
  - `test_is_standard_true_when_end_date_is_latest_data_date`：建两个 run，其中一个 `end_date` 为 None。从 summary 读出 `latest = latest_data_end(...)`，再建一个 `metadata={"end_date": latest}` 的 run。断言 `is_standard(run, STD, latest)` 成立，并且 `standard_rows` 给 `fa` 选这个更新的 run。
  - `test_is_standard_false_when_end_date_before_latest`：`end_date="20200101"` 时，`is_standard(run, STD, latest)` 为 False。
  - `test_latest_data_end_none_without_summaries`：`write_summary=False` 时返回 None；此时 `end_date` 非空的 run 判为不标准。
  - 原有的 `test_is_standard_false_when_end_date_set` 保持不变（不传 `latest_end`）。
- [ ] **Step 2: 运行**：`… -m pytest tests/web/test_runs.py -q` → 新用例失败。
- [ ] **Step 3: 实现。** `end_date` 列的值可能是字符串或 Timestamp，用 `pd.Timestamp(v).strftime("%Y%m%d")` 统一格式。
- [ ] **Step 4: 运行**：`… -m pytest tests/web -q` → 全部 PASS。
- [ ] **Step 5: 提交** `fix(web): runs ending on the latest data date count as standard`

### Task 2: 版本指标与叠加曲线接口

**Files:**
- Modify: `zer0factor/web/bases.py`（`base_versions` 的版本加上 `metrics`）
- Modify: `zer0factor/web/charts.py`（新增 `version_curve`）
- Modify: `zer0factor/web/app.py`（新增路由 `/api/bases/{base}/curves`）
- Test: `tests/web/test_bases.py`、`tests/web/test_api.py`

**Interfaces:**
- Produces：
  - `base_versions(...)["versions"][i]["metrics"]: dict[str, float | None]`，键为 `bases.METRIC_KEYS`。
  - `charts.version_curve(run: RunInfo, factor: str, period: str, cache_dir: Path, kind: Literal["long_excess", "ls"]) -> pd.Series | None`：只用 `cached_series`。`long_excess` 的日收益为 `port[f"{period}:long"] - port[f"{period}:benchmark"].fillna(0)`，`ls` 为 `port[f"{period}:ls"]`，再计算 `(1 + r.fillna(0)).cumprod() - 1`。缺列或无缓存时返回 None。
  - `GET /api/bases/{base}/curves?prep=&win=&kind=long_excess`：
    - `prep` 和 `win` 必须恰好给一个，否则返回 400。`kind` 不是两种之一时返回 400；base 不存在时返回 404。
    - 选中的版本按 `base_versions` 的顺序排列，每个版本用 `catalog.standard_rows()` 里的 run 和 `standard.period`。
    - 返回 `{"kind", "dates": [YYYY-MM-DD], "series": {name: [float|None]}, "missing": [name]}`，日期取各条曲线日期的并集，用 ffill 补齐（同 `/api/compare`）。

- [ ] **Step 1: 写失败测试**
  - `test_bases.py::test_base_versions_carry_metrics`：版本行里的 `icir` 为 0.5，断言 `versions[0]["metrics"]["icir"] == 0.5`，并且 `metrics` 的键集合等于 `METRIC_KEYS`。
  - `test_api.py::test_base_curves_by_prep`：先请求 `/api/factors/fa/runs/20260101_000000?period=1D` 生成缓存，再请求 `/api/bases/fa/curves?prep=raw`。断言 `series` 里有 `fa`，长度等于 `len(dates)`，并且 `missing == []`。
  - `test_base_curves_by_window_none`：`?win=none&kind=ls` 返回 200，`series` 里有 `fa`。
  - `test_base_curves_missing_when_uncached`：不先请求详情，`?prep=raw` 的 `missing` 包含 `fa`。`fc`（未评估）的 curves 返回 200，`missing == ["fc"]`。
  - `test_base_curves_bad_args`：同时给 `prep` 和 `win`，或者 `kind=foo`，返回 400；`/api/bases/nope/curves?prep=raw` 返回 404。
- [ ] **Step 2: 运行**：`… -m pytest tests/web/test_bases.py tests/web/test_api.py -q` → 新用例失败。
- [ ] **Step 3: 实现。** `win` 参数按 `"none"` → None、其余转 int 来解析。
- [ ] **Step 4: 运行**：`… -m pytest tests/web -q` → 全部 PASS。
- [ ] **Step 5: 提交** `feat(web): per-version metrics and overlay curves for base factors`

### Task 3: 主页版本表格与叠加曲线

**Files:**
- Modify: `web/src/types.ts`（`BaseVersion.metrics`、`BaseCurves`）、`web/src/api.ts`（`fetchBaseCurves`）
- Create: `web/src/components/VersionMatrix.tsx`、`web/src/components/VersionCurves.tsx`
- Modify: `web/src/pages/BaseHome.tsx`（删除 Tabs 和周期按钮，改用以上两个组件）
- Modify: `web/src/index.css`（表格样式，替换不再使用的 `zf-sib*`）

**Interfaces:**
- Consumes：Task 2 的接口。
- Produces：
  - `BaseVersion.metrics: Partial<Record<BaseMetricKey, Num>>`；`BaseCurves { kind: "long_excess" | "ls"; dates: string[]; series: Record<string, Num[]>; missing: string[] }`。
  - `fetchBaseCurves(base: string, q: { prep?: string; win?: number | null; kind: "long_excess" | "ls" }): Promise<BaseCurves>`。
  - `VersionMatrix({ versions, primaryPrep, current, onSelect }: { versions: BaseVersion[]; primaryPrep: string; current: BaseVersion | undefined; onSelect: (v: BaseVersion) => void })`：指标选择放在组件内部，存进 URL 参数 `m`，默认 `icir`。
  - `VersionCurves({ base, current, versions }: { base: string; current: BaseVersion; versions: BaseVersion[] })`：组件内部切换模式（`by=prep|win`，默认 prep）和种类，存进 URL 参数 `by`、`kind`。线名用 `windowLabel` 或 `prepLabel`，当前版本的线加粗，`missing` 用小字列出。

- [ ] **Step 1: 实现类型、API、两个组件。**
  - 表格的行按 `comparePrep` 排序，列取所有窗口的并集，`null` 窗口排最前。旧的 `z_neu` 行标签为“中性化（旧）”。
  - “中位数”列取该行有数字的格子的中位数。
  - 格子的判断：没有这个版本 →“—”；未评估 →“未评估”；已评估但该指标为空 →“无数字”。
  - 当前版本的格子加边框，主版本行加“主版本”角标，处理方式列固定在左侧。
- [ ] **Step 2: 改 `BaseHome`。**
  - 点击格子：`select(prep, win)` 用 push（不加 `replace`），并删除 `run` 参数。
  - 快捷键：`h` / `l` 切换周期，`j` / `k` 切换处理方式（只在有对应版本时移动）。
  - “评估全部未评估窗口”的范围改为当前处理方式下“未评估或 ICIR 为空”的版本。
- [ ] **Step 3: 构建并手工检查**（在 Task 5 的验证服务上）：
  - `daily_return` 主页有缺版本的格子显示“—”。
  - 点击另一格后按后退，能回到原版本。
  - 曲线在两种模式、两种种类下都能显示。
- [ ] **Step 4: 提交** `feat(web-ui): version matrix and overlay curves on base home`

### Task 4: 版本详情改成方案 A

**Files:**
- Modify: `web/src/components/VersionDetail.tsx`
- Modify: `web/src/components/panels.tsx`（新增 `KeyMetrics`；`MetricCards` 移到折叠区，原样保留）
- Modify: `web/src/components/charts.tsx`（新增 `GroupBars`）

**Interfaces:**
- Produces：
  - `KeyMetrics({ detail }: { detail: Detail })`：一行 5 个数字，取值同 `MetricCards` 中的对应项，正负着色（红为正）。
  - `GroupBars({ rows, field }: { rows: GroupRow[]; field: "exc_ann_ret" | "ann_ret" })`：ECharts 柱状图，不含“多空”行；横轴为组号，柱顶标百分比，正值红、负值绿。

- [ ] **Step 1: 实现。** 布局从上到下：
  - 评估信息一行，保持现状。
  - `KeyMetrics`。
  - `Row`：左边是分组累计收益（`xl=14`），右边是分层收益（`xl=10`），标题旁有 `Segmented`（超额年化 / 年化收益）。
  - `Collapse`，默认全部收起，四项依次为：更多指标（`MetricCards`）、分组收益明细表（`GroupTable`）、IC 分析（`IcCharts`）、最新因子值（`LatestValues`，展开时才请求）。
- [ ] **Step 2: 构建**：`cd web && npm run build` → 成功。
- [ ] **Step 3: 提交** `feat(web-ui): simplified version detail with group return bars`

### Task 5: 文档与验证

**Files:**
- Modify: `README.md` 的 Web 工作台一节（因子主页：版本表格、叠加曲线、默认 run 规则）
- Scratch：`<scratchpad>/verify/settings.toml`（照抄参考配置，替换路径和端口）

- [ ] **Step 1: 更新 README。**
- [ ] **Step 2: 完整测试**：`… -m pytest -q` → 全部 PASS。
- [ ] **Step 3: 构建**：`cd web && npm run build` → 成功。
- [ ] **Step 4: 启动验证服务**：监听 `100.119.175.111:8641`，后台运行。评估 run 用软链接只读挂载，`web_cache` 和 duckdb 各拷贝一份，`state_dir` 用新目录。不点任何评估按钮。
- [ ] **Step 5: 截图**：`daily_return`、`intraday_rtn_var_up`、`log_total_market_cap` 三个主页，看板（确认 run 已切到 11-07），以及窄屏主页。截图发给用户。
- [ ] **Step 6: 提交** README 和计划 / 设计文档；代码是否提交按用户决定。
