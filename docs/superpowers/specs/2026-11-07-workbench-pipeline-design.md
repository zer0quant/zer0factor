# 工作台流程化：在网页上构建、评估、跟踪任务

日期：2026-11-07
状态：待用户确认

## 1. 意图

工作台目前只读，只能看评估结果。研究流程里的其他步骤（算原始因子、预处理、发起评估、预热缓存、刷新看板）都要敲命令、临时写 toml、盯 `logs/factor.log`。

本轮目标：在网页上**发起和跟踪**这些步骤，评估跑完结果自动出现在看板上。

更长远的方向：以后新因子主要来自论文，由 agent 从论文中提取因子、写出因子族代码，然后直接构建。本轮**不做 agent**，但要打好它需要的地基：

- 一套网页和 agent 共用的**任务接口与任务队列**；
- 一个**自动发现因子族**的机制，agent 新写的族放进 zer0alpha 后，不需要任何登记就会出现；
- 因子族可以声明**来源信息**（论文、公式）。

## 2. 目标、非目标、反目标

**目标（本轮）**

- P0 任务系统：后台执行、状态持久化、实时日志、进度、取消、按原参数重跑；重启网页服务不中断正在跑的任务。
- P0 发起评估：“新建评估”抽屉，可以从看板勾选、对比篮、详情页“重新评估”打开；评估成功后自动预热，并刷新看板。
- P1 因子族：自动发现因子族（内置 + 扫描包 + 兼容旧的显式登记）；“因子族”页列出全部族，可以发起构建（原始计算 / 预处理 / 全部），构建完可以一键接着评估。

**非目标（本轮不做，留给后续）**

- 从论文提取因子的 agent（下一阶段）。
- 在网页上写因子公式或编辑 Python 代码。
- 数据体检（覆盖率、缺失率、每日股票数）、在网页上标记因子的启用/观察/淘汰、同一因子不同设定的并排对比、合成与组合回测、增量更新。
- 鉴权。网络里只有用户自己的设备，见第 7 节。

**反目标（即使能跑起来，出现这些也算失败）**

- 改动 `zer0factor/eval/` 下的指标定义和计算口径。网页跑出来的结果必须和 CLI 跑出来的完全一致。
- 网页服务因为某个任务或某个因子族的代码出错而卡死或崩溃。
- 同一个任务被重复执行（例如一个批量评估被跑两遍）。
- 和交易系统共用资源，例如 `zer0qmt-redis`。

## 3. 约束

- 单机、单用户。机器有 128 核、251GB 内存，但上面还在跑其他服务和评估。一次批量评估大约占 2.4GB 内存，耗时几十分钟到一小时以上。
- 现有 CLI 是行为的唯一标准，任务就是去执行这些 CLI 命令。
- 旧 run（如 20260614_135227）的 summary 是旧口径，多头指标和分组表对不上，这不是 UI 的 bug，不需要处理。
- 前端沿用 React + antd + ECharts + react-query，后端沿用 FastAPI，不引入新的重依赖。

## 4. 考虑过的方案（任务执行方式）

| 方案 | 做法 | 取舍 |
|---|---|---|
| **A. 网页服务拉起独立子进程（选定）** | 每个任务由一个包装进程执行对应的 CLI 命令。包装进程和网页服务脱离（新会话），自己把状态写进 SQLite 任务表，日志写进文件。网页服务里有一个调度线程，负责从队列中取任务、启动包装进程。 | 评估代码一行不改；进程隔离；重启网页服务不影响正在跑的任务。代价是进度只能靠解析日志得到（因子级粒度），网页服务停着时排队的任务不会开始。 |
| B. 独立常驻 worker 进程 | 网页只写队列，`main.py worker` 负责取任务执行 | 网页服务停了队列也照样推进，但要多守护一个进程，单人使用时收益不大。 |
| C. Celery + Redis | 标准分布式任务队列 | 多队列和任务编排对以后的 agent 有用。但 Celery 的 prefork worker 是 daemon 进程，不能再起进程池（评估 `workers>1` 要用），所以仍然得用子进程执行 CLI；Redis 默认会把超过 1 小时的任务重新投递；结果会过期，任务历史还是要自己存。还要多维护一个专用 Redis。 |

