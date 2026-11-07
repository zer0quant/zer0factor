# 因子研究工作台（Web 只读版）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 在 zer0factor 里加一个只读网页工作台，包含因子看板、单因子详情页和因子对比页，展示已有的评估结果。

**Architecture：** 后端是 `zer0factor/web/` 下的 FastAPI 服务，读取 `data/evaluations/` 和 `data/factors/`。详情页需要、但现有结果里没有的序列（每日分组收益、扣费组合收益、Pearson IC），抽成 `zer0factor/eval/series.py` 中的纯函数：新的评估在跑完时写出这些序列，旧的 run 由网页在首次访问时从 `clean_factor_data` 派生，再缓存到 `data/web_cache/`。前端是 `web/` 下的 Vite + React 应用，构建产物输出到 `zer0factor/web/static/`，由 FastAPI 一起提供。

**Tech Stack：** Python 3.11、FastAPI、uvicorn、pandas、pyarrow、duckdb、alphalens-reloaded、pyfolio-reloaded；前端用 Vite、React 18、TypeScript、Ant Design 5、ECharts 5（echarts-for-react）、React Router 6 和 TanStack Query 5。

**Spec：** `docs/superpowers/specs/2026-11-07-factor-workbench-web-design.md`

## Global Constraints

- 网页服务对 `data/evaluations/`、`data/factors/`、`config/`、zer0share 数据**只读**，唯一的写入位置是 `[web].cache_dir`（默认 `data/web_cache`）。
- 不改变任何现有评估指标的数值。重构 `returns.py` 前后，`build_pyfolio_return_metrics` 的输出必须逐项相等。
- 标准设定的默认值：`start_date = "20160101"`、`quantiles = 10`、`period = "1D"`、`return_type = "open_t1"`、`universe = "univ_trade_base"`，`end_date` 必须为空。
- 看板、对比页的 IC 主列 = `IC Mean × factor_direction`（“方向调整 IC”），排序和最优值高亮都按这一列。
- 收益口径：多头、空头、多空曲线 = `returns.py` 的扣费组合日收益；分组曲线 = 等权毛收益；持有期 n>1 时一律按 `(1+r)^(1/n) - 1` 折成日收益。图表上要注明口径。
- 相关性：在 `univ_trade_base` 当日成分股内计算截面 Spearman；在所选因子标准 run 样本区间的交集中均匀抽 60 个交易日；|ρ| ≥ 0.7 标为疑似重复。
- 对比最多 8 个因子，最少 2 个。
- 服务默认监听 `127.0.0.1:8600`。
- 前端用中文；涨红跌绿（正值红色、负值绿色）。
- 提交信息里不加 `Co-Authored-By` 行。
- 在新分支 `feat/web-workbench` 上开发。仓库里 `uv.lock` 原本就有未提交的改动，不要把它混进本计划的提交（`uv add` 产生的 lock 改动要一起提交时，先和用户确认）。

## Review Focus

1. **评估正在进行中的 run 目录**：只有 `factors/` 没有 `metadata.json`，或者有 metadata 没有 summary。扫描时应该跳过，不能报错，等下次刷新再纳入。测试放在 Task 4。
2. **URL 里的因子名或 run_id 带 `../` 等路径字符**：一律返回 404，不能读到目录之外的文件。所有路径参数都必须先和扫描出的已知集合比对。测试放在 Task 8。
3. **两个请求同时首次打开同一个因子的详情页**：缓存写入要先写临时文件再原子 rename，不能产生半截文件，也不能让后一个读者读到损坏的 parquet。测试放在 Task 5。
4. **summary 里没有 `period == "1D"` 的行**（比如旧 run 只评估了 5D）：这个 run 不算标准 run 的匹配结果，详情页可以选它的已有持有期，不报错。测试放在 Task 4。
5. **某个因子的 IC 全是 NaN，或者某一组整段没有样本**：图表数据返回空数组或 null，JSON 序列化不能因为 NaN/inf 失败。所有 API 输出的浮点数中，NaN/inf 一律转成 `null`。测试放在 Task 6。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `zer0factor/eval/metrics/returns.py`（改） | 抽出 `build_portfolio_daily_returns`，`build_pyfolio_return_metrics` 改为调用它 |
| `zer0factor/eval/series.py`（新） | 图表序列的纯函数：分组日收益、Pearson 日 IC、组合日收益；读写序列目录 |
| `zer0factor/eval/evaluator.py`（改） | 评估完成后调用 `write_chart_series` |
| `zer0factor/config.py`（改） | 新增 `WebConfig`、`StandardSetting`，解析 `[web]` |
| `zer0factor/web/jsonsafe.py` | NaN/inf 转 null，DataFrame/Series 转 JSON 结构 |
| `zer0factor/web/runs.py` | 扫描 run、解析 metadata、判断标准 run、带 mtime 缓存读取 summary |
| `zer0factor/web/catalog.py` | 合并存储目录、登记表和标准 run，生成看板行 |
| `zer0factor/web/charts.py` | 详情页数据：取序列（缓存或派生）、算分组表、IC 分布、自相关、衰减、最新因子值 |
| `zer0factor/web/correlation.py` | 抽样日期、读因子分区和股票池、平均截面 Spearman |
| `zer0factor/web/app.py` | FastAPI app 工厂、全部 `/api` 路由、静态文件 |
| `zer0factor/cli/web_cmds.py` | `serve`、`web-warm` 命令 |
| `web/` | React 前端 |
| `tests/web/` | 后端测试；`conftest.py` 提供假 run 构造器 |

