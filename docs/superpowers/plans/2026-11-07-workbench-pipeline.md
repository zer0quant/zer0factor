# 工作台流程化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 在网页上发起和跟踪构建、评估、预热任务，自动发现因子族，评估完成后结果自动进入看板。

**Architecture：** 网页服务里有一个调度线程，从 SQLite 任务表里取任务，用 `python -m zer0factor.jobs.runner <task_id>` 拉起独立进程组。runner 执行现有的 CLI，把日志和进度写回任务表。因子族发现由 CLI `families --json` 在子进程里完成，网页服务不 import 因子族代码。

**Tech Stack：** Python 3 / FastAPI / sqlite3 / pydantic；React 18 + antd 5 + react-query + ECharts。

**Spec：** `docs/superpowers/specs/2026-11-07-workbench-pipeline-design.md`

## Global Constraints

- 不改 `zer0factor/eval/` 下的指标定义和计算口径；评估行为以 CLI 为准。
- 任务状态取值：`queued` `running` `succeeded` `failed` `cancelled` `lost`。
- 任务类型和队列：`evaluate`、`build`、`base` 走 `heavy` 队列；`warm` 走 `light` 队列。heavy 默认上限为 1，light 默认上限为 2。
- 状态目录：`[web] state_dir`，默认 `data/workbench`，库文件为 `workbench.db`，日志放在 `logs/<task_id>.log`。
- 评估任务一律带上 `--output-dir <cfg.web.evaluations_dir>` 和 `--run-id <预分配的 id>`。
- 新发现的因子族默认是 `enabled`；first_seen 在 7 天以内的显示“新”标签。
- 写接口只接受结构化参数：因子名必须是 `data/factors` 下已有的，族名必须是已发现的。
- 测试里不真跑构建或评估，用假命令代替。
- 测试命令：`/data/projects/zer0quant/zer0factor/.venv/bin/python -m pytest -q`；前端构建命令：`cd web && npm run build`。
- commit 不加 Co-Authored-By，不 push。

## Review Focus

1. 网页服务在任务运行中重启：重启后任务仍显示 running，最终状态由 runner 写入，不会被误判成 lost。（Task 3：pid 存活且命令行匹配时保持 running 的测试）
2. 同一时刻两次 tick：同一个 queued 任务只会被启动一次。（Task 1：claim_next 原子认领测试）
3. 取消一个正在运行的评估：子进程树全部退出，状态为 cancelled，run 目录里有 `.cancelled`，看板扫描时跳过它。（Task 2 和 Task 3）
4. 任务日志很大（几十 MB）时，日志接口按偏移量分段返回，单次不超过 256KB。（Task 4）
5. 某个因子族模块 import 报错：其他族照常列出，坏族带 error 信息。（Task 5）

---

### Task 1：任务存储 TaskStore

**Files：**
- Create：`zer0factor/jobs/__init__.py`、`zer0factor/jobs/store.py`
- Modify：`zer0factor/config.py`（WebConfig 增加 `state_dir: Path = Path("data/workbench")`、`heavy_slots: int = 1`、`light_slots: int = 2`，解析 `[web] state_dir` 和 `[web.tasks] heavy_slots/light_slots`；Config 增加 `family_packages: tuple[str, ...] = ()`，解析 `[families] packages`）、`.gitignore`（加入 `data/workbench/`）、`config/settings.example.toml`
- Test：`tests/jobs/test_store.py`、`tests/test_config.py`

**Interfaces：**
- Produces：
  - `TaskStore(db_path: Path)`：WAL 模式，每次调用开一个短连接。
  - `create(*, kind, queue, title, params: dict, command: list[str], cwd: str, run_id: str|None=None, parent_id: str|None=None, source="web") -> dict`
  - `get(id) -> dict|None`
  - `list(*, status: list[str]|None=None, kind: str|None=None, limit=200) -> list[dict]`，按 created_at 倒序。
  - `claim_next(queue) -> dict|None`：把最早的 queued 任务原子地改成 `running`（pid 先为空）。
  - `set_pid(id, pid)`
  - `set_progress(id, done, total|None, last_line: str|None)`
  - `finish(id, status, exit_code: int|None, error: str|None)`：只在当前状态不是终态时才写入。
  - `count_running(queue) -> int`
  - `log_path(id) -> Path`
  - `family_states() -> dict[name, {status, note, first_seen}]`
  - `touch_families(names) -> None`：首次见到的族写入 enabled 和当前时间。
  - `set_family(name, *, status=None, note=None)`
  - 任务 dict 的键：`id kind queue title params command cwd status created_at started_at finished_at pid exit_code progress_done progress_total last_line run_id parent_id error source`；时间用 ISO 字符串。
  - `new_task_id() -> str`，格式为 `t_YYYYMMDD_HHMMSS_xxxx`。

