# 看板按原始因子组织（方案 D）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 看板一行一个原始因子（名称 / 方向 / 主版本 ICIR 窗口中位数），所有版本收进 `/base/:base` 因子主页。

**Architecture：** 后端新增纯函数模块 `zer0factor/web/bases.py`。它在 `Catalog.board_rows()` 的结果上做名字拆解和聚合，通过 `/api/bases`、`/api/bases/{base}` 暴露。前端重写 `Board.tsx`，新增 `BaseHome.tsx`。现有详情内容从 `FactorDetail.tsx` 抽成 `VersionDetail` 组件复用，`/factor/:name` 改为重定向。

**Tech Stack：** FastAPI、pytest；React 18 + antd 5 + react-query + react-router。

**Spec：** `docs/superpowers/specs/2026-11-08-board-by-base-design.md`

## Global Constraints

- 不改 `zer0factor/eval/` 下任何文件。
- 不做鉴权；不动 8600、8611、8621 端口上的服务。
- 不在 `/data/projects/zer0quant/zer0factor` 写任何东西；不跑构建因子或评估任务。
- 测试命令（在 worktree 根目录运行）：`PYTHONPATH=$PWD /data/projects/zer0quant/zer0factor/.venv/bin/python -m pytest …`
- 前端：`web/node_modules` 软链接到 `/data/projects/zer0quant/zer0factor/web/node_modules`；在 `web/` 下运行 `npm run build`（含 `tsc --noEmit`）。
- 默认主版本处理方式 `z_size_industry_neu`；`industry_only_bases = ["log_total_market_cap", "log_circulating_market_cap"]` 用 `z_industry_neu`。
- 状态取值固定为 `"ok" | "mixed" | "unevaluated" | "missing"`，界面文案依次为（数字）/“方向不一致”/“待评估”/“待中性化”。
- 方向文案：`1` →“正向”（红），`-1` →“反向”（绿）；悬停：“正向：因子值越大，未来收益越高”/“反向：因子值越小，未来收益越高”。
- 处理方式顺序（Python 与 TS 一致）：`raw, z, z_size_neu, z_industry_neu, z_size_industry_neu, z_neu, rank, rank_size_neu, rank_industry_neu, rank_size_industry_neu`，未知的排最后、按字母序。
- 界面文案全中文。

## Review Focus

1. 市值因子只有无窗口版本（`window = null`）：中位数就是那一个值，周期按钮显示“无窗口”。→ Task 1 `test_single_unwindowed_version`。
2. 已评估但 ICIR 为空（NaN 已在 catalog 里转成 None）的窗口：不计入中位数和方向；如果所有已评估窗口都没有数字，状态为 `unevaluated`。→ Task 1 `test_evaluated_without_icir_is_ignored`。
3. URL 里的 `prep` / `win` 在该因子下不存在（手改 URL、旧链接）：退回默认处理方式和默认窗口，不报错、不空白。→ Task 5 Step 4 手工检查。
4. `/factor/<不存在的名字>`、`/base/<不存在>`：显示“没有这个原始因子”加回看板按钮，不白屏。→ Task 2 `test_base_versions_unknown_404`，以及 Task 5 手工检查。
5. 名字拆不出前缀或窗口（如 `foo_ma`、`z_`）：整个名字当作 base，prep 为 `raw`，与 TS 规则一致。→ Task 1 `test_parse_matches_frontend_rules`。

---

### Task 1: 后端聚合模块与配置

**Files:**
- Create: `zer0factor/web/bases.py`
- Modify: `zer0factor/config.py`（新增 `BoardSetting`，`WebConfig.board`，`_parse_web` 解析 `[web.board]`）
- Modify: `config/settings.toml`（新增 `[web.board]`，写明默认值和注释）
- Test: `tests/web/test_bases.py`，`tests/test_config.py` 追加一个用例