---

### Task 1: 抽出组合日收益序列（`returns.py` 重构）

**Files:**
- Modify: `zer0factor/eval/metrics/returns.py:27-149`
- Test: `tests/test_portfolio_daily_returns.py`
- Test fixture: `tests/fixtures/pyfolio_metrics_snapshot.json`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class PortfolioDailyReturns:
      long: pd.Series        # 扣费后日收益，index=date
      short: pd.Series
      ls: pd.Series
      full: pd.Series
      benchmark: pd.Series | None   # 全市场等权，日收益（不扣费）
      long_positions: pd.DataFrame
      short_positions: pd.DataFrame
      ls_positions: pd.DataFrame
      full_positions: pd.DataFrame
      ls_benchmark: pd.Series | None
      full_benchmark: pd.Series | None

  def build_portfolio_daily_returns(
      clean_factor_data: pd.DataFrame, *, direction: int, period: str,
      long_quantile: int, short_quantile: int, transaction_cost_bps: float = 0.0,
  ) -> PortfolioDailyReturns
  ```

- [ ] **Step 1：在重构前生成快照。** 写一个确定性的合成 `clean_factor_data` 构造器 `make_clean_factor_data(n_dates=80, n_assets=40, quantiles=5, periods=("1D","5D"), seed=7)`，放在 `tests/eval_fixtures.py`。它返回 alphalens 格式：index 为 (date, asset)，列为 `1D`、`5D`、`factor`、`factor_quantile`。日期用 `pd.bdate_range("2024-01-02", periods=n_dates)`，资产 `f"{i:06d}.SZ"`，`factor` 用 `np.random.default_rng(seed)` 生成，`factor_quantile` 按日 `pd.qcut(..., labels=1..q)`，远期收益 = 0.001·factor + 噪声。用当前代码对 `(direction=1, period="1D", long=5, short=1, cost=10)` 和 `(direction=-1, period="5D", long=1, short=5, cost=0)` 两组参数跑 `build_pyfolio_return_metrics`，把结果写进 `tests/fixtures/pyfolio_metrics_snapshot.json`（NaN 存成 `null`）。

- [ ] **Step 2：写测试。**
  ```python
  @pytest.mark.parametrize("case", SNAPSHOT_CASES)
  def test_metrics_unchanged_after_refactor(case):
      got = build_pyfolio_return_metrics(make_clean_factor_data(), **case["kwargs"])
      for k, v in case["expected"].items():
          if v is None: assert pd.isna(got[k])
          else: assert got[k] == pytest.approx(v, rel=1e-12, abs=1e-15)

  def test_daily_returns_reproduce_ls_ann_ret():
      cfd = make_clean_factor_data()
      r = build_portfolio_daily_returns(cfd, direction=1, period="1D",
                                        long_quantile=5, short_quantile=1,
                                        transaction_cost_bps=10)
      metrics = build_pyfolio_return_metrics(cfd, direction=1, period="1D",
                                             long_quantile=5, short_quantile=1,
                                             transaction_cost_bps=10)
      assert pf.timeseries.perf_stats(r.ls)["Annual return"] == pytest.approx(metrics["ls_ann_ret"])
      assert r.long.index.equals(r.short.index)
  ```

- [ ] **Step 3：运行测试，确认会失败。** 运行 `uv run pytest tests/test_portfolio_daily_returns.py -v`。预期：快照用例 PASS，`test_daily_returns_reproduce_ls_ann_ret` FAIL，报 ImportError: `build_portfolio_daily_returns`。

- [ ] **Step 4：实现。** 把 `build_pyfolio_return_metrics` 中“构造组合 → 折算日收益 → 扣费”这一段原样搬到 `build_portfolio_daily_returns`。原函数的 `try/except Exception → _empty_pyfolio_return_metrics` 保留在 `build_pyfolio_return_metrics` 里，包住对新函数的调用；新函数本身不吞异常。

- [ ] **Step 5：运行全部现有测试。** 运行 `uv run pytest tests/test_portfolio_daily_returns.py tests/test_eval_metrics_returns.py tests/test_eval_metrics.py -v`。预期：全部 PASS。

- [ ] **Step 6：提交。** `git commit -m "refactor(eval): expose portfolio daily return series"`

---

### Task 2: 图表序列模块 `series.py`，并在评估时写出

**Files:**
- Create: `zer0factor/eval/series.py`
- Modify: `zer0factor/eval/evaluator.py`（在 `write_factor_artifacts` 之后调用）
- Test: `tests/test_eval_series.py`

**Interfaces:**
- Consumes: Task 1 的 `build_portfolio_daily_returns`
- Produces:
  ```python
  SERIES_FILES = ("quantile_daily_returns.parquet", "daily_ic_pearson.parquet",
                  "portfolio_daily_returns.parquet")

  def quantile_daily_returns(clean_factor_data: pd.DataFrame, period: str) -> pd.DataFrame
      # index=date，columns=int 分组号 1..N，值=该组当天等权毛收益，已折成日收益
  def pearson_daily_ic(clean_factor_data: pd.DataFrame) -> pd.DataFrame
      # index=date，columns=持有期标签，与 daily_ic.parquet 同形
  def portfolio_daily_returns(clean_factor_data: pd.DataFrame, summary_row: Mapping) -> pd.DataFrame
      # columns=["long","short","ls","benchmark"]；
      # direction/long_quantile/short_quantile/transaction_cost_bps/period 都取自 summary_row
  def build_chart_series(clean_factor_data: pd.DataFrame, summary: pd.DataFrame) -> dict[str, pd.DataFrame]
      # key 为 SERIES_FILES 去掉扩展名；分组收益和组合收益按 summary 中的每个 period 分别计算，
      # 列加前缀 f"{period}:"，例如 "1D:3"、"1D:ls"
  def write_chart_series(directory: Path, series: dict[str, pd.DataFrame]) -> None
      # 每个文件先写 f"{name}.tmp-{uuid}"，再 os.replace 成正式文件名
  def read_chart_series(directory: Path) -> dict[str, pd.DataFrame] | None
      # 任何一个文件缺失，返回 None
  ```

- [ ] **Step 1：写测试**（继续用 `tests/eval_fixtures.make_clean_factor_data`）：
  - `test_quantile_daily_returns_matches_groupby_mean`：`period="1D"` 时，结果等于 `cfd.groupby(["date","factor_quantile"])["1D"].mean().unstack()`。
  - `test_quantile_daily_returns_converts_multi_day_period`：`period="5D"` 时，结果等于 `(1 + 上述均值) ** (1/5) - 1`。
  - `test_pearson_daily_ic_equals_manual`：取第一天，结果等于 `np.corrcoef(factor, 1D)[0,1]`。
  - `test_portfolio_daily_returns_uses_summary_row`：结果的 `ls` 列等于 `build_portfolio_daily_returns(...).ls`，参数取自给定的 summary_row。
  - `test_write_then_read_roundtrip`：用 `tmp_path` 写入后再读，各 DataFrame 用 `assert_frame_equal` 比较。
  - `test_read_returns_none_when_any_file_missing`。
  - `test_write_leaves_no_tmp_files`：写入后目录中没有 `*.tmp-*` 文件。

- [ ] **Step 2：运行测试，确认会失败。** 运行 `uv run pytest tests/test_eval_series.py -v`。预期：ImportError。

- [ ] **Step 3：实现 `series.py`。**

- [ ] **Step 4：接入评估流程。** 在 `evaluator.py` 中，`self.artifact_store.write_factor_artifacts(result)` 之后调用 `write_chart_series(result.output_dir, build_chart_series(clean_factor_data, summary))`。用 `try/except Exception` 包住，失败时只 `self._log("evaluation_chart_series_failed ...")`，不影响评估结果。

- [ ] **Step 5：补一个评估流程的测试。** 在 `tests/test_eval_evaluator.py` 中新增 `test_evaluator_writes_chart_series`：沿用该文件已有的 fake loader，断言 `run.factor_dir(name)` 下存在 `SERIES_FILES` 中的三个文件。

- [ ] **Step 6：运行测试。** 运行 `uv run pytest tests/test_eval_series.py tests/test_eval_evaluator.py -v`。预期：PASS。

- [ ] **Step 7：提交。** `git commit -m "feat(eval): persist chart series for web workbench"`

---

### Task 3: Web 配置和依赖

**Files:**
- Modify: `zer0factor/config.py`、`config/settings.example.toml`、`config/settings.toml`、`pyproject.toml`、`.gitignore`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class StandardSetting:
      start_date: str = "20160101"; quantiles: int = 10; period: str = "1D"
      return_type: str = "open_t1"; universe: str = "univ_trade_base"
  @dataclass(frozen=True)
  class WebConfig:
      cache_dir: Path = Path("data/web_cache")
      evaluations_dir: Path = Path("data/evaluations")
      registry_path: Path = Path("config/factors.toml")
      standard: StandardSetting = StandardSetting()
  # Config 新增字段：web: WebConfig = WebConfig()
  ```