用户的决定：**这一轮用方案 A**。任务表按“以后可以把调度层换成 Celery”的方式设计：字段里单独记录 `queue`（heavy/light，以后加 llm）和 `kind`，调度逻辑集中在一个模块里。

## 5. 已定的设计

### 5.1 任务系统

**存储**
- SQLite：`<state_dir>/workbench.db`。`state_dir` 新增配置项 `[web] state_dir`，默认值为 `data/workbench`，加入 gitignore。
- 每个任务的日志：`<state_dir>/logs/<task_id>.log`。

**任务表字段（`tasks`）**

| 字段 | 说明 |
|---|---|
| `id` | 形如 `t_20261107_213001_ab12` |
| `kind` | `evaluate` / `build` / `base` / `warm` |
| `queue` | `heavy` / `light` |
| `title` | 人可读的标题 |
| `params` | JSON，表单原始参数 |
| `argv` | JSON，实际执行的 CLI 参数 |
| `status` | `queued` / `running` / `succeeded` / `failed` / `cancelled` / `lost` |
| 时间戳 | `created_at`、`started_at`、`finished_at` |
| `pid`、`exit_code` | |
| `progress_done`、`progress_total` | |
| `run_id` | 评估产出的 run |
| `parent_id` | 例如预热任务指向它的评估任务；以后 agent 的任务链也用这个字段 |
| `error` | 最后若干行报错 |
| `source` | `web` / `agent` / `cli` |

**执行方式**
- 调度线程：在网页服务进程内运行，每 2 秒检查一次。只要 heavy 队列里在跑的任务数小于上限（默认 1），就按创建时间取最早的 queued 任务启动；light 队列的上限默认是 2。上限可以在 `[web.tasks]` 里配置。认领任务用 `UPDATE ... WHERE status='queued'` 的原子更新完成，避免同一个任务被启动两次。
- 包装进程：`python -m zer0factor.jobs.runner <task_id>`，以 `start_new_session=True` 启动，所以它是一个独立进程组的组长。它负责：
  1. 把状态写成 running，记录 pid；
  2. 用同一个解释器、带绝对路径的 `--config` 执行 `main.py <argv>`，stdout 和 stderr 合并写进日志文件；
  3. 一边执行一边解析日志，更新进度；
  4. 结束时写入退出码和最终状态；
  5. 对于评估任务，成功后自动插入一个 warm 子任务（`parent_id` 指向自己）。
- 取消：网页对进程组发 SIGTERM，10 秒后仍未退出就发 SIGKILL。包装进程捕获 SIGTERM 后把状态写成 cancelled。对评估任务，还要在 run 目录下写一个 `.cancelled` 标记文件。`scan_runs` 会跳过带这个标记的目录，也跳过还在运行的任务对应的目录。
- 重启恢复：网页服务启动时，检查所有 status 为 running 的任务的 pid，并核对该进程的命令行里包含这个 task_id。进程还在的就保持原状态（它自己会写完最后的状态）；进程已经不在的，标记为 `lost`。
- 失败：不自动重试，提供“用相同参数重跑”按钮，会新建一个任务并复制原任务的 params。

**评估的 run_id**
- 给 `evaluate-factors` 增加 `--run-id` 参数。这个参数会传给已有的 `EvaluationService.run(run_id=...)`，只改 CLI，不改评估逻辑。
- 任务创建时就预先确定 run_id，这样在运行过程中就能知道它对应哪个 run 目录，也避免了同一秒启动两个评估时 run 目录重名的问题。

**输出目录与路径**
- 评估任务的 argv 必须显式传入 `--output-dir <cfg.web.evaluations_dir>`。
- 原因：CLI 的默认值是相对路径 `data/evaluations`，而 settings 里 `web.evaluations_dir` 可能是另一个绝对路径（当前环境就是）。不显式指定的话，结果会写到看板扫描不到的地方。
- 子进程的 cwd 设为网页服务的 cwd，`--config` 传绝对路径。

