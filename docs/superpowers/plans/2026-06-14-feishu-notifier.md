# Feishu Notifier 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 zer0factor 的 preprocess 和 evaluate-batch 流程添加飞书富文本卡片通知。

**Architecture:** 新增 `zer0factor/notify/` 包，包含 `NullNotifier`（no-op）和 `FeishuNotifier`（发飞书卡片）；`load_notifier(config)` 工厂函数根据配置返回对应实例；pipeline 函数通过可选参数接收 notifier，`None` 时静默。

**Tech Stack:** Python 标准库 `urllib.request`（无新依赖），飞书 Webhook API（`msg_type: "interactive"` 卡片格式）

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 创建 | `zer0factor/notify/__init__.py` | 导出 FeishuNotifier, NullNotifier, load_notifier |
| 创建 | `zer0factor/notify/null.py` | NullNotifier（5 个空方法） |
| 创建 | `zer0factor/notify/feishu.py` | FeishuNotifier + 卡片构建 + HTTP 发送 |
| 创建 | `tests/notify/__init__.py` | 测试包 |
| 创建 | `tests/notify/test_null.py` | NullNotifier 测试 |
| 创建 | `tests/notify/test_feishu.py` | FeishuNotifier 测试 |
| 修改 | `zer0factor/config.py` | 增加 `notify_webhook_url: str` 字段 |
| 修改 | `config/settings.toml` | 增加 `[notify]` 节 |
| 修改 | `tests/test_config.py` | 补充 notify_webhook_url 测试 |
| 修改 | `zer0factor/pipeline.py` | `run_build_stage()` 加 notifier 参数 |
| 修改 | `zer0factor/eval/pipeline.py` | `evaluate_factors()` 加 notifier 参数 |
| 修改 | `main.py` | 构造 notifier 并传入 pipeline |

---

## Task 1: NullNotifier

**Files:**
- Create: `zer0factor/notify/null.py`
- Create: `zer0factor/notify/__init__.py`（空壳，Task 5 填充）
- Create: `tests/notify/__init__.py`
- Create: `tests/notify/test_null.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/notify/test_null.py
from zer0factor.notify.null import NullNotifier


def test_null_notifier_all_methods_are_no_ops():
    n = NullNotifier()
    # 所有方法调用不抛异常，返回 None
    assert n.notify_start("raw") is None
    assert n.notify_start("preprocess", details={"因子数": "40"}) is None
    assert n.notify_done("raw", {"factor_a": 100, "factor_b": 200}, 5.3) is None
    assert n.notify_eval_done("evaluate", "20260614_120000", 129, 87.3) is None
    assert n.notify_progress("evaluate", 32, 129) is None
    assert n.notify_error("raw", ValueError("boom")) is None
```

- [ ] **Step 2: 建目录和空包文件**

```bash
mkdir -p zer0factor/notify tests/notify
touch zer0factor/notify/__init__.py tests/notify/__init__.py
```

- [ ] **Step 3: 运行测试确认失败**

```bash
pytest tests/notify/test_null.py -v
```
预期：`ImportError: cannot import name 'NullNotifier'`

- [ ] **Step 4: 实现 NullNotifier**

```python
# zer0factor/notify/null.py
from __future__ import annotations


class NullNotifier:
    def notify_start(self, stage: str, details: dict[str, str] | None = None) -> None:
        pass

    def notify_done(self, stage: str, rows: dict[str, int], elapsed: float) -> None:
        pass

    def notify_eval_done(
        self, stage: str, run_id: str, factor_count: int, elapsed: float
    ) -> None:
        pass

    def notify_progress(self, stage: str, done: int, total: int) -> None:
        pass

    def notify_error(self, stage: str, exc: Exception) -> None:
        pass
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/notify/test_null.py -v
```
预期：PASSED

- [ ] **Step 6: 提交**

```bash
git add zer0factor/notify/__init__.py zer0factor/notify/null.py tests/notify/__init__.py tests/notify/test_null.py
git commit -m "feat(notify): add NullNotifier"
```