**Interfaces:**
- Produces:
  - `config.BoardSetting(primary_prep: str = "z_size_industry_neu", industry_only_prep: str = "z_industry_neu", industry_only_bases: tuple[str, ...] = ("log_total_market_cap", "log_circulating_market_cap"))`，冻结 dataclass；`WebConfig.board: BoardSetting = BoardSetting()`。
  - `bases.ParsedName(name: str, prep: str, base: str, window: int | None)`，冻结 dataclass。
  - `bases.parse_factor_name(name: str) -> ParsedName`
  - `bases.prep_sort_key(prep: str) -> tuple[int, str]`
  - `bases.primary_prep(base: str, board: BoardSetting) -> str`
  - `bases.summarize_bases(rows: list[dict], board: BoardSetting) -> list[dict]`：按 base 名排序。每项为 `{"base", "primary_prep", "status", "direction": int|None, "icir_median": float|None, "windows": [{"name","window","evaluated","icir","direction"}], "preps": [{"prep","n_versions","n_evaluated"}]}`；`windows` 是主版本各窗口，按窗口升序、`None` 在最前。
  - `bases.base_versions(rows: list[dict], base: str, board: BoardSetting) -> dict | None`：`{"base", "primary_prep", "default_prep", "versions": [{"name","prep","window","evaluated","icir","direction","run_id"}]}`。版本按 `prep_sort_key` 再按窗口排序；没有这个 base 时返回 `None`。
  - `rows` 的每一项至少包含 `name`、`evaluated`、`icir`、`direction`、`run_id`（即 `Catalog.board_rows()` 的行）。

- [ ] **Step 1: 写失败测试** `tests/web/test_bases.py`，用手写的行字典（不需要 fixture）：
  - `test_parse_matches_frontend_rules`：`z_size_industry_neu_daily_return_ma5` → `("z_size_industry_neu", "daily_return", 5)`；`z_neu_daily_return` → `("z_neu", "daily_return", None)`；`rank_industry_neu_x_ma10` → `("rank_industry_neu", "x", 10)`；`daily_return` → `("raw", "daily_return", None)`；`foo_ma` → `("raw", "foo_ma", None)`；`z_` → `("raw", "z_", None)`；`intraday_rtn_var_up_ma40` → `("raw", "intraday_rtn_var_up", 40)`。
  - `test_ok_median_and_direction`：主版本 3 个窗口，ICIR 为 0.2、0.4、0.9，方向全为 -1 → `status == "ok"`，`direction == -1`，`icir_median == 0.4`。
  - `test_even_count_median_is_mean_of_middle`：ICIR 为 0.2、0.4 → `0.3`。
  - `test_mixed_direction`：方向为 1、-1 → `status == "mixed"`，`icir_median is None`，`direction is None`。
  - `test_unevaluated_and_missing`：主版本存在但都没有评估 → `"unevaluated"`；只有 `raw` 和 `z_` 版本 → `"missing"`；两者的 `icir_median` 都是 `None`。
  - `test_other_preps_never_substitute`：主版本未评估、`z_` 版本已评估 → 仍为 `"unevaluated"`，`icir_median is None`。
  - `test_industry_only_base_uses_industry_prep`：`z_industry_neu_log_total_market_cap` 已评估 → `primary_prep == "z_industry_neu"`，`status == "ok"`。
  - `test_single_unwindowed_version`：上一条中 `windows == [{"window": None, ...}]`，中位数等于它的 ICIR。
  - `test_evaluated_without_icir_is_ignored`：一个窗口 `evaluated=True, icir=None`，另一个 ICIR 0.5、方向 1 → `ok / 0.5`；只有前者时为 `"unevaluated"`。
  - `test_preps_counts`：`preps` 按处理方式顺序排列，`n_versions` / `n_evaluated` 计数正确。
  - `test_base_versions_default_prep`：有主版本时 `default_prep == primary_prep`；只有 `raw`、`z` 时 `default_prep == "z"`；未知 base 返回 `None`。
  - `tests/test_config.py::test_web_board_setting`：`[web.board] primary_prep = "z_industry_neu"`、`industry_only_bases = ["a"]` 能被解析；缺省时等于 `BoardSetting()`。

