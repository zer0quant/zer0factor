from __future__ import annotations

from zer0factor.notify.feishu import FeishuNotifier
from zer0factor.notify.null import NullNotifier

__all__ = ["FeishuNotifier", "NullNotifier", "load_notifier"]


def load_notifier(config) -> FeishuNotifier | NullNotifier:
    """Return FeishuNotifier if webhook_url is set, else NullNotifier."""
    if config.notify_webhook_url:
        return FeishuNotifier(config.notify_webhook_url)
    return NullNotifier()