---

## Task 2: Config 扩展

**Files:**
- Modify: `zer0factor/config.py`
- Modify: `config/settings.toml`
- Modify: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 末尾增加：

```python
def test_load_config_reads_notify_webhook_url(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""

[notify]
webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"
""")
    cfg = load_config(toml)
    assert cfg.notify_webhook_url == "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"


def test_load_config_notify_webhook_url_defaults_to_empty(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""
""")
    cfg = load_config(toml)
    assert cfg.notify_webhook_url == ""
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_config.py::test_load_config_reads_notify_webhook_url tests/test_config.py::test_load_config_notify_webhook_url_defaults_to_empty -v
```
预期：`AttributeError: 'Config' object has no attribute 'notify_webhook_url'`

- [ ] **Step 3: 修改 Config dataclass 和 load_config**

将 `zer0factor/config.py` 全文替换为：

```python
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    zer0share_data_dir: Path
    factor_dir: Path
    db_path: Path
    log_path: Path
    universe: str
    process_universe: str
    start_date: str
    end_date: str
    notify_webhook_url: str = ""


def load_config(path: Path = Path("config/settings.toml")) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"配置文件格式错误: {e}") from e
    try:
        return Config(
            zer0share_data_dir=Path(raw["zer0share"]["data_dir"]),
            factor_dir=Path(raw["paths"]["factor_dir"]),
            db_path=Path(raw["paths"]["db_path"]),
            log_path=Path(raw["paths"]["log_path"]),
            universe=raw["factor"]["universe"],
            process_universe=raw["factor"].get("process_universe", "univ_trade_base"),
            start_date=raw["factor"]["start_date"],
            end_date=raw["factor"]["end_date"],
            notify_webhook_url=raw.get("notify", {}).get("webhook_url", ""),
        )
    except KeyError as e:
        raise KeyError(f"配置文件缺少必要字段: {e}") from e
```

- [ ] **Step 4: 在 config/settings.toml 末尾追加**

```toml

[notify]
webhook_url = ""   # 空 = 关闭通知；填入飞书 Webhook URL 即启用
```

- [ ] **Step 5: 运行全部 config 测试**

```bash
pytest tests/test_config.py -v
```
预期：全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add zer0factor/config.py config/settings.toml tests/test_config.py
git commit -m "feat(config): add notify_webhook_url field"
```

---

## Task 3: FeishuNotifier — 卡片构建

**Files:**
- Create: `zer0factor/notify/feishu.py`（只实现 `_build_card`）
- Create: `tests/notify/test_feishu.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/notify/test_feishu.py
from zer0factor.notify.feishu import FeishuNotifier


def _make_notifier() -> FeishuNotifier:
    return FeishuNotifier("https://open.feishu.cn/open-apis/bot/v2/hook/fake")


def test_build_card_structure():
    n = _make_notifier()
    card = n._build_card(
        title="[zer0factor] `raw` 完成 ✅",
        color="green",
        fields=[("因子数", "40"), ("耗时", "5.3s")],
    )
    assert card["msg_type"] == "interactive"
    c = card["card"]
    assert c["header"]["title"]["content"] == "[zer0factor] `raw` 完成 ✅"
    assert c["header"]["template"] == "green"
    elements = c["elements"]
    assert len(elements) == 1
    assert elements[0]["tag"] == "div"
    fs = elements[0]["fields"]
    assert len(fs) == 2
    assert fs[0]["is_short"] is True
    assert "因子数" in fs[0]["text"]["content"]
    assert "40" in fs[0]["text"]["content"]


def test_build_card_no_fields():
    n = _make_notifier()
    card = n._build_card(title="标题", color="orange", fields=[])
    # 无字段时 elements 为空列表
    assert card["card"]["elements"] == []


def test_build_card_red_color():
    n = _make_notifier()
    card = n._build_card(title="出错", color="red", fields=[])
    assert card["card"]["header"]["template"] == "red"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/notify/test_feishu.py -v