- [ ] **Step 2: 运行测试，确认失败**
  `PYTHONPATH=$PWD /data/projects/zer0quant/zer0factor/.venv/bin/python -m pytest tests/web/test_bases.py tests/test_config.py -q` → 应报 ImportError / AttributeError。

- [ ] **Step 3: 实现 `config.BoardSetting` 和 `bases.py`**
  - 正则与 `web/src/factorName.ts` 一致：`^(z|rank)_(?:(size_industry|size|industry)_neu_|(neu)_)?`，以及 `_ma(\d+)$`。前缀匹配的长度必须小于整个名字；窗口匹配的起点必须大于 0。
  - 只用“已评估、并且 `icir` 和 `direction` 都不是 None”的窗口来判定方向和计算中位数（用 `statistics.median`）。
  - `default_prep`：主版本处理方式存在任意版本时取它，否则取该 base 已有处理方式中 `prep_sort_key` 最大的那个。

- [ ] **Step 4: 运行测试，确认通过**（命令同 Step 2）→ 全部 PASS。

- [ ] **Step 5: 提交**
  `git add zer0factor/web/bases.py zer0factor/config.py config/settings.toml tests/web/test_bases.py tests/test_config.py && git commit -m "feat(web): aggregate factors by base with primary-version ICIR median"`

### Task 2: `/api/bases` 接口

**Files:**
- Modify: `zer0factor/web/app.py`（在 `/api/factors` 旁边新增两个路由）
- Test: `tests/web/test_api.py` 追加用例

**Interfaces:**
- Consumes：`summarize_bases`、`base_versions`、`cfg.web.board`、`catalog().board_rows()`
- Produces：`GET /api/bases` → `{"rows": summarize_bases(...)}`；`GET /api/bases/{base}` → `base_versions(...)`，为 None 时返回 404，detail 为 `unknown base factor: <base>`。

- [ ] **Step 1: 写失败测试**（复用 `client` fixture，它的存储里有 `fa` 等因子）：
  - `test_bases_endpoint_lists_bases`：`rows` 是列表，每项都有 `base`、`status` 键，`status` 取值在四种状态里。
  - `test_base_versions_endpoint`：`/api/bases/<rows[0].base>` 返回 200，`versions` 非空，每项都有 `prep`、`window`。
  - `test_base_versions_unknown_404`：`/api/bases/nope` 返回 404。

- [ ] **Step 2: 运行，确认失败**：`… -m pytest tests/web/test_api.py -q` → 新增用例 404 / FAIL。
- [ ] **Step 3: 实现两个路由**，用 `_json(...)` 返回（处理 NaN）。
- [ ] **Step 4: 运行完整 web 测试**：`… -m pytest tests/web -q` → 全部 PASS。
- [ ] **Step 5: 提交** `feat(web): base factor endpoints`

### Task 3: 前端类型、接口与链接工具

**Files:**
- Modify: `web/src/types.ts`、`web/src/api.ts`、`web/src/factorName.ts`
- Modify: `web/src/components/FactorName.tsx`、`web/src/pages/Families.tsx`、`web/src/pages/Tasks.tsx`（所有 `/factor/${…}` 链接改用 `factorHref`）

