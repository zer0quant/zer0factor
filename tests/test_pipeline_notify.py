from unittest.mock import MagicMock, patch, call
import pytest
from zer0factor.notify.null import NullNotifier


def test_run_build_stage_calls_notify_start_and_done(tmp_path):
    """run_build_stage 在 raw 阶段前后调用 notifier。"""
    from zer0factor.pipeline import run_build_stage
    from zer0factor.storage import FactorStorage

    notifier = MagicMock(spec=NullNotifier)

    # 构造最小可运行的 storage（有所有 base factor 数据）
    import pandas as pd
    from zer0factor.factors.rolling_returns import BASE_RETURN_FACTORS
    storage = FactorStorage(tmp_path / "factors", tmp_path / "db.duckdb")
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    codes = ["000001.SZ", "000002.SZ"]
    idx = pd.MultiIndex.from_product([dates, codes], names=["trade_date", "ts_code"])
    df = pd.DataFrame({"value": [0.01, 0.02, 0.03, 0.04]}, index=idx).reset_index()
    for base_factor in BASE_RETURN_FACTORS:
        storage.write(base_factor, df)

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