```
预期：`ImportError: cannot import name 'FeishuNotifier'`

- [ ] **Step 3: 实现 FeishuNotifier（仅 _build_card，其余 stub）**

```python
# zer0factor/notify/feishu.py
from __future__ import annotations

import json
import urllib.request


class FeishuNotifier:
    def __init__(self, webhook_url: str, *, app: str = "zer0factor") -> None:
        self._url = webhook_url
        self._app = app

    # --- 公开方法（Task 4 实现）---

    def notify_start(self, stage: str, details: dict[str, str] | None = None) -> None:
        pass

    def notify_done(self, stage: str, rows: dict[str, int], elapsed: float) -> None:
        pass

    def notify_eval_done(
        self, stage: str, run_id: str, factor_count: int, elapsed: float
    ) -> None:
        pass

    def notify_progress(self, stage: str, done: int, total: int) -> None:
        pass

    def notify_error(self, stage: str, exc: Exception) -> None:
        pass

    # --- 私有方法 ---

    def _build_card(
        self, title: str, color: str, fields: list[tuple[str, str]]
    ) -> dict:
        elements: list[dict] = []
        if fields:
            elements.append({
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{key}**\n{value}",
                        },
                    }
                    for key, value in fields
                ],
            })
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color,
                },
                "elements": elements,
            },
        }

    def _send(self, card: dict) -> None:
        pass  # Task 4 实现
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/notify/test_feishu.py::test_build_card_structure tests/notify/test_feishu.py::test_build_card_no_fields tests/notify/test_feishu.py::test_build_card_red_color -v
```
预期：全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add zer0factor/notify/feishu.py tests/notify/test_feishu.py
git commit -m "feat(notify): add FeishuNotifier._build_card"
```

---

## Task 4: FeishuNotifier — 发送与公开方法

**Files:**
- Modify: `zer0factor/notify/feishu.py`（实现 `_send` + 5 个公开方法）
- Modify: `tests/notify/test_feishu.py`（追加测试）

- [ ] **Step 1: 在 tests/notify/test_feishu.py 末尾追加测试**

```python
from unittest.mock import MagicMock, patch


def test_send_posts_json_to_webhook():
    n = _make_notifier()
    card = n._build_card("标题", "green", [])
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        n._send(card)
    mock_open.assert_called_once()
    req = mock_open.call_args[0][0]
    assert req.full_url == "https://open.feishu.cn/open-apis/bot/v2/hook/fake"
    body = json.loads(req.data)
    assert body["msg_type"] == "interactive"


def test_send_silences_network_errors():
    n = _make_notifier()
    card = n._build_card("标题", "green", [])
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        n._send(card)  # 不抛异常


def test_notify_start_sends_orange_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_start("raw", details={"因子数": "40", "workers": "16"})
    mock_send.assert_called_once()
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "orange"
    assert "raw" in card["card"]["header"]["title"]["content"]
    fields_content = [f["text"]["content"] for f in card["card"]["elements"][0]["fields"]]
    assert any("因子数" in c for c in fields_content)


def test_notify_done_sends_green_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_done("preprocess", {"f_a": 100, "f_b": 200}, 23.4)
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "green"
    fields_content = " ".join(
        f["text"]["content"] for f in card["card"]["elements"][0]["fields"]
    )
    assert "2" in fields_content   # 因子数 2
    assert "300" in fields_content  # 总行数 300
    assert "23.4" in fields_content


def test_notify_eval_done_sends_green_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_eval_done("evaluate", "20260614_120000", 129, 87.3)
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "green"
    fields_content = " ".join(
        f["text"]["content"] for f in card["card"]["elements"][0]["fields"]
    )
    assert "20260614_120000" in fields_content
    assert "129" in fields_content
    assert "87.3" in fields_content


def test_notify_progress_sends_blue_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_progress("evaluate", 32, 129)
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "blue"
    assert "25%" in card["card"]["header"]["title"]["content"]


def test_notify_error_sends_red_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_error("raw", ValueError("bad data"))
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "red"
    fields_content = " ".join(
        f["text"]["content"] for f in card["card"]["elements"][0]["fields"]
    )
    assert "ValueError" in fields_content
    assert "bad data" in fields_content
```