- [ ] **Step 1：写测试。**
  - `test_load_config_web_defaults_when_section_missing`：没有 `[web]` 段时，`cfg.web == WebConfig()`。
  - `test_load_config_web_overrides`：`[web.standard] quantiles = 5`，`cache_dir = "x"` 时，对应字段生效。

- [ ] **Step 2：运行测试，确认会失败。** 运行 `uv run pytest tests/test_config.py -v`。预期：FAIL。

- [ ] **Step 3：实现 `load_config` 对 `[web]`、`[web.standard]` 的解析。** 把规格 6.4 节的 `[web]` 示例段落写进两个 settings 文件。

- [ ] **Step 4：加依赖和忽略规则。** 运行 `uv add "fastapi>=0.115" "uvicorn[standard]>=0.30"`，再运行 `uv add --dev httpx`（TestClient 需要）。在 `.gitignore` 中加入 `data/web_cache/`、`zer0factor/web/static/`、`web/node_modules/`。

- [ ] **Step 5：运行测试。** 运行 `uv run pytest tests/test_config.py -v`。预期：PASS。

- [ ] **Step 6：提交。** `git commit -m "feat(config): add web workbench settings"`。只提交 `uv.lock` 中本次依赖变动的部分；要是没法和原有的未提交改动分开，先停下来问用户。