**看不到的外部任务**
- 在命令行直接启动的任务不在任务表里，并发上限不会把它们算进去。
- 任务页顶部用一行提示说明这一点；本轮不去探测外部进程。

**进度解析**

| 任务类型 | 进度来源 |
|---|---|
| evaluate | 统计 `evaluation_factor_finished` 的行数，总数是因子数 |
| warm | 统计 `ok ` / `fail ` 开头的行数，总数是 run 中的因子数 |
| build / base | 不显示百分比，显示“运行中 + 最新一行日志” |

**刷新看板**
- 调度线程发现 evaluate 或 warm 任务进入终态后，重建 catalog，并清空相关性缓存（和 `/api/refresh` 做的事情一样）。
- 前端轮询任务时，如果看到有任务新完成，就让 meta、factors、curves 这几个查询失效，并弹出提示。

**接口**

| 接口 | 用途 |
|---|---|
| `GET /api/tasks?status=&kind=&limit=` | 任务列表 |
| `GET /api/tasks/{id}` | 任务详情 |
| `GET /api/tasks/{id}/log?offset=` | 返回 `{text, offset, done}`，单次最多返回 256KB |
| `POST /api/tasks` | 请求体为 `{kind, params}`，后端用 pydantic 校验并生成 argv，返回任务 |
| `POST /api/tasks/{id}/cancel` | 取消 |
| `POST /api/tasks/{id}/retry` | 按相同参数重跑 |
| `GET /api/eval/options` | 返回标准设定、各参数的默认值、可选股票池（读 `zer0share/data/stock/universe/name=*`）、可选收益口径 |

agent 以后就调用这一套接口，请求里带上 `source=agent`。

### 5.2 发起评估

**“新建评估”抽屉的入口**
- 看板上勾选因子后的操作栏；
- 对比篮；
- 详情页的“重新评估”按钮（会带上当前 run 的参数）；
- 因子族页构建完成后的“接着评估”。

**抽屉里的表单**
- 因子列表：可以增删，支持粘贴多个名字。
- 顶部有“标准设定”开关，默认打开。打开时，起始日、分组数、收益口径、股票池锁定为 `[web.standard]` 的值，结束日留空（表示最新），持有期中必须包含标准持有期。
- 其余参数的默认值和 CLI 一致：持有期 1,5,10、max_loss 0.35、成本 10bps、workers 1；可选填写基准指数。
- 因子数大于 1 时，提示可以把 workers 调大。

**提交之后**
- 提交后生成一个 evaluate 任务，界面跳到该任务的详情页。
- 不按标准设定跑出来的结果不进看板主表，只出现在详情页的 run 列表里。

### 5.3 因子族自动发现

**配置**

```toml
[families]
packages = ["zer0alpha.factors"]   # 扫描这些包的子模块
```

原有的 `[external_families]` 继续兼容，可以用来补充包外的单个族。内置的 `rolling_return` 保留。

**发现规则**
- 遍历包内的子模块，跳过以 `_` 开头的模块。
- 模块级属性 `FAMILY` 是 `FactorFamily` 实例的，就算一个因子族。
- 没有 `FAMILY` 的模块（如 `ff3_returns`、`ff3_exposures`）直接跳过，不算错误。
- 以下情况作为“坏族”列出，并附上报错信息：import 报错、`FAMILY` 不是 `FactorFamily`、族名重复。

**CLI**
- 新命令 `main.py families --json`：输出每个族的 name、module、来源（builtin / package / explicit）、base_factors、windows、profiles、原始因子数、输出因子数、uses_data_provider、可选的 `SOURCE` 元数据，以及 error。
- `build-factors --family` 和 `analyze-evaluation --family` 改用同一套发现逻辑。

**网页**
- 网页服务**不在自己的进程里 import 因子族模块**，而是用子进程执行 `families --json`，把结果缓存起来。“重新扫描”按钮会重新执行一次。这样既隔离了坏代码，也能看到 zer0alpha 刚改过的代码。

