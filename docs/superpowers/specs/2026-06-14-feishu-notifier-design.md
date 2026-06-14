# Feishu Notifier 设计文档

**日期**: 2026-06-14  
**项目**: zer0factor  
**状态**: 已批准，待实现

---

## 背景

zer0factor 的预处理（`build-factors`）和评估（`evaluate-batch`）任务耗时较长，目前运行期间没有任何外部通知。参考 zer0alpha 的企业微信通知实现，在 zer0factor 中加入飞书富文本卡片通知。

---

## 目标

- 预处理（raw / preprocess）和评估（evaluate-batch）的关键节点（开始、进度、完成、出错）发送飞书通知
- 消息使用飞书 Interactive Card（富文本卡片），支持颜色区分状态
- 未配置 webhook 时完全静默，不影响正常流程
- 良好的 OOP 设计：职责清晰，可测试，改动范围小

---

## 模块结构

```
zer0factor/
└── notify/
    ├── __init__.py       # 导出 FeishuNotifier, NullNotifier, load_notifier
    ├── feishu.py         # FeishuNotifier + 卡片构建
    └── null.py           # NullNotifier（全部 no-op）
```

### `load_notifier(config: Config) -> FeishuNotifier | NullNotifier`

工厂函数，读 `config.notify_webhook_url`：
- 有值 → 返回 `FeishuNotifier(webhook_url)`
- 空值 → 返回 `NullNotifier()`

`main.py` 只调用这一个函数，无需在 CLI 层做分支判断。

---

## 配置

`config/settings.toml` 增加：

```toml
[notify]
webhook_url = ""   # 空字符串 = 关闭通知；填入飞书 Webhook URL 即启用
```

`Config` dataclass（`zer0factor/config.py`）增加字段：

```python
notify_webhook_url: str  # 空字符串表示未配置
```

---

## 类设计

### `NullNotifier`（`notify/null.py`）

5 个方法全部 `pass`，签名与 `FeishuNotifier` 完全一致，无任何状态，用于未配置通知时和测试场景。

### `FeishuNotifier`（`notify/feishu.py`）

```python
class FeishuNotifier:
    def __init__(self, webhook_url: str, *, app: str = "zer0factor") -> None:
        # app 作为卡片标题前缀

    # --- 公开方法（与 NullNotifier 签名一致）---

    def notify_start(self, stage: str, details: dict[str, str] | None = None) -> None:
        # 橙色卡片，标题 "[app] `stage` 开始运行 ⏳"
        # details 渲染为字段列表（如 因子数、workers）

    def notify_done(self, stage: str, rows: dict[str, int], elapsed: float) -> None:
        # 绿色卡片，标题 "[app] `stage` 完成 ✅"
        # 字段：因子数、总行数、耗时

    def notify_eval_done(
        self, stage: str, run_id: str, factor_count: int, elapsed: float
    ) -> None:
        # 绿色卡片，标题 "[app] `stage` 完成 ✅"
        # 字段：run_id、因子数、耗时

    def notify_progress(self, stage: str, done: int, total: int) -> None:
        # 蓝色卡片，标题 "[app] `stage` 进度 XX%"
        # 字段：已完成、总数

    def notify_error(self, stage: str, exc: Exception) -> None:
        # 红色卡片，标题 "[app] `stage` 出错 ❌"
        # 字段：异常类型、异常信息

    # --- 私有方法 ---

    def _build_card(
        self, title: str, color: str, fields: list[tuple[str, str]]
    ) -> dict:
        # 构造飞书 Interactive Card JSON
        # color 取值：green / red / orange / blue
        # fields 渲染为两列短字段（lark_md 格式）

    def _send(self, card: dict) -> None:
        # urllib.request.urlopen，timeout=10，异常静默忽略
```

**卡片 JSON 结构**（`msg_type: "interactive"`）：

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {"tag": "plain_text", "content": "[zer0factor] `preprocess` 完成 ✅"},
      "template": "green"
    },
    "elements": [
      {
        "tag": "div",
        "fields": [
          {"is_short": true, "text": {"tag": "lark_md", "content": "**因子数**\n40"}},
          {"is_short": true, "text": {"tag": "lark_md", "content": "**耗时**\n23.4s"}}
        ]
      }
    ]
  }
}
```

**颜色映射**：

| 状态 | color |
|------|-------|
| 开始 / 进度 | `orange` / `blue` |
| 完成 | `green` |
| 出错 | `red` |

---

## Pipeline 集成点

### `zer0factor/pipeline.py` — `run_build_stage()`

新增参数：`notifier: FeishuNotifier | NullNotifier | None = None`

| 时机 | 调用 |
|------|------|
| 进入 raw 阶段前 | `notify_start("raw")` |
| raw 完成后 | `notify_done("raw", rows, elapsed)` |
| 进入 preprocess 阶段前 | `notify_start("preprocess")` |
| preprocess 完成后 | `notify_done("preprocess", rows, elapsed)` |
| 任意阶段抛异常 | `notify_error(stage, exc)`，异常继续向上抛 |

### `zer0factor/eval/pipeline.py` — batch 评估入口

新增参数：`notifier: FeishuNotifier | NullNotifier | None = None`

| 时机 | 调用 |
|------|------|
| 评估开始前 | `notify_start("evaluate", details={"因子数": str(n), "workers": str(w)})` |
| 完成 25% / 50% / 75% | `notify_progress("evaluate", done, total)` |
| 全部完成后 | `notify_eval_done("evaluate", run_id, count, elapsed)` |
| 出错时 | `notify_error("evaluate", exc)` |

进度里程碑逻辑封装在 eval pipeline 内部，调用侧不感知。

### `main.py`

在各 CLI 命令入口处统一构造，传入各 pipeline 函数：

```python
cfg = load_config()
notifier = load_notifier(cfg)
run_build_stage(..., notifier=notifier)
```

---

## 不在本次范围内

- 抽象基类 / Protocol（YAGNI，目前只有飞书一个渠道）
- 重试机制（网络异常静默忽略即可）
- 消息队列 / 异步发送
- 其他渠道（企业微信、邮件）