---

### Task 4: run 扫描和标准 run 判定（`runs.py`）

**Files:**
- Create: `zer0factor/web/__init__.py`、`zer0factor/web/runs.py`
- Create: `tests/web/__init__.py`、`tests/web/conftest.py`
- Test: `tests/web/test_runs.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class RunInfo:
      run_id: str; path: Path; start_date: str | None; end_date: str | None
      periods: tuple[str, ...]          # 统一为 "1D" 这种形式（metadata 存的是 int）
      quantiles: int | None; return_type: str | None; universe: str | None
      transaction_cost_bps: float | None
      factor_names: tuple[str, ...]     # 只包含 factors/<name>/ 目录确实存在的因子
      has_summary: bool

  def scan_runs(evaluations_dir: Path) -> list[RunInfo]   # 按 run_id 升序；坏的 run 跳过并 logger.warning
  def is_standard(run: RunInfo, std: StandardSetting) -> bool
  class SummaryCache:
      def get(self, run: RunInfo) -> pd.DataFrame | None  # 按 summary.parquet 的 mtime 失效
  def standard_rows(runs: list[RunInfo], std: StandardSetting, cache: SummaryCache) -> dict[str, tuple[RunInfo, dict]]
      # factor_name -> (最新的标准 run, 该 run 中 period==std.period 的 summary 行)
  ```
- 测试辅助（`tests/web/conftest.py`）：fixture `make_run(run_id, factors, *, metadata=..., periods=("1D",), write_summary=True, write_metadata=True, write_series=False)`。它在 `tmp_path/"evaluations"` 下建立 run 目录，用 `make_clean_factor_data` 写出 `clean_factor_data.parquet` 和 `daily_ic.parquet`，再用真实的 `build_summary` 生成 summary，保证列名和真实数据一致。

- [ ] **Step 1：写测试。**
  - `test_scan_skips_dir_without_metadata`（Review Focus 1）。
  - `test_scan_marks_missing_summary`：`has_summary is False`，扫描不报错。
  - `test_scan_converts_int_periods`：metadata `periods=[1,5]` → `("1D","5D")`。
  - `test_is_standard_true_for_matching_metadata`；`test_is_standard_false_when_end_date_set`；`test_is_standard_false_when_universe_none`。
  - `test_standard_rows_picks_latest_run`：两个标准 run 都包含 `fa` 时，取 run_id 较大的那个。
  - `test_standard_rows_ignores_run_without_1D_row`（Review Focus 4）。
  - `test_summary_cache_reloads_on_mtime_change`。

- [ ] **Step 2：运行测试，确认会失败。** 运行 `uv run pytest tests/web/test_runs.py -v`。预期：FAIL。

- [ ] **Step 3：实现 `runs.py`。**

- [ ] **Step 4：运行测试。** 运行 `uv run pytest tests/web/test_runs.py -v`。预期：PASS。

- [ ] **Step 5：提交。** `git commit -m "feat(web): scan evaluation runs and match standard setting"`

---

### Task 5: 因子目录和看板行（`catalog.py`），以及 JSON 安全转换

**Files:**
- Create: `zer0factor/web/jsonsafe.py`、`zer0factor/web/catalog.py`
- Test: `tests/web/test_catalog.py`、`tests/web/test_jsonsafe.py`

**Interfaces:**
- Consumes: Task 4 的 `RunInfo`、`scan_runs`、`standard_rows`、`SummaryCache`；`zer0factor.registry.FactorRegistry`
- Produces:
  ```python
  def to_jsonable(obj) -> object   # 递归处理；float NaN/inf → None；Timestamp → "YYYY-MM-DD"；
                                   # numpy 标量 → Python 标量；DataFrame/Series 由调用方先转成 dict/list
  BOARD_COLUMNS: dict[str, str]    # summary 列 → API 字段名，例如 "adjusted_ICIR" → "icir"
  @dataclass
  class Catalog:
      factor_names: list[str]                 # data/factors 下的子目录名，排序
      runs: list[RunInfo]
      scanned_at: datetime
      def board_rows(self) -> list[dict]      # 每个因子一行
      def runs_for(self, factor: str) -> list[RunInfo]
      def has_factor(self, name: str) -> bool
      def get_run(self, run_id: str) -> RunInfo | None
  def build_catalog(cfg: Config) -> Catalog
  ```
- 看板行字段：`name, category, tags, description, evaluated(bool), direction, ic_adj(=IC Mean×direction), icir, t_stat, ic_win_rate, ls_ann_ret, ls_max_dd, ls_sharpe, long_exc_ann_ret, monotonicity, turnover_long(=turnover_daily_long), start_date, end_date, run_id`。分别对应 summary 列 `adjusted_ICIR`、`adjusted_t-stat`、`directional_IC>0 %`、`ls_ann_ret`、`ls_max_dd`、`ls_sharpe`、`long_exc_ann_ret`、`monotonicity`、`turnover_daily_long`。
- 登记表文件不存在或解析失败时，记录 warning，分类和标签留空，不报错。