**Interfaces:**
- Produces:
  - `types.ts`：`BaseStatus = "ok" | "mixed" | "unevaluated" | "missing"`；`BaseWindow { name: string; window: number | null; evaluated: boolean; icir: Num; direction: Num }`；`BaseRow { base: string; primary_prep: string; status: BaseStatus; direction: Num; icir_median: Num; windows: BaseWindow[]; preps: { prep: string; n_versions: number; n_evaluated: number }[] }`；`BaseVersion extends BaseWindow { prep: string; run_id: string | null }`；`BaseInfo { base: string; primary_prep: string; default_prep: string; versions: BaseVersion[] }`。
  - `api.ts`：`fetchBases(): Promise<BaseRow[]>`（解包 `.rows`），`fetchBase(base: string): Promise<BaseInfo>`。
  - `factorName.ts`：`baseHref(base: string, q?: { prep?: string; win?: number | null; run?: string; period?: string }): string`，生成 `/base/<enc>?prep=…&win=…`，`win` 为 null 时写 `none`；`factorHref(name: string, q?: { run?: string; period?: string }): string`，等于对拆名结果调用 `baseHref`。

- [ ] **Step 1: 实现上述类型和函数，替换所有旧链接**（`Siblings.tsx`、`FactorMatrix.tsx`、`Board.tsx` 在后面的任务里删除或重写，这里不改）。
- [ ] **Step 2: 类型检查**：`cd web && npx tsc --noEmit` → 没有错误。
- [ ] **Step 3: 提交** `feat(web-ui): base API client and base-page links`

### Task 4: 重写看板

**Files:**
- Rewrite: `web/src/pages/Board.tsx`
- Delete: `web/src/components/FactorMatrix.tsx`（先确认没有其他引用）
- Modify: `web/src/index.css`（删除只给矩阵 / 分组用的样式，按需新增看板行样式）

**Interfaces:**
- Consumes：`fetchBases`、`baseHref`、`baseLabel`、`compareBase`、`rememberBoardSearch`
- Produces：新组件 `DirectionTag({ direction, status }: { direction: Num; status: BaseStatus })`，放在 `web/src/components/DirectionTag.tsx`，Task 5 复用。

- [ ] **Step 1: 实现**：antd `Table`，三列：
  - **因子**：`baseLabel(base)` 加灰色小字 `base`。
  - **方向**：`DirectionTag`。
  - **ICIR（窗口中位数）**：`ok` 时显示 `num(v, 3)`；否则按状态显示“方向不一致 / 待评估 / 待中性化”的灰色标签。悬停列出各窗口 ICIR，加上“已评估 k / n 个窗口”。
  - 默认按 ICIR 降序，非 `ok` 状态始终排在最后（复用 `nullsLast` 的写法）。
  - 点击整行跳到 `baseHref(base)`。
  - 搜索框匹配 base 和中文名，`q` 保存在 URL 里；保留 `/` 聚焦搜索框的快捷键。
  - 标题显示“共 N 个原始因子”。
  - 保留 `rememberBoardSearch`，让详情页的“回到看板”能保持搜索和排序。
  - 删除所有旧功能：矩阵、分组、列选择、热力、迷你曲线、多维筛选、勾选、`sel` 迁移、悬停预取、`CompareBar` 以外的对比篮入口。`CompareBar` 保留：对比篮里有东西时仍可去对比页。
- [ ] **Step 2: 构建**：`cd web && npm run build` → 成功，没有未使用的 import 报错。
- [ ] **Step 3: 提交** `feat(web-ui): board lists base factors only`

### Task 5: 因子主页与旧路由重定向

**Files:**
- Create: `web/src/pages/BaseHome.tsx`
- Create: `web/src/components/VersionDetail.tsx`（从 `FactorDetail.tsx` 搬来 `IcSection`、`IcCharts`、`Results`、`CompareToggle`，以及 run 选择、持有期、重新评估）
- Rewrite: `web/src/pages/FactorDetail.tsx` → 只做重定向：`<Navigate replace to={factorHref(name, {run, period})} />`
- Delete: `web/src/components/Siblings.tsx`
- Modify: `web/src/App.tsx`（新增路由 `/base/:base`）

**Interfaces:**
- Consumes：`fetchBase`、`fetchFactor`、`fetchDetail`、`useEvaluate().open(factors: string[], preset)`、`DirectionTag`、`fetchEvalOptions`
- Produces：`VersionDetail({ name }: { name: string })`。`run` 和 `period` 照旧从 URL 读写。

