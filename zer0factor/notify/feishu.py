from __future__ import annotations

import json
import urllib.request


class FeishuNotifier:
    def __init__(self, webhook_url: str, *, app: str = "zer0factor") -> None:
        self._url = webhook_url
        self._app = app

    # --- 公开方法（Task 4 实现）---

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
