from pathlib import Path

from zer0factor.config import Config
from zer0factor.notify import load_notifier, FeishuNotifier, NullNotifier


def test_null_notifier_all_methods_are_no_ops():
    n = NullNotifier()
    # 所有方法调用不抛异常，返回 None
    assert n.notify_start("raw") is None
    assert n.notify_start("preprocess", details={"因子数": "40"}) is None
    assert n.notify_done("raw", {"factor_a": 100, "factor_b": 200}, 5.3) is None
    assert n.notify_eval_done("evaluate", "20260614_120000", 129, 87.3) is None
    assert n.notify_progress("evaluate", 32, 129) is None
    assert n.notify_error("raw", ValueError("boom")) is None


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
