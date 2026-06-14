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