- [ ] 写测试：`test_create_and_get_roundtrip`（params 和 command 存的是 JSON，取回后等于原值，status 为 queued）、`test_claim_next_is_fifo_and_atomic`（两个任务；连续 claim 两次分别得到 t1、t2，第三次得到 None；两个 store 实例对同一个库并发 claim，不会拿到同一个任务）、`test_finish_does_not_override_terminal`（先 finish 成 cancelled，再 finish 成 failed，结果仍是 cancelled）、`test_family_states_default_enabled`（touch 之后 status 为 enabled；set_family 设成 archived 后再 touch，仍是 archived）、`test_list_filters_by_status_and_kind`；config 测试：`test_parse_web_state_dir_and_slots`、`test_parse_family_packages`。
- [ ] 运行测试，确认失败；实现；运行测试，确认通过。
- [ ] 提交：`feat(jobs): sqlite task store and workbench config`

### Task 2：任务参数校验与 runner

**Files：**
- Create：`zer0factor/jobs/specs.py`、`zer0factor/jobs/progress.py`、`zer0factor/jobs/runner.py`
- Modify：`zer0factor/cli/evaluate_cmds.py`（`evaluate-factors` 增加 `--run-id`，并传给 `EvaluationService.run(run_id=...)`；`_run_evaluation_job` 和 `_run_evaluation_request` 增加 `run_id` 参数）
- Test：`tests/jobs/test_specs.py`、`tests/jobs/test_runner.py`、`tests/test_cli.py`

**Interfaces：**
- Consumes：Task 1 的 TaskStore。
- Produces：
  - pydantic 模型：
    - `EvaluateParams(factors: list[str] 1..500, start_date: str="20160101", end_date: str|None=None, periods: list[int]=[1,5,10], quantiles: int 2..50 = 10, return_type: Literal["open_t1","close_t0"]="open_t1", universe: str|None=None, max_loss: float=0.35, transaction_cost_bps: float=10.0, benchmark_index: str|None=None, workers: int 1..64 = 1)`
    - `BuildParams(family: str, stage: Literal["raw","preprocess","all"]="all", start_date: str|None=None, end_date: str|None=None, workers: int 1..64 = 1, update_registry: bool=False)`
    - `BaseParams(target: Literal["returns","market_cap"])`
    - `WarmParams(run_id: str, workers: int 1..32 = 8)`
    - 日期必须是 8 位数字；universe、benchmark 只允许 `[A-Za-z0-9_.]`。
  - `TaskSpec` 数据类：`kind queue title params command run_id`。
  - `build_spec(kind: str, raw: dict, *, cfg: Config, config_path: Path, known_factors: set[str], known_families: set[str], known_runs: set[str]) -> TaskSpec`：参数不合法时抛 `SpecError(msg)`。command 为 `[sys.executable, <repo>/main.py, "--config", str(config_path.resolve()), <子命令...>]`。evaluate 的 command 带上 `--output-dir str(cfg.web.evaluations_dir.resolve())` 和 `--run-id`，run_id 由 `datetime.now().strftime("%Y%m%d_%H%M%S")` 生成，与 `known_runs` 冲突时加 `_2`、`_3`。
  - `class Progress`：`feed(line) -> bool`，返回是否有变化；属性 `done`、`total`、`last_line`。规则：evaluate 统计包含 `evaluation_factor_finished` 的行，total 为因子数；warm 统计以 `ok ` 或 `fail ` 开头的行，total 为 run 中的因子数（由 spec 时传入）；其他类型只更新 last_line。
  - `runner.main(task_id: str, db_path: str) -> int`：
    1. 设 pid；
    2. 用 `Popen(command, cwd=cwd, stdout=PIPE, stderr=STDOUT, text=True, bufsize=1)` 启动子进程；
    3. 逐行写日志文件并调用 Progress.feed，每秒最多写一次进度；
    4. 收到 SIGTERM 时向子进程转发 SIGTERM，等待 10 秒，必要时 SIGKILL；对带 run_id 的任务，在 `<evaluations_dir>/<run_id>/` 存在时写 `.cancelled`；最终状态为 cancelled；
    5. 退出码为 0 时状态为 succeeded，否则为 failed，error 取日志最后 20 行；
    6. evaluate 成功后创建 warm 子任务（parent_id 指向本任务，source 继承本任务）。warm 子任务需要的 command 由 `build_spec` 生成，所以 runner 用 `load_config` 读取 command 里的 `--config` 路径。
  - 入口：`python -m zer0factor.jobs.runner <task_id> <db_path>`。