- [ ] **Step 1：写测试。**
  - `test_to_jsonable_converts_nan_and_inf_to_none`（Review Focus 5 的一部分）。
  - `test_board_rows_lists_all_stored_factors`：存储里有 3 个因子、标准 run 只覆盖 2 个时，返回 3 行，其中 1 行 `evaluated=False`，指标都是 None。
  - `test_board_ic_adj_is_direction_adjusted`：summary 中 `IC Mean=-0.02`、`factor_direction=-1` → `ic_adj == 0.02`。
  - `test_board_merges_registry_metadata`。
  - `test_board_survives_missing_registry`。

- [ ] **Step 2：运行测试，确认会失败。** 运行 `uv run pytest tests/web/test_catalog.py tests/web/test_jsonsafe.py -v`。预期：FAIL。

- [ ] **Step 3：实现。**

- [ ] **Step 4：运行测试。** 预期：PASS。

- [ ] **Step 5：提交。** `git commit -m "feat(web): build factor catalog and board rows"`

---

### Task 6: 详情页数据（`charts.py`）

**Files:**
- Create: `zer0factor/web/charts.py`
- Test: `tests/web/test_charts.py`

**Interfaces:**
- Consumes: Task 2 的 `build_chart_series`、`read_chart_series`、`write_chart_series`；Task 4 的 `RunInfo`、`SummaryCache`；Task 5 的 `to_jsonable`
- Produces:
  ```python
  def get_series(run: RunInfo, factor: str, cache_dir: Path, summary: pd.DataFrame) -> dict[str, pd.DataFrame] | None
      # 查找顺序：run 自己的 factor 目录 → cache_dir/run_id/factor → 从 clean_factor_data 派生并写入缓存；
      # clean_factor_data 不存在时返回 None
  def detail_payload(run: RunInfo, factor: str, period: str, cache_dir: Path, summary: pd.DataFrame) -> dict
  def latest_values(run: RunInfo, factor: str, names: Mapping[str, str], page: int, size: int) -> dict
      # {"date","total","items":[{"ts_code","name","value","quantile"}]}，按 value 降序
  def ic_decay(clean_factor_data: pd.DataFrame, max_lag: int = 20) -> list[float | None]
  def autocorr_with_ci(series: pd.Series, max_lag: int = 23) -> dict   # {"acf":[...], "ci": 1.96/sqrt(n)}
  def histogram_with_normal(series: pd.Series, bins: int = 40) -> dict  # {"edges","density","normal"}
  def group_table(qret: pd.DataFrame, port: pd.DataFrame) -> list[dict]
      # 每组一行：ann_ret, exc_ann_ret（相对 benchmark）, max_dd, ann_vol, sharpe；最后加一行 "多空"（用 port["ls"]）
      # 年化按 252 个交易日；max_dd 用正数表示
  def load_stock_names(zer0share_data_dir: Path) -> dict[str, str]   # 读 stock/basic/data.parquet，取 ts_code→name
  ```
- `detail_payload` 的结构：`{"summary": {...summary 行}, "direction", "period", "notes": [...口径说明], "cumulative": {"dates", "groups": {"1":[...],...}, "long", "short", "ls"}, "group_table", "rank_ic": IcBlock, "ic": IcBlock}`。其中 `IcBlock = {"series": {"dates","values","cumulative"}, "monthly": bool, "hist", "acf", "decay"}`。
- IC 序列超过 500 个点时，按月取均值，`monthly=True`；累计 IC 始终用日度数据累加，再在月末取值。
- `ic_decay` 的算法：先把 `factor` 和 `1D` 收益分别 pivot 成 date×asset 的宽表；对 lag k = 1..max_lag，把 1D 收益宽表沿日期上移 k 行，每天计算两行的 Spearman 相关（先对行做 rank，再按行算 Pearson），然后对所有日期取均值。结果写进缓存文件 `ic_decay.json`，下次直接读。
- `notes` 必须包含这两句口径说明：“分组曲线为等权毛收益（未扣费）”、“多头/空头/多空为扣费后组合收益（单边 {cost}bps）”。

- [ ] **Step 1：写测试。**
  - `test_get_series_prefers_run_dir`：run 目录里已有序列文件时，不写缓存。
  - `test_get_series_derives_and_caches`：第一次调用后，缓存目录出现三个文件；第二次调用时，monkeypatch `build_chart_series` 让它抛异常，仍然能返回结果，说明读的是缓存。
  - `test_get_series_returns_none_without_clean_data`。
  - `test_concurrent_derivation_is_safe`（Review Focus 3）：用 `ThreadPoolExecutor` 并发 4 次调用 `get_series`，结果都不是 None，可以读回，目录里没有 tmp 文件。
  - `test_cumulative_long_matches_portfolio`：`cumulative.ls[-1] == (1+port.ls).prod()-1`。
  - `test_group_table_has_ls_row_and_positive_max_dd`。
  - `test_ic_decay_lag1_matches_manual`：对合成数据手算 lag=1 的结果，然后比对。
  - `test_autocorr_lag0_is_one`。
  - `test_detail_payload_all_nan_ic_is_serializable`（Review Focus 5）：IC 全是 NaN 时，`json.dumps(to_jsonable(payload), allow_nan=False)` 不报错。
  - `test_latest_values_sorted_and_paged`。

- [ ] **Step 2：运行测试，确认会失败。** 运行 `uv run pytest tests/web/test_charts.py -v`。预期：FAIL。

- [ ] **Step 3：实现。**

- [ ] **Step 4：运行测试。** 预期：PASS。