- [ ] **Step 1: 抽出 `VersionDetail`**：内容和行为与原详情页一致（run 下拉、持有期、参数摘要、核心指标、累计收益、分组收益、IC、最新因子值、“重新评估”、“加入对比”、快捷键 `a`）。快捷键 `b` 回看板。
- [ ] **Step 2: 实现 `BaseHome`**：
  - 头部：中文名、`base`、主版本的 `DirectionTag`（取自 `fetchBases` 里这一行），面包屑“因子看板 / 中文名”。
  - 处理方式 `Tabs`：选项来自 `versions` 中实际存在的 prep，按 `comparePrep` 排序，标签文字用 `prepLabel`；主版本那一项加一个小的“主版本”角标。
  - 周期按钮：沿用 `zf-sib` 样式，每个按钮显示 `windowLabel` 和下方小字“ICIR x.xx”或“未评估”。`h` / `l` 快捷键前后切换。
  - URL：`prep` 不存在时用 `default_prep`；`win` 不存在时用最短的已评估窗口，全部未评估时用最短窗口。用 `replace` 把选中的值写回 URL。切换处理方式或窗口时删除 `run`，保留 `period`。
  - “评估全部未评估窗口（k）”按钮：只在当前处理方式下有未评估窗口时显示，调用 `evaluate.open(未评估的名字, {})`，使用抽屉默认的标准口径。
  - 下方渲染 `<VersionDetail name={当前版本名} key={当前版本名} />`。
  - `fetchBase` 返回 404 时显示 `ErrorState`，加“回到因子看板”按钮。
- [ ] **Step 3: 路由**：`App.tsx` 加 `<Route path="/base/:base" element={<BaseHome />} />`；`/factor/:name` 继续指向重定向用的 `FactorDetail`。
- [ ] **Step 4: 构建并手工检查**（在 Task 6 的验证服务上）：
  - `/factor/z_size_industry_neu_daily_return_ma5?run=20260614_135227` 应跳到 `/base/daily_return?prep=z_size_industry_neu&win=5&run=…`。
  - `/base/daily_return?prep=bogus&win=999` 应退回到主版本的默认窗口。
  - `/base/intraday_rtn_var_up` 应默认选中“原始”。
  - `/factor/nope` 和 `/base/nope` 应显示错误卡片。
- [ ] **Step 5: 提交** `feat(web-ui): base factor home page with prep tabs and window buttons`

### Task 6: 文档与验证

**Files:**
- Modify: `README.md` 的 Web 工作台一节（看板改为原始因子、因子主页、`[web.board]` 配置）
- Scratch：`<scratchpad>/verify/settings.toml`（复制参考配置，改端口和路径）

- [ ] **Step 1: 更新 README**，并在 `docs/TODO.md` 里勾掉或补充相关条目（如果有）。
- [ ] **Step 2: 完整测试**：`… -m pytest -q` → 全部 PASS（失败的话先确认在本分支开始前是否已经失败）。
- [ ] **Step 3: 构建**：`cd web && npm run build` → 成功。
- [ ] **Step 4: 启动验证服务**，监听 `100.119.175.111`，使用未被占用的端口（例如 8631；不用 8600、8611、8621）。配置里 `evaluations_dir`、`state_dir`、`cache_dir` 指向 scratchpad，`db_path` 用 duckdb 的拷贝。命令：`main.py --config <scratch>/settings.toml serve --host 100.119.175.111 --port 8631`，后台运行。调度器会启动，但 `state_dir` 是全新的，只要不在页面上点“评估”就不会跑任务；截图时不点评估按钮。
- [ ] **Step 5: 截图**：看板、`daily_return` 主页、`log_total_market_cap` 主页、`intraday_rtn_var_up` 主页、窄屏看板。截图发给用户。
- [ ] **Step 6: 提交** README（是否提交代码由用户决定；如果用户还没说，先问）。
