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