- [ ] **Step 5：提交。** `git commit -m "feat(web): factor detail chart data"`

---

### Task 7: 因子相关性（`correlation.py`）

**Files:**
- Create: `zer0factor/web/correlation.py`
- Test: `tests/web/test_correlation.py`

**Interfaces:**
- Consumes: Task 5 的 `Catalog`；Task 4 的 `standard_rows`
- Produces:
  ```python
  def sample_dates(available: list[str], start: str, end: str, n: int = 60) -> list[str]
      # 在 [start, end] 范围内、且 available 中存在的日期里均匀取 n 个（不足 n 个就全取），保持升序
  def factor_correlation(factors: list[str], factor_dir: Path, universe_dir: Path,
                         ranges: dict[str, tuple[str, str]], n_dates: int = 60) -> dict
      # {"factors":[...], "matrix":[[...]], "dates_used": int, "pairs_over_threshold":[{"a","b","rho"}]}
      # universe_dir = zer0share_data_dir/"stock/universe/name=univ_trade_base"
  ```
- 读取方式：每个因子只读 `factor_dir/<f>/date=<d>/data.parquet`，日期 `d` 是三个集合的交集：区间交集、各因子都有的分区、股票池里有的分区。股票池读 `universe_dir/date=<d>/` 下的 parquet，取 `ts_code` 列。每天先把各因子按 ts_code 对齐到当天成分股、去掉 NaN，再算 Spearman 矩阵；最后对所有天取均值（某对因子某天的值是 NaN 时跳过那一天）。
- 结果按 `(tuple(sorted(factors)), 区间)` 缓存在内存中，用 `functools.lru_cache(maxsize=64)`。
- 阈值固定为 0.7（取绝对值）。

- [ ] **Step 1：写测试。**（在 `tmp_path` 下造假因子分区和股票池分区，3 个因子：`b = a·2 + 微噪声`，`c` 独立）
  - `test_sample_dates_even_and_bounded`：100 个可用日期，n=10 → 10 个、升序，首尾在区间内。
  - `test_correlation_detects_duplicate_pair`：a、b 的 ρ>0.95，并且出现在 `pairs_over_threshold` 里；a、c 的 |ρ|<0.3。
  - `test_correlation_restricts_to_universe`：股票池里没有的股票，即使因子值异常也不影响结果。
  - `test_correlation_uses_range_intersection`：`dates_used` 只计交集范围内的日期。

- [ ] **Step 2：运行测试，确认会失败。** 预期：FAIL。

- [ ] **Step 3：实现。**

- [ ] **Step 4：运行测试。** 预期：PASS。

- [ ] **Step 5：提交。** `git commit -m "feat(web): sampled cross-sectional factor correlation"`

---

### Task 8: FastAPI 应用和 CLI 命令

**Files:**
- Create: `zer0factor/web/app.py`、`zer0factor/cli/web_cmds.py`
- Modify: `zer0factor/cli/__init__.py`（导入 `web_cmds`）
- Test: `tests/web/test_api.py`、`tests/test_cli.py`（新增 serve、web-warm 的 `--help` 用例）

**Interfaces:**
- Consumes: Task 4–7 的全部函数
- Produces:
  ```python
  def create_app(cfg: Config, static_dir: Path | None = None) -> FastAPI
      # 启动时 build_catalog；catalog 存在 app.state 上；POST /api/refresh 会重建它
  ```
- 路由：
  - `GET /api/meta` → `{"standard": {...}, "scanned_at", "runs": [{run_id, start_date, end_date, universe, quantiles, periods, n_factors, standard}]}`
  - `POST /api/refresh` → 与 `/api/meta` 返回相同结构
  - `GET /api/factors` → `{"rows": board_rows}`
  - `GET /api/factors/{name}` → `{"name", "meta": {category, tags, description}, "runs": [...包含该因子的 run，带 standard 标记], "default_run": run_id | None}`
  - `GET /api/factors/{name}/runs/{run_id}?period=1D` → `detail_payload`
  - `GET /api/factors/{name}/runs/{run_id}/latest?page=1&size=20` → `latest_values`
  - `GET /api/compare?f=a,b` → `{"factors": [...], "rows": [各因子的看板行], "inconsistent": [没有标准 run、用最新 run 代替的因子], "curves": {"dates", "series": {f: cum_ls}}}`
  - `GET /api/compare/correlation?f=a,b` → `factor_correlation` 的结果
- 校验：
  - `name` 必须满足 `catalog.has_factor`，`run_id` 必须在 `catalog.runs` 里，而且这个 run 要包含该因子；否则返回 404（Review Focus 2）。
  - `f` 的个数必须在 2..8 之间，否则返回 422。
  - `period` 必须在 run 的 periods 里，否则返回 404。
- 所有响应都要经过 `to_jsonable`。读 parquet 失败时返回 500，响应体为 `{"detail": "<说明>"}`。
- 有 `static_dir` 且目录存在时，挂载到 `/`，所有非 `/api` 的路径都回退到 `index.html`（供 SPA 路由使用）。
- CLI：
  - `serve --host 127.0.0.1 --port 8600`：用 `uvicorn.run(create_app(cfg, static_dir=Path(zer0factor.web.__file__).parent/"static"), host, port)` 启动。`static` 目录不存在时，先打印提示“前端未构建：cd web && npm install && npm run build”，然后照常启动 API。
  - `web-warm --run <run_id> [--workers 8]`：对这个 run 的每个因子调用 `get_series`，再调用 `ic_decay`，用 `ProcessPoolExecutor`；最后打印成功和失败的数量。