- [ ] 写测试：
  - `test_evaluate_spec_builds_cli_argv`：断言 command 包含 `evaluate-factors fa fb --start-date 20160101 --periods 1,5,10 --quantiles 10 --return-type open_t1 --max-loss 0.35 --transaction-cost-bps 10.0 --output-dir <abs> --run-id <id>`，queue 为 heavy。
  - `test_spec_rejects_unknown_factor_and_bad_date`
  - `test_build_spec_requires_known_family`
  - `test_run_id_avoids_existing`
  - `test_progress_counts_evaluate_lines`
  - `test_runner_success_writes_log_and_status`：command 为 `python -c` 打印 3 行 `evaluation_factor_finished`；结束后状态为 succeeded，进度为 3/3，日志里有这 3 行，并生成了一个 warm 子任务。
  - `test_runner_failure_captures_tail`：exit 3 时状态为 failed，exit_code 为 3，error 包含最后一行输出。
  - `test_runner_cancel_kills_child_and_marks_run`：command 为 sleep 60，并预先建好 run 目录；对 runner 进程组发 SIGTERM 后，状态为 cancelled，存在 `.cancelled`，子进程已经退出。
  - CLI 测试：`test_evaluate_factors_passes_run_id`（monkeypatch EvaluationService，断言收到 `run_id="r1"`）。
- [ ] 运行测试，确认失败；实现；运行测试，确认通过。
- [ ] 提交：`feat(jobs): task specs, progress parsing and detached runner`

### Task 3：调度器

**Files：**
- Create：`zer0factor/jobs/scheduler.py`
- Test：`tests/jobs/test_scheduler.py`

**Interfaces：**
- Consumes：TaskStore，runner 入口。
- Produces：
  - `Scheduler(store, *, slots: dict[str,int], spawn: Callable[[dict], int] | None = None, on_finished: Callable[[dict], None] | None = None)`。默认的 spawn 用 `Popen([sys.executable, "-m", "zer0factor.jobs.runner", id, db], start_new_session=True, cwd=task.cwd, stdout/stderr=DEVNULL)`，返回 pid。
  - `tick()`，按顺序做三件事：
    1. reconcile：对 status 为 running 的任务，如果 pid 不为空，且进程已死或 `/proc/<pid>/cmdline` 里不含 task_id，就 `finish(lost)`；如果 pid 为空且 started_at 已超过 30 秒，也记为 lost。
    2. 对上次 tick 之后进入终态的任务调用 on_finished。用“已通知集合”来判断，启动时把已经是终态的任务都放进这个集合。
    3. 每个队列在 `count_running < slots` 时调用 `claim_next` 并 spawn，然后 `set_pid`。
  - `cancel(id) -> dict`：queued 的直接 `finish(cancelled)`；running 的对其进程组发 SIGTERM（`os.killpg`）；终态的原样返回。
  - `start(interval=2.0)` / `stop()`：后台 daemon 线程。

- [ ] 写测试：
  - `test_tick_respects_slots`：3 个 heavy 任务、1 个 light，spawn 用假函数；一次 tick 后 heavy 只启动了 1 个，light 启动了 1 个。
  - `test_reconcile_marks_dead_pid_lost`：用一个已退出进程的 pid。
  - `test_reconcile_keeps_live_runner`：用一个真实的 `python -c "import time,sys; time.sleep(30)" <task_id>` 子进程作为 pid，tick 后仍是 running。
  - `test_on_finished_called_once`
  - `test_cancel_queued`
- [ ] 运行测试，确认失败；实现；运行测试，确认通过。
- [ ] 提交：`feat(jobs): scheduler with slots, recovery and cancel`

### Task 4：任务与评估 API，并接入看板刷新

**Files：**
- Modify：`zer0factor/web/app.py`（`create_app(cfg, static_dir=None, *, config_path: Path|None=None, scheduler: bool=True)`）、`zer0factor/web/runs.py`（`scan_runs(evaluations_dir, exclude: set[str] = frozenset())`，跳过带 `.cancelled` 的目录和 exclude 中的目录）、`zer0factor/web/catalog.py`（`build_catalog(cfg, exclude_runs=frozenset())`）、`zer0factor/cli/web_cmds.py`（serve 传入 config_path）
- Test：`tests/web/test_tasks_api.py`、`tests/web/test_runs.py`