- [ ] **Step 2: 在文件顶部补充 import**

`tests/notify/test_feishu.py` 顶部添加：

```python
import json
from unittest.mock import MagicMock, patch
```

- [ ] **Step 3: 运行测试确认失败**

```bash
pytest tests/notify/test_feishu.py -v
```
预期：`_send`、各 notify 方法相关测试 FAIL（当前是 stub）

- [ ] **Step 4: 实现 _send 和 5 个公开方法**

将 `zer0factor/notify/feishu.py` 中 `_send` 和公开方法替换为：

```python
    def notify_start(self, stage: str, details: dict[str, str] | None = None) -> None:
        fields = list((details or {}).items())
        self._send(self._build_card(
            title=f"[{self._app}] `{stage}` 开始运行 ⏳",
            color="orange",
            fields=fields,
        ))

    def notify_done(self, stage: str, rows: dict[str, int], elapsed: float) -> None:
        self._send(self._build_card(
            title=f"[{self._app}] `{stage}` 完成 ✅",
            color="green",
            fields=[
                ("因子数", str(len(rows))),
                ("总行数", f"{sum(rows.values()):,}"),
                ("耗时", f"{elapsed:.1f}s"),
            ],
        ))

    def notify_eval_done(
        self, stage: str, run_id: str, factor_count: int, elapsed: float
    ) -> None:
        self._send(self._build_card(
            title=f"[{self._app}] `{stage}` 完成 ✅",
            color="green",
            fields=[
                ("run_id", run_id),
                ("因子数", str(factor_count)),
                ("耗时", f"{elapsed:.1f}s"),
            ],
        ))

    def notify_progress(self, stage: str, done: int, total: int) -> None:
        if total == 0:
            return
        pct = round(done / total * 100)
        self._send(self._build_card(
            title=f"[{self._app}] `{stage}` 进度 {pct}% ({done}/{total})",
            color="blue",
            fields=[],
        ))

    def notify_error(self, stage: str, exc: Exception) -> None:
        self._send(self._build_card(
            title=f"[{self._app}] `{stage}` 出错 ❌",
            color="red",
            fields=[
                ("异常类型", type(exc).__name__),
                ("信息", str(exc)),
            ],
        ))

    def _send(self, card: dict) -> None:
        payload = json.dumps(card).encode()
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass
```

- [ ] **Step 5: 运行全部 feishu 测试**

```bash
pytest tests/notify/test_feishu.py -v
```
预期：全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add zer0factor/notify/feishu.py tests/notify/test_feishu.py
git commit -m "feat(notify): implement FeishuNotifier"
```

---

## Task 5: load_notifier 工厂 + __init__.py

**Files:**
- Modify: `zer0factor/notify/__init__.py`
- Modify: `tests/notify/test_null.py`（追加 load_notifier 测试）

- [ ] **Step 1: 在 tests/notify/test_null.py 末尾追加测试**

```python
from zer0factor.config import Config
from zer0factor.notify import load_notifier, FeishuNotifier, NullNotifier
from pathlib import Path


def _make_config(webhook_url: str) -> Config:
    return Config(
        zer0share_data_dir=Path("."),
        factor_dir=Path("."),
        db_path=Path("."),
        log_path=Path("."),
        universe="all",
        process_universe="univ_trade_base",
        start_date="20160101",
        end_date="",
        notify_webhook_url=webhook_url,
    )


def test_load_notifier_returns_feishu_when_url_set():
    cfg = _make_config("https://open.feishu.cn/open-apis/bot/v2/hook/fake")
    notifier = load_notifier(cfg)
    assert isinstance(notifier, FeishuNotifier)


def test_load_notifier_returns_null_when_url_empty():
    cfg = _make_config("")
    notifier = load_notifier(cfg)
    assert isinstance(notifier, NullNotifier)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/notify/test_null.py -v
