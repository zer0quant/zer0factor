import math

import pandas as pd
import pytest

from zer0factor.eval.metrics.returns import (
    build_pyfolio_return_metrics,
    detect_direction,
)


def test_detect_direction_positive_ic_gives_plus_one():
    daily_ic = pd.DataFrame(
        {"1D": [0.1, 0.2, 0.05]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == 1


def test_detect_direction_negative_ic_gives_minus_one():
    daily_ic = pd.DataFrame(
        {"1D": [-0.1, -0.2, -0.05]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == -1


def test_detect_direction_zero_ic_gives_plus_one():
    daily_ic = pd.DataFrame(
        {"1D": [0.0, 0.0, 0.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == 1


def test_build_pyfolio_return_metrics_builds_all_portfolios_and_maps_stats(monkeypatch):
    index = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-02"), "A"),
            (pd.Timestamp("2024-01-02"), "B"),
        ],
        names=["date", "asset"],
    )
    clean_factor_data = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 10],
            "1D": [0.01, -0.01],
        },
        index=index,
    )
    captured = {}
    call_returns = {
        (False, (1,)): pd.Series(
            [0.03, 0.01], index=pd.date_range("2024-01-02", periods=2)
        ),
        (False, (10,)): pd.Series(
            [-0.02, 0.01], index=pd.date_range("2024-01-02", periods=2)
        ),
        (True, (1, 10)): pd.Series(
            [0.04, -0.01], index=pd.date_range("2024-01-02", periods=2)
        ),
        (True, None): pd.Series(
            [0.05, -0.02], index=pd.date_range("2024-01-02", periods=2)
        ),
    }

    def fake_create_pyfolio_input(
        factor_data,
        period,
        capital,
        long_short,
        group_neutral,
        equal_weight,
        quantiles,
        groups,
        benchmark_period,
    ):
        key = (long_short, tuple(quantiles) if quantiles is not None else None)
        captured[key] = {
            "factor": factor_data["factor"].tolist(),
            "period": period,
            "long_short": long_short,
            "equal_weight": equal_weight,
            "quantiles": quantiles,
        }
        returns = call_returns[key]
        positions = pd.DataFrame(index=returns.index)
        benchmark = pd.Series([0.01, 0.005], index=returns.index)
        return returns, positions, benchmark

    def fake_perf_stats(returns, factor_returns=None, positions=None):
        ann_by_returns = {
            (0.03, 0.01): 0.30,
            (-0.02, 0.01): 0.20,
            (0.02, 0.005): 0.10,
            (-0.01, 0.015): 0.05,
            (0.04, -0.01): 0.40,
            (0.025, -0.005): 0.15,
            (0.05, -0.02): 0.50,
        }
        rounded = tuple(round(float(x), 6) for x in returns.tolist())
        return pd.Series(
            {
                "Annual return": ann_by_returns[rounded],
                "Max drawdown": -0.03,
                "Calmar ratio": 4.0,
                "Sharpe ratio": 1.5,
            }
        )

    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.alphalens_performance.create_pyfolio_input",
        fake_create_pyfolio_input,
    )
    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.pf.timeseries.perf_stats",
        fake_perf_stats,
    )

    result = build_pyfolio_return_metrics(
        clean_factor_data,
        direction=-1,
        period="1D",
        long_quantile=1,
        short_quantile=10,
        index_returns=pd.Series([0.005, 0.015], index=pd.date_range("2024-01-02", periods=2)),
    )

    assert captured[(False, (1,))]["factor"] == [1.0, 1.0]
    assert captured[(False, (1,))]["period"] == "1D"
    assert not captured[(False, (1,))]["long_short"]
    assert captured[(False, (1,))]["equal_weight"]
    assert captured[(False, (10,))]["factor"] == [-1.0, -1.0]
    assert captured[(True, (1, 10))]["factor"] == [-1.0, -2.0]
    assert captured[(True, (1, 10))]["long_short"]
    assert captured[(True, None)]["factor"] == [-1.0, -2.0]
    assert captured[(True, None)]["long_short"]
    assert not captured[(True, None)]["equal_weight"]
    assert captured[(True, None)]["quantiles"] is None
    assert result["long_ann_ret"] == pytest.approx(0.30)
    assert result["short_ann_ret"] == pytest.approx(0.20)
    assert result["long_exc_ann_ret"] == pytest.approx(0.10)
    assert result["short_exc_ann_ret"] == pytest.approx(0.05)
    assert result["short_exc_max_dd"] == pytest.approx(-0.03)
    assert result["short_exc_calmar"] == pytest.approx(4.0)
    assert result["short_exc_sharpe"] == pytest.approx(1.5)
    assert result["long_exc_short_exc_ann_ret_ratio"] == pytest.approx(2.0)
    assert result["full_ann_ret"] == pytest.approx(0.50)
    assert result["full_max_dd"] == pytest.approx(-0.03)
    assert result["full_calmar"] == pytest.approx(4.0)
    assert result["full_sharpe"] == pytest.approx(1.5)
    assert result["ls_ann_ret"] == pytest.approx(0.40)
    assert result["idx_exc_ann_ret"] == pytest.approx(0.15)
    assert result["ls_max_dd"] == pytest.approx(-0.03)
    assert result["ls_calmar"] == pytest.approx(4.0)
    assert result["ls_sharpe"] == pytest.approx(1.5)
    assert result["ls_ann_ret_ratio"] == pytest.approx(2.0)