**族的管理状态**
- 存在 `workbench.db` 的 `families` 表里，字段有 name、status（`enabled` / `archived`）、note、first_seen。
- 新发现的族**默认就是 enabled**。first_seen 在 7 天以内的显示一个“新”标签。
- 归档的族默认隐藏，已有的数据和评估结果都保留，CLI 照样可以构建它。

**来源信息**
- 族模块可以选择性地声明 `SOURCE = {"paper": ..., "url": ..., "formula": ..., "notes": ...}`，因子族页会显示出来。这是给以后的论文 agent 预留的。

### 5.4 因子族页

- **列表**：族名、来源模块、状态、输出因子数、`data/factors` 下已有的因子数（只检查目录是否存在，不统计行数）、数据截至日（取最新的 `date=` 分区，结果缓存）、最近一次构建任务及其状态。
- **展开某个族**：显示 base_factors × windows × profiles 的因子清单，每个因子标出是否已经算过，并链接到该因子的详情页。
- **操作**：
  - 构建，可选原始计算 / 预处理 / 全部，可填起止日、workers、是否登记进 registry，生成 build 任务；
  - “接着评估”：打开新建评估抽屉，因子列表预先填好该族已算好的输出因子；
  - 归档 / 恢复；
  - 填写备注。
- **页面顶部“基础因子”区**：`compute-returns` 和 `compute-market-cap` 两个按钮，生成 base 任务。

### 5.5 页面组织

- 顶部导航从“看板 · 对比”扩展为“看板 · 对比 · 因子族 · 任务”。
- 标题栏有一个运行中任务数的角标，点开是最近 5 个任务的弹层。
- **任务页（`/tasks`、`/tasks/:id`）**：
  - 左边是任务列表，可按状态和类型筛选；
  - 右边是任务详情：参数、进度条、实时日志（每 2 秒轮询一次，默认自动滚到底，往上翻时暂停自动滚动），以及取消、重跑按钮；
  - 评估任务完成后显示“查看结果”，链接到对应因子的详情页并带上 run_id。
- **确认弹窗**：取消任务、批量评估（因子数 > 20 或 workers > 8）、构建“全部”时，提交前弹窗确认，并写明预计的影响。

## 6. 数据读写一览

| 步骤 | 读 | 写 |
|---|---|---|
| base / build raw | zer0share | `data/factors/<factor>` |
| build preprocess | `data/factors`、zer0share（股票池、行业） | `data/factors/z_*`，可选写 `config/factors.toml` |
| evaluate | `data/factors`、zer0share | `data/evaluations/<run_id>` |
| warm | `data/evaluations/<run_id>` | `data/web_cache` |
| 任务系统 | — | `data/workbench/` |

## 7. 安全

- 网络里只有用户自己的设备，用户决定**本轮不加鉴权**。
- 只用第 5.5 节的确认弹窗防止误操作。
- 写接口只接受结构化参数，argv 由后端拼出来，不接受任意命令或路径，因子名和族名都要和已知清单比对。
- 如果以后要开放给 agent 之外的人访问，再加 token。

## 8. 验证方式

- 自动化测试用假命令代替真实的 CLI，**不在测试里真跑构建或评估**。构建会写共享的 `data/factors`。
- 截图验证时，服务另选端口（不用 8611），配置里的 `evaluations_dir` 和 `state_dir` 指向 scratchpad。
- 如果要真跑一次小评估来做端到端验证（只读 `data/factors`，结果写到 scratchpad），**先征得用户同意**，因为主目录可能正在跑评估。

## 9. 留给实现者决定的

- 前端组件怎么拆、样式细节，沿用现有的 `index.css` 和主题。
- SQLite 的访问方式：标准库 `sqlite3` 加 WAL 模式即可。
- `families --json` 的缓存失效策略，例如保存时记录 zer0alpha 目录的 mtime。
- 测试：任务存储、调度认领、包装进程（用一个假命令测）、取消和恢复、发现逻辑（用测试用的假包）、各个 API 都要有 pytest。前端用 `npm run build` 和截图验证。