```
预期：`ImportError: cannot import name 'load_notifier'`

- [ ] **Step 3: 实现 __init__.py**

```python
# zer0factor/notify/__init__.py
from __future__ import annotations

from zer0factor.notify.feishu import FeishuNotifier
from zer0factor.notify.null import NullNotifier

__all__ = ["FeishuNotifier", "NullNotifier", "load_notifier"]


def load_notifier(config) -> FeishuNotifier | NullNotifier:
    """Return FeishuNotifier if webhook_url is set, else NullNotifier."""
    if config.notify_webhook_url:
        return FeishuNotifier(config.notify_webhook_url)
    return NullNotifier()
```

- [ ] **Step 4: 运行全部 notify 测试**

```bash
pytest tests/notify/ -v
```
预期：全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add zer0factor/notify/__init__.py tests/notify/test_null.py
git commit -m "feat(notify): add load_notifier factory"
```

---

## Task 6: pipeline.py 集成（preprocess / raw 阶段）

**Files:**
- Modify: `zer0factor/pipeline.py`（`run_build_stage` 加 notifier 参数）

- [ ] **Step 1: 写失败测试**

在 `tests/test_rolling_return_family.py`（或新建 `tests/test_pipeline_notify.py`）中追加：

```python
# tests/test_pipeline_notify.py
from unittest.mock import MagicMock, patch, call
import pytest
from zer0factor.notify.null import NullNotifier


def test_run_build_stage_calls_notify_start_and_done(tmp_path):
    """run_build_stage 在 raw 阶段前后调用 notifier。"""
    from zer0factor.pipeline import run_build_stage
    from zer0factor.storage import FactorStorage

    notifier = MagicMock(spec=NullNotifier)

    # 构造最小可运行的 storage（有 daily_return 数据）
    import pandas as pd
    storage = FactorStorage(tmp_path / "factors", tmp_path / "db.duckdb")
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    codes = ["000001.SZ", "000002.SZ"]
    idx = pd.MultiIndex.from_product([dates, codes], names=["trade_date", "ts_code"])
    df = pd.DataFrame({"value": [0.01, 0.02, 0.03, 0.04]}, index=idx).reset_index()
    storage.write("daily_return", df)

    run_build_stage(
        family_name="rolling_return",
        stage="raw",
        storage=storage,
        start_date=None,
        end_date=None,
        notifier=notifier,
    )

    notifier.notify_start.assert_called_once_with("raw")
    notifier.notify_done.assert_called_once()
    args = notifier.notify_done.call_args
    assert args[0][0] == "raw"
    assert isinstance(args[0][1], dict)   # rows dict
    assert isinstance(args[0][2], float)  # elapsed


def test_run_build_stage_calls_notify_error_on_failure(tmp_path):
    from zer0factor.pipeline import run_build_stage
    from zer0factor.storage import FactorStorage

    notifier = MagicMock(spec=NullNotifier)
    storage = FactorStorage(tmp_path / "factors", tmp_path / "db.duckdb")
    # 没有 daily_return 数据，应触发 FileNotFoundError

    with pytest.raises(FileNotFoundError):
        run_build_stage(
            family_name="rolling_return",
            stage="raw",
            storage=storage,
            start_date=None,
            end_date=None,
            notifier=notifier,
        )

    notifier.notify_error.assert_called_once()
    assert notifier.notify_done.call_count == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_pipeline_notify.py -v
```
预期：`TypeError: run_build_stage() got an unexpected keyword argument 'notifier'`

- [ ] **Step 3: 修改 zer0factor/pipeline.py 中的 run_build_stage**

在 `pipeline.py` 顶部增加 import：

```python
import time
from zer0factor.notify.null import NullNotifier
```

将 `run_build_stage` 签名和函数体替换为：