def test_build_pyfolio_return_metrics_returns_nan_metrics_when_pyfolio_fails(monkeypatch):
    clean_factor_data = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 10],
            "1D": [0.01, -0.01],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-02"), "A"),
                (pd.Timestamp("2024-01-02"), "B"),
            ],
            names=["date", "asset"],
        ),
    )

    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.alphalens_performance.create_pyfolio_input",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad input")),
    )

    result = build_pyfolio_return_metrics(
        clean_factor_data,
        direction=1,
        period="1D",
        long_quantile=10,
        short_quantile=1,
    )

    assert math.isnan(result["long_ann_ret"])
    assert math.isnan(result["short_ann_ret"])
    assert math.isnan(result["long_exc_ann_ret"])
    assert math.isnan(result["short_exc_ann_ret"])
    assert math.isnan(result["full_ann_ret"])
    assert math.isnan(result["ls_ann_ret"])


def test_build_pyfolio_return_metrics_daily_equivalent_for_multi_day_period(monkeypatch):
    clean_factor_data = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 10],
            "5D": [0.10, -0.05],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-02"), "A"),
                (pd.Timestamp("2024-01-02"), "B"),
            ],
            names=["date", "asset"],
        ),
    )
    dates = pd.date_range("2024-01-02", periods=2)
    call_returns = {
        (False, (1,)): pd.Series([0.10, 0.20], index=dates),
        (False, (10,)): pd.Series([-0.05, -0.10], index=dates),
        (True, (1, 10)): pd.Series([0.15, 0.30], index=dates),
        (True, None): pd.Series([0.08, 0.16], index=dates),
    }
    captured_returns = {}

    def fake_create_pyfolio_input(
        factor_data,
        period,
        capital,
        long_short,
        group_neutral,
        equal_weight,
        quantiles,
        groups,
        benchmark_period,
    ):
        key = (long_short, tuple(quantiles) if quantiles is not None else None)
        returns = call_returns[key]
        positions = pd.DataFrame(index=returns.index)
        benchmark = pd.Series([0.05, 0.10], index=returns.index)
        return returns, positions, benchmark

    def fake_perf_stats(returns, factor_returns=None, positions=None):
        captured_returns[len(captured_returns)] = returns.copy()
        return pd.Series(
            {
                "Annual return": float(returns.iloc[0]),
                "Max drawdown": -0.01,
                "Calmar ratio": 1.0,
                "Sharpe ratio": 1.0,
            }
        )

    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.alphalens_performance.create_pyfolio_input",
        fake_create_pyfolio_input,
    )
    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.pf.timeseries.perf_stats",
        fake_perf_stats,
    )

    result = build_pyfolio_return_metrics(
        clean_factor_data,
        direction=1,
        period="5D",
        long_quantile=1,
        short_quantile=10,
        index_returns=pd.Series([0.025, 0.05], index=dates),
    )

    long_daily = (1.10 ** (1 / 5)) - 1
    benchmark_daily = (1.05 ** (1 / 5)) - 1
    index_daily = (1.025 ** (1 / 5)) - 1
    assert result["long_ann_ret"] == pytest.approx(long_daily)
    assert result["long_exc_ann_ret"] == pytest.approx(long_daily - benchmark_daily)
    assert result["idx_exc_ann_ret"] == pytest.approx(long_daily - index_daily)
    assert captured_returns[0].iloc[0] == pytest.approx(long_daily)


def test_build_pyfolio_return_metrics_adjusts_sharpe_for_overlapping_period(monkeypatch):
    clean_factor_data = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 10],
            "5D": [0.10, -0.05],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-02"), "A"),
                (pd.Timestamp("2024-01-02"), "B"),
            ],
            names=["date", "asset"],
        ),
    )
    dates = pd.date_range("2024-01-02", periods=5)
    overlapping_returns = pd.Series([0.01, 0.011, 0.012, 0.013, 0.014], index=dates)

    def fake_create_pyfolio_input(
        factor_data,
        period,
        capital,
        long_short,
        group_neutral,
        equal_weight,
        quantiles,
        groups,
        benchmark_period,
    ):
        positions = pd.DataFrame(index=dates)
        benchmark = pd.Series([0.0] * len(dates), index=dates)
        return overlapping_returns, positions, benchmark

    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.alphalens_performance.create_pyfolio_input",
        fake_create_pyfolio_input,
    )
    monkeypatch.setattr(
        "zer0factor.eval.metrics.returns.pf.timeseries.perf_stats",
        lambda *args, **kwargs: pd.Series(
            {
                "Annual return": 0.1,
                "Max drawdown": -0.01,
                "Calmar ratio": 1.0,
                "Sharpe ratio": 10.0,
            }
        ),
    )

    result = build_pyfolio_return_metrics(
        clean_factor_data,
        direction=1,
        period="5D",
        long_quantile=1,
        short_quantile=10,
    )

    assert result["long_sharpe"] < 10.0
    assert result["ls_sharpe"] < 10.0