**Interfaces：**
- Consumes：Task 1～3。
- Produces（接口，返回 JSON）：
  - `GET /api/tasks?status=a,b&kind=&limit=` → `{tasks: [...], running: n, queued: n}`
  - `GET /api/tasks/{id}` → 任务 dict，找不到返回 404。
  - `GET /api/tasks/{id}/log?offset=0` → `{text, offset, size, done}`，单次最多 262144 字节；offset 超过文件大小时返回空 text。
  - `POST /api/tasks` 请求体 `{kind, params}` → 201 和任务 dict；`SpecError` 返回 422。
  - `POST /api/tasks/{id}/cancel`、`POST /api/tasks/{id}/retry` → 任务 dict。retry 会用原任务的 kind 和 params 重新 build_spec。
  - `GET /api/eval/options` → `{standard, defaults: EvaluateParams 默认值, universes: [...], return_types: ["open_t1","close_t0"]}`。universes 读取 `zer0share_data_dir/stock/universe/name=*`。
  - 任务进入终态时，on_finished 对 kind 为 evaluate 或 warm 的任务执行“重建 catalog（exclude 当前 running/queued 任务的 run_id）+ 清空相关性缓存 + 清空 sparklines”。`/api/refresh` 也用同样的 exclude。
  - `scheduler=False` 时不启动线程（测试用），测试可以通过 `app.state.scheduler.tick()` 手动推进。

- [ ] 写测试：
  - `test_create_evaluate_task_and_list`：返回 201，status 为 queued，command 里有 `--run-id`。
  - `test_create_rejects_unknown_factor_422`
  - `test_log_endpoint_offsets`：写一个 300KB 的日志；第一次取到 262144 字节，第二次取到剩余部分。
  - `test_cancel_queued_task`
  - `test_retry_copies_params`
  - `test_eval_options_lists_universes`
  - `test_finished_evaluate_refreshes_catalog`：spawn 用假函数；手动 finish(succeeded)，同时建一个新 run；tick 之后 `/api/meta` 里能看到这个新 run。
  - `test_scan_runs_skips_cancelled_and_excluded`
- [ ] 运行测试，确认失败；实现；运行测试，确认通过。
- [ ] 提交：`feat(web): task and evaluate APIs with auto refresh`

### Task 5：因子族自动发现与 API

**Files：**
- Create：`zer0factor/discovery.py`、`zer0factor/web/families.py`
- Modify：`zer0factor/factor_registry.py`（新增 `family_registry(cfg) -> FactorFamilyRegistry`，合并内置族、显式登记族和包扫描结果）、`zer0factor/cli/compute_cmds.py` 和 `zer0factor/cli/evaluate_cmds.py`（`build-factors` 和 `analyze-evaluation` 改用 `family_registry(cfg)`）、`zer0factor/cli/registry_cmds.py`（新命令 `families --json`）、`zer0factor/web/app.py`
- Test：`tests/test_discovery.py`、`tests/web/test_families_api.py`

**Interfaces：**
- Produces：
  - `DiscoveredFamily` 数据类：`name, module, origin: Literal["builtin","package","explicit"], family: FactorFamily|None, error: str|None`
  - `discover_families(builtins: Mapping[str,FactorFamily], packages: Iterable[str], explicit: Iterable[ExternalFamilySpec]) -> list[DiscoveredFamily]`。规则：遍历包内子模块，跳过以 `_` 开头的；没有 `FAMILY` 的跳过；`FAMILY` 不是 FactorFamily 的，记为 error；import 失败的，error 为异常的最后一行，name 用模块名；族名重复的，后出现的记为 error `duplicate family name ... (also in <module>)`。
  - `describe(d: DiscoveredFamily) -> dict`：键为 `name module origin error base_factors windows profiles raw_names outputs uses_data_provider source`。`outputs` 是 `all_factor_names()`，`source` 是模块的 `SOURCE`，没有时为 None。
  - CLI `families --json` 输出 `{"families": [describe...]}`。
  - `FamilyCatalog(cfg, config_path, store)`：`list(refresh=False) -> list[dict]`。在子进程里执行 CLI，超时 120 秒，结果缓存在内存里；把 store 里的 status、note、first_seen、`is_new` 合并进去，补上 `stored`（输出因子中在 factor_dir 下有目录的个数）、`stored_names`、`data_end`（第一个 raw 因子最新的 `date=` 分区）、`last_task`（该族最近一个 build 任务的 id 和 status）；对所有成功发现的族调用 `touch_families`。子进程本身失败时抛出带 stderr 的异常。
  - 接口：
    - `GET /api/families?refresh=0|1` → `{families: [...], scanned_at}`
    - `PATCH /api/families/{name}`，请求体 `{status?, note?}`
    - build_spec 的 `known_families` 来自 FamilyCatalog 中没有 error 的族名。