```python
def run_build_stage(
    family_name: str,
    stage: str,
    *,
    storage: Any,
    pro: Any | None = None,
    start_date: str | None,
    end_date: str | None,
    process_universe: str | None = None,
    workers: int = 1,
    notifier: NullNotifier | None = None,
) -> dict[str, int]:
    family = get_family(family_name)
    if stage not in {"raw", "preprocess", "all"}:
        raise ValueError(f"unknown build stage: {stage}")

    _notifier = notifier or NullNotifier()
    rows: dict[str, int] = {}

    if stage in {"raw", "all"}:
        _notifier.notify_start("raw")
        t0 = time.monotonic()
        try:
            rows.update(
                compute_raw_family_factors(
                    family,
                    storage=storage,
                    start_date=start_date,
                    end_date=end_date,
                    workers=workers,
                )
            )
        except Exception as exc:
            _notifier.notify_error("raw", exc)
            raise
        _notifier.notify_done("raw", rows, time.monotonic() - t0)

    if stage in {"preprocess", "all"}:
        if pro is None:
            raise ValueError("pro is required for preprocess stage")
        if process_universe is None:
            raise ValueError("process_universe is required for preprocess stage")
        _notifier.notify_start("preprocess")
        t0 = time.monotonic()
        pre_rows: dict[str, int] = {}
        try:
            pre_rows.update(
                preprocess_all_factors(
                    list(family.raw_names()),
                    storage=storage,
                    pro=pro,
                    start_date=start_date,
                    end_date=end_date,
                    process_universe=process_universe,
                    profiles=family.profiles,
                    workers=workers,
                )
            )
        except Exception as exc:
            _notifier.notify_error("preprocess", exc)
            raise
        _notifier.notify_done("preprocess", pre_rows, time.monotonic() - t0)
        rows.update(pre_rows)

    return rows
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_pipeline_notify.py -v
```
预期：全部 PASSED

- [ ] **Step 5: 运行既有测试确认无回归**

```bash
pytest tests/test_rolling_return_family.py tests/test_build_rolling_return_factors.py -v
```
预期：全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add zer0factor/pipeline.py tests/test_pipeline_notify.py
git commit -m "feat(pipeline): add notifier to run_build_stage"
```

---

## Task 7: eval/pipeline.py 集成（evaluate 阶段）

**Files:**
- Modify: `zer0factor/eval/pipeline.py`（`evaluate_factors` 加 notifier 参数和进度里程碑）
- Create: `tests/test_eval_pipeline_notify.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_eval_pipeline_notify.py
from unittest.mock import MagicMock
import pandas as pd
import pytest
from zer0factor.notify.null import NullNotifier


def _make_factor_df(dates, codes, value=0.01):
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(dates), codes], names=["trade_date", "ts_code"]
    )
    return pd.DataFrame({"value": value}, index=idx).reset_index()


def test_evaluate_factors_calls_notify_start_and_eval_done(tmp_path, monkeypatch):
    from zer0factor.eval.pipeline import evaluate_factors
    from zer0factor.eval.config import EvaluationConfig
    from zer0factor.storage import FactorStorage

    notifier = MagicMock(spec=NullNotifier)

    # Patch evaluate_factor を返す stub
    stub_result = MagicMock()
    stub_result.summary = pd.DataFrame({
        "factor_name": ["f"], "period": ["1D"], "ic_mean": [0.05],
        "ic_std": [0.1], "icir": [0.5], "win_rate": [0.55],
        "long_short_spread_bps": [10.0], "monotonicity": [0.8],
        "sample_count": [2000], "direction": [1],
    })
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.evaluate_factor", lambda **kwargs: stub_result
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.write_run_summary",
        lambda **kwargs: {"metadata": tmp_path / "meta.json"},
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.create_run_directory",
        lambda *args, **kwargs: ("20260614_120000", tmp_path),
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.load_price_data", lambda *args, **kwargs: pd.DataFrame()
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.load_universe_panel", lambda *args, **kwargs: None
    )

    storage = FactorStorage(tmp_path / "factors", tmp_path / "db.duckdb")
    config = EvaluationConfig(
        factor_names=("factor_a", "factor_b"),
        start_date="20160101",
        end_date="20260101",  # 避免触发 _max_stored_factor_trade_date 读 storage
        periods=(1,),
        quantiles=5,
        return_type="open_t1",
        max_loss=0.35,
        output_dir=tmp_path / "evals",
    )

    result = evaluate_factors(
        factor_names=("factor_a", "factor_b"),
        storage=storage,
        pro=MagicMock(),
        config=config,
        notifier=notifier,
    )

    notifier.notify_start.assert_called_once()
    start_args = notifier.notify_start.call_args
    assert start_args[0][0] == "evaluate"

    notifier.notify_eval_done.assert_called_once()
    eval_done_args = notifier.notify_eval_done.call_args[0]
    assert eval_done_args[0] == "evaluate"
    assert eval_done_args[1] == "20260614_120000"
    assert eval_done_args[2] == 2
    assert isinstance(eval_done_args[3], float)