- [ ] **Step 1：写测试。**（用 `fastapi.testclient.TestClient` 加 conftest 的假 run，cfg 指向 `tmp_path`）
  - `test_factors_endpoint_returns_rows`。
  - `test_detail_endpoint_ok`：状态码 200，带 `cumulative.ls` 和 `rank_ic.series`。
  - `test_path_traversal_rejected`：`/api/factors/..%2F..%2Fetc/runs/x` 和 `/api/factors/fa/runs/..%2Fx` 都返回 404（Review Focus 2）。
  - `test_run_not_containing_factor_404`。
  - `test_compare_requires_2_to_8`：1 个因子返回 422，9 个也返回 422。
  - `test_refresh_picks_up_new_run`。
  - `test_spa_fallback_serves_index`：`static_dir` 下有 `index.html` 时，`GET /factor/abc` 返回 200 和 HTML。
  - `test_responses_have_no_nan`：所有 JSON 响应都能用 `json.loads` 解析，且不含 `NaN`。

- [ ] **Step 2：运行测试，确认会失败。** 预期：FAIL。

- [ ] **Step 3：实现 `app.py` 和 `web_cmds.py`。**

- [ ] **Step 4：运行全部测试。** 运行 `uv run pytest -q`。预期：全部 PASS。

- [ ] **Step 5：用真实数据冒烟。** 运行 `uv run python main.py serve --port 8600 &`，再执行 `curl -s localhost:8600/api/factors | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['rows']), sum(r['evaluated'] for r in d['rows']))"`。预期：第一个数等于 `ls data/factors | wc -l`（当前是 200）；第二个数是标准 run `20260614_135227` 中、并且仍在 `data/factors` 里的因子个数，最多 129，应该接近这个数。如果明显偏少，检查标准 run 的匹配逻辑。完成后停掉服务。

- [ ] **Step 6：提交。** `git commit -m "feat(web): FastAPI app with serve and web-warm commands"`

---

### Task 9: 前端脚手架和因子看板页

**Files:**
- Create: `web/`（`package.json`、`vite.config.ts`、`tsconfig.json`、`index.html`、`src/main.tsx`、`src/App.tsx`、`src/api.ts`、`src/types.ts`、`src/format.ts`、`src/pages/Board.tsx`）

**Interfaces:**
- Consumes: Task 8 的 API
- Produces（供 Task 10、11 使用）：
  - `src/api.ts`：`fetchMeta()`、`refresh()`、`fetchFactors()`、`fetchFactor(name)`、`fetchDetail(name, runId, period)`、`fetchLatest(name, runId, page, size)`、`fetchCompare(fs)`、`fetchCorrelation(fs)`。它们都返回 `src/types.ts` 中对应的类型，字段名与后端 JSON 完全一致。
  - `src/format.ts`：`pct(v, digits=2)`、`num(v, digits=4)`、`signColor(v)`。正值返回红色 `#cf1322`，负值返回绿色 `#389e0d`，null 返回灰色。null 一律显示为 `—`。
  - 路由：`/` → Board，`/factor/:name` → FactorDetail，`/compare` → Compare。

- [ ] **Step 1：初始化项目。** 运行 `npm create vite@latest web -- --template react-ts`，再在 `web/` 下安装 `antd@5 echarts@5 echarts-for-react@3 react-router-dom@6 @tanstack/react-query@5`。在 `vite.config.ts` 中设置 `build.outDir = "../zer0factor/web/static"`、`emptyOutDir: true`，并把 `server.proxy` 的 `/api` 转发到 `http://127.0.0.1:8600`。

- [ ] **Step 2：搭外壳。** 在 `App.tsx` 中写布局：左侧导航放“因子看板”，顶部显示当前标准设定（来自 `/api/meta`）、上次扫描时间和“刷新数据”按钮。ConfigProvider 设为 `zhCN` locale。

- [ ] **Step 3：实现 `Board.tsx`。**
  - 用 antd `Table`，列见规格 7.1 节，每列都可排序；未评估的行在任何排序方向下都排在最后（自定义 sorter）。
  - 表格上方放搜索框（按名称模糊匹配）、分类和标签多选、“只看已评估”开关、名称前缀单选（全部、原始、`z_`、`z_neu_`、`z_size_neu_`）。
  - 行可勾选，勾选状态写到 URL 的 `?sel=a,b`；勾选 2 个及以上时，底部出现悬浮条“已选 N 个 · 开始对比”，最多 8 个，超过时禁止继续勾选并给出提示，点击后跳到 `/compare?f=...`。
  - 点因子名进入 `/factor/:name`；方向为 -1 的因子在名字旁显示“反向”标签。

- [ ] **Step 4：类型检查并构建。** 在 `web/` 下运行 `npm run build`。预期：tsc 无报错，`zer0factor/web/static/index.html` 生成出来。

- [ ] **Step 5：手动验证。** 运行 `uv run python main.py serve`，在浏览器中打开看板，确认以下几点：行数等于存储中的因子数，有指标的行数和 Task 8 冒烟测试的结果一致；“方向调整 IC”降序排序时，未评估的行排在最后；搜索、筛选、勾选、URL 同步都正常。