- [ ] 写测试：
  - `test_discover_package_families`：在 tmp_path 下建一个假包 `fakefam`，包含 `good.py`（含 FAMILY）、`_private.py`、`helper.py`（无 FAMILY）、`broken.py`（raise ImportError("boom")）、`dup.py`（族名和 good 相同），通过 monkeypatch 加入 sys.path。断言 good 正常；broken 的 error 含 boom；dup 的 error 含 duplicate；`_private` 和 `helper` 不出现。
  - `test_family_registry_resolves_package_family`
  - `test_families_cli_json`
  - `test_families_api_merges_state`：用一个返回固定 JSON 的 runner 替代子进程；断言新族 status 为 enabled、is_new 为 true；PATCH 成 archived 后再次 GET 仍是 archived；stored 计数正确。
- [ ] 运行测试，确认失败；实现；运行测试，确认通过。
- [ ] 提交：`feat: auto-discover factor families with workbench state`

### Task 6：前端

**Files：**
- Create：`web/src/pages/Tasks.tsx`、`web/src/pages/Families.tsx`、`web/src/components/EvaluateDrawer.tsx`（含 `EvaluateProvider` 和 `useEvaluate(): { open(factors: string[], preset?: Partial<EvaluateParams>) }`）、`web/src/components/TaskBadge.tsx`、`web/src/taskStatus.ts`（状态到中文和颜色的映射）
- Modify：`web/src/api.ts`、`web/src/types.ts`、`web/src/App.tsx`（菜单：因子看板 · 因子对比 · 因子族 · 任务；路由 `/families`、`/tasks`、`/tasks/:id`；标题栏 TaskBadge；包上 EvaluateProvider；任务进入终态时让 meta、factors、curves 失效并 `message.success`）、`web/src/components/CompareBar.tsx`（增加“评估”按钮）、`web/src/pages/FactorDetail.tsx`（“重新评估”按钮，preset 取当前 run 的参数）、`web/src/pages/Board.tsx`（如果有多选，就在批量操作区加“评估所选”）

**界面要求（来自 spec）：**
- 抽屉：
  - 因子列表用 Select tags 模式，支持粘贴逗号或空格分隔的名字；
  - “标准设定”开关默认打开，打开时锁定起始日、分组数、收益口径、股票池，结束日为空，持有期中必须包含标准持有期；
  - 其余参数沿用 options 返回的默认值；
  - 因子数大于 20 或 workers 大于 8 时，提交前用 Modal.confirm；
  - 提交成功后跳转到 `/tasks/<id>`。
- 任务页：
  - 左边是列表，可按状态和类型筛选，每 3 秒刷新一次；右边是详情；
  - 日志每 2 秒按 offset 增量拉取，默认自动滚到底，用户往上翻时暂停自动滚动；
  - 有进度条；取消前要确认；重跑；
  - evaluate 任务成功后显示“查看结果”，链接到 `/factor/<第一个因子>?run=<run_id>`；
  - 顶部提示“命令行直接启动的任务不在此列表中”。
- 因子族页：
  - 顶部是“基础因子”区，有 compute-returns 和 compute-market-cap 两个按钮（需要确认）；
  - 表格列：族名（带“新”标签和来源模块）、状态、输出数/已算数、数据截至、最近构建、操作（构建、接着评估、归档/恢复、备注）；
  - 展开行显示输出因子清单，已算的链接到详情页；
  - error 族标红并显示报错；
  - 有“重新扫描”按钮；
  - 默认隐藏 archived，可以用开关显示。
- TaskBadge：每 3 秒轮询 `status=running,queued`，显示运行中的数量，点开 Popover 显示最近 5 个任务。

- [ ] `cd web && npm run build` 通过。
- [ ] 提交：`feat(web-ui): tasks page, evaluate drawer and families page`

### Task 7：端到端验证与文档

- [ ] 完整运行 pytest，全部通过。
- [ ] 准备 scratchpad 版的 settings：evaluations_dir 和 state_dir 指向 scratchpad，factor_dir 指向主目录（只读）。在 8612 端口启动服务，用 playwright 截图：任务页（含一个用假命令跑完的任务、一个失败的任务）、新建评估抽屉、因子族页（真实扫描 zer0alpha）、标题栏角标。
- [ ] 如果要真跑小评估做端到端验证，先征得用户同意。
- [ ] README 的工作台部分补充：任务、因子族、`[families] packages` 配置、`state_dir`。
- [ ] 提交：`docs: workbench tasks and families usage`