def test_evaluate_factors_calls_notify_progress_at_milestones(tmp_path, monkeypatch):
    from zer0factor.eval.pipeline import evaluate_factors
    from zer0factor.eval.config import EvaluationConfig
    from zer0factor.storage import FactorStorage

    notifier = MagicMock(spec=NullNotifier)

    stub_result = MagicMock()
    stub_result.summary = pd.DataFrame({
        "factor_name": ["f"], "period": ["1D"], "ic_mean": [0.05],
        "ic_std": [0.1], "icir": [0.5], "win_rate": [0.55],
        "long_short_spread_bps": [10.0], "monotonicity": [0.8],
        "sample_count": [2000], "direction": [1],
    })
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.evaluate_factor", lambda **kwargs: stub_result
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.write_run_summary",
        lambda **kwargs: {"metadata": tmp_path / "meta.json"},
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.create_run_directory",
        lambda *args, **kwargs: ("run_id", tmp_path),
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.load_price_data", lambda *args, **kwargs: pd.DataFrame()
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.load_universe_panel", lambda *args, **kwargs: None
    )

    storage = FactorStorage(tmp_path / "factors", tmp_path / "db.duckdb")
    # 4 个因子：完成第 1 个 = 25%，第 2 个 = 50%，第 3 个 = 75%
    factor_names = ("f1", "f2", "f3", "f4")
    config = EvaluationConfig(
        factor_names=factor_names,
        start_date="20160101",
        end_date="20260101",  # 避免触发 _max_stored_factor_trade_date 读 storage
        periods=(1,),
        quantiles=5,
        return_type="open_t1",
        max_loss=0.35,
        output_dir=tmp_path / "evals",
    )

    evaluate_factors(
        factor_names=factor_names,
        storage=storage,
        pro=MagicMock(),
        config=config,
        notifier=notifier,
    )

    assert notifier.notify_progress.call_count == 3
    progress_calls = [c[0] for c in notifier.notify_progress.call_args_list]
    assert progress_calls[0] == ("evaluate", 1, 4)
    assert progress_calls[1] == ("evaluate", 2, 4)
    assert progress_calls[2] == ("evaluate", 3, 4)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_eval_pipeline_notify.py -v
```
预期：`TypeError: evaluate_factors() got an unexpected keyword argument 'notifier'`

- [ ] **Step 3: 修改 zer0factor/eval/pipeline.py**

在 `eval/pipeline.py` 顶部增加 import：

```python
import time
from zer0factor.notify.null import NullNotifier
```

将 `evaluate_factors` 签名改为：

```python
def evaluate_factors(
    *,
    factor_names: tuple[str, ...] | list[str],
    storage,
    pro,
    config: EvaluationConfig,
    run_id: str | None = None,
    log_info: Callable[[str], None] | None = None,
    workers: int = 1,
    notifier: NullNotifier | None = None,
) -> EvaluationRunResult:
```

在函数体内，`run_id, run_dir = create_run_directory(...)` 之后，price/universe 加载之前插入：

```python
    _notifier = notifier or NullNotifier()
    _notifier.notify_start(
        "evaluate",
        details={
            "因子数": str(len(resolved_config.factor_names)),
            "workers": str(workers),
        },
    )
    _t0 = time.monotonic()
    _milestones = {
        round(len(resolved_config.factor_names) * pct)
        for pct in (0.25, 0.50, 0.75)
    } - {0, len(resolved_config.factor_names)}