- [ ] **Step 6：提交。** `git commit -m "feat(web-ui): scaffold and factor board"`。提交前确认 `node_modules` 和 `static` 已被忽略。

---

### Task 10: 单因子详情页

**Files:**
- Create: `web/src/pages/FactorDetail.tsx`、`web/src/components/charts/*.tsx`（`CumulativeChart`、`IcSeriesChart`、`IcHistChart`、`AcfChart`、`DecayChart`）、`web/src/components/ParamsPanel.tsx`、`web/src/components/MetricCards.tsx`、`web/src/components/GroupTable.tsx`、`web/src/components/LatestValues.tsx`

**Interfaces:**
- Consumes: Task 9 的 `api.ts`、`format.ts`
- `ParamsPanel` 的 props：`{ run: RunSummary }`，只负责展示参数。第二版会把它替换成可编辑的组件，所以详情页对它只依赖这一个 prop。

- [ ] **Step 1：页头和左栏。**
  - 页头显示因子名、分类、描述、标签和方向。
  - run 下拉框列出 `fetchFactor(name).runs`，每项写成 `run_id · 区间 · 股票池 · N组 · 持有期`，标准 run 加“标准”徽标。默认选 `default_run`；没有默认值时选最新的 run。
  - 所选 run 有多个持有期时，显示 Segmented 切换。
  - run 和持有期都写进 URL 的 query 参数。
  - 左栏放 `ParamsPanel`。

- [ ] **Step 2：右栏。**
  - 按顺序放：分组累计收益（N 组加多空、多头、空头，口径说明 `notes` 放在图下）、核心指标卡片（取 summary，IC 显示原始符号并标注方向）、分组收益表。
  - Rank IC 和 IC 两组各四张图：序列图（柱 + 累计折线，`monthly` 为真时标题注“月度均值”）、分布图（直方图 + 正态曲线）、自相关图（带 ±CI 虚线）、衰减图。
  - 最后是最新因子值的分页表。
  - 每个卡片单独显示 loading 和 error 状态。detail 接口返回 `cumulative` 为空时，显示“该 run 缺少原始数据”。

- [ ] **Step 3：构建。** 运行 `npm run build`。预期：无报错。

- [ ] **Step 4：手动验证。** 打开 `/factor/z_daily_return_ma10`，确认以下几点：
  - 默认选中 `20260614_135227`。
  - 多空曲线终点算出的年化，和指标卡上的多空年化在同一量级、符号一致。
  - 切到一个旧 run，比如 `20260524_092920` 的 5D，页面正常显示。
  - 首次打开一个没有缓存的因子，在一两分钟内出结果；之后再打开，几秒内就能出来。

- [ ] **Step 5：提交。** `git commit -m "feat(web-ui): factor detail page"`

---

### Task 11: 因子对比页

**Files:**
- Create: `web/src/pages/Compare.tsx`、`web/src/components/charts/CorrHeatmap.tsx`

- [ ] **Step 1：实现页面。**
  - 读 URL 的 `f` 参数。参数不足 2 个时，提示“请回看板勾选 2–8 个因子”。
  - 如果 `inconsistent` 不为空，顶部显示警告，列出哪些因子没有标准 run、用的是最新 run。
  - 指标并排表：行为指标，列为因子；按“越大越好”的规则高亮每行最优值，最大回撤和换手例外，越小越好。
  - 多空累计收益叠加图。
  - 相关性热力图单独请求（加载可能需要几秒，显示 loading）；格子里显示数值，|ρ| ≥ 0.7 的格子加粗描边，图下列出疑似重复的因子对。

- [ ] **Step 2：构建。** 运行 `npm run build`。预期：无报错。

- [ ] **Step 3：手动验证。**
  - 在看板勾选 `z_daily_return_ma5`、`z_daily_return_ma10`、`z_daily_return_ma20`、`z_size_neu_daily_return_ma20` 后点击对比。预期：它们之间的相关性较高，并被列为疑似重复。
  - 相关性在 10 秒内返回。

- [ ] **Step 4：提交。** `git commit -m "feat(web-ui): factor compare page"`

---

### Task 12: 文档和整体验证

**Files:**
- Modify: `README.md`、`README.en.md`（加“Web 工作台”一节）

- [ ] **Step 1：写文档。** 在 README 中加入以下内容：
  - 首次构建：`cd web && npm install && npm run build`
  - 启动服务：`uv run python main.py serve`
  - SSH 端口转发：`ssh -L 8600:localhost:8600 <服务器>`
  - 预热缓存：`uv run python main.py web-warm --run 20260614_135227 --workers 16`
  - 前端开发：`npm run dev`
  - 说明标准设定的含义，以及在哪里修改（`[web.standard]`）。

- [ ] **Step 2：跑全量测试和 lint。** 运行 `uv run pytest -q && uv run ruff check zer0factor tests`，以及 `cd web && npm run build`。预期：全部通过。

- [ ] **Step 3：完整手动走查。** 从看板筛选，进入详情页并切换 run，再回到看板勾选、对比。各页面都不白屏。

- [ ] **Step 4：提交。** `git commit -m "docs: web workbench usage"`
