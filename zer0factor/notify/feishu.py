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