```

在串行循环 `for factor_name in resolved_config.factor_names:` 内，`factor_results.append(...)` 之后插入：

```python
                _done = len(factor_results)
                if _done in _milestones:
                    _notifier.notify_progress("evaluate", _done, len(resolved_config.factor_names))
```

在并行分支 `for factor_name, summary in pool.map(...):` 内，`summaries[factor_name] = summary` 之后插入：

```python
            _done = len(summaries)
            if _done in _milestones:
                _notifier.notify_progress("evaluate", _done, len(config.factor_names))
```

在 `return EvaluationRunResult(...)` 之前插入：

```python
    _notifier.notify_eval_done(
        "evaluate", run_id, len(factor_results), time.monotonic() - _t0
    )
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_eval_pipeline_notify.py -v
```
预期：全部 PASSED

- [ ] **Step 5: 运行既有 eval 测试确认无回归**

```bash
pytest tests/test_eval_pipeline.py -v
```
预期：全部 PASSED

- [ ] **Step 6: 提交**

```bash
git add zer0factor/eval/pipeline.py tests/test_eval_pipeline_notify.py
git commit -m "feat(eval): add notifier to evaluate_factors"
```

---

## Task 8: main.py 接线

**Files:**
- Modify: `main.py`（`build_factors_command` 和 `_run_evaluation_job` 中构造并传入 notifier）

- [ ] **Step 1: 在 main.py 顶部 import 中追加**

找到 `from zer0factor.config import load_config` 所在行，在其下方添加：

```python
from zer0factor.notify import load_notifier
```

- [ ] **Step 2: 修改 build_factors_command**

找到 `build_factors_command` 函数体中的 `rows = run_build_stage(...)` 调用，在 `storage = ...` 行之后加一行，并在 `run_build_stage` 调用中传入 `notifier`：

```python
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    notifier = load_notifier(cfg)                          # 新增
    pro = LocalPro(cfg.zer0share_data_dir) if stage in {"preprocess", "all"} else None

    rows = run_build_stage(
        family_name=family_name,
        stage=stage,
        storage=storage,
        pro=pro,
        start_date=resolved_start,
        end_date=resolved_end,
        process_universe=cfg.process_universe,
        workers=workers,
        notifier=notifier,                                 # 新增
    )
```

- [ ] **Step 3: 修改 _run_evaluation_job**

找到 `_run_evaluation_job` 函数体中的 `result = evaluate_factors(...)` 调用，在 `storage = ...` 行之后加一行，并在 `evaluate_factors` 调用中传入 `notifier`：

```python
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    notifier = load_notifier(cfg)                          # 新增

    def log_progress(message: str) -> None:
        logger.info(message)

    result = evaluate_factors(
        factor_names=factor_names,
        storage=storage,
        pro=LocalPro(cfg.zer0share_data_dir),
        config=config,
        log_info=log_progress,
        workers=workers,
        notifier=notifier,                                 # 新增
    )
```

- [ ] **Step 4: 运行全部测试确认无回归**

```bash
pytest tests/ -v --tb=short
```
预期：全部 PASSED

- [ ] **Step 5: 提交**

```bash
git add main.py
git commit -m "feat: wire notifier into CLI commands"
```

---

## 验收标准

1. `pytest tests/notify/ tests/test_config.py tests/test_pipeline_notify.py tests/test_eval_pipeline_notify.py -v` 全部绿
2. `config/settings.toml` 中 `webhook_url` 为空时，全流程运行无任何副作用
3. 填入真实飞书 Webhook URL 后，`build-factors` 和 `evaluate-batch` 命令各发送开始/完成卡片
