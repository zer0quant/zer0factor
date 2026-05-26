from __future__ import annotations

import re
import warnings
from contextlib import contextmanager

import numpy as np
import pandas as pd

warnings.filterwarnings(
    "ignore",
    message='Module "zipline.assets" not found.*',
    category=UserWarning,
    module=r"pyfolio\.pos",
)

import pyfolio as pf  # noqa: E402
from alphalens import performance as alphalens_performance  # noqa: E402


def detect_direction(daily_ic: pd.DataFrame) -> int:
    """Returns +1 if overall IC is non-negative, -1 otherwise."""
    overall = daily_ic.mean().mean()
    return 1 if (pd.isna(overall) or overall >= 0) else -1


def build_pyfolio_return_metrics(
    clean_factor_data: pd.DataFrame,
    *,
    direction: int,
    period: str,
    long_quantile: int,
    short_quantile: int,
    index_returns: pd.Series | None = None,
) -> dict[str, float]:
    """
    Build all portfolio performance stats from Alphalens daily returns.

    Single-leg portfolios pin factor values to +1/-1 so Alphalens builds pure
    equal-weight long and short sleeves instead of using raw factor signs.
    """
    try:
        with _suppress_known_pyfolio_warnings():
            long_returns, long_positions, benchmark = _create_pyfolio_returns(
                clean_factor_data,
                period=period,
                quantiles=[long_quantile],
                factor_value=1.0,
            )
            short_returns, short_positions, _ = _create_pyfolio_returns(
                clean_factor_data,
                period=period,
                quantiles=[short_quantile],
                factor_value=-1.0,
            )
            ls_returns, ls_positions, ls_benchmark = _create_long_short_pyfolio_returns(
                clean_factor_data,
                direction=direction,
                period=period,
                equal_weight=True,
                quantiles=sorted([long_quantile, short_quantile]),
            )
            full_returns, full_positions, full_benchmark = (
                _create_long_short_pyfolio_returns(
                    clean_factor_data,
                    direction=direction,
                    period=period,
                    equal_weight=False,
                    quantiles=None,
                )
            )
    except Exception:
        return _empty_pyfolio_return_metrics(index_returns is not None)

    period_int = _parse_period_int(period)
    long_returns = _daily_equivalent_returns(long_returns, period_int)
    short_returns = _daily_equivalent_returns(short_returns, period_int)
    ls_returns = _daily_equivalent_returns(ls_returns, period_int)
    full_returns = _daily_equivalent_returns(full_returns, period_int)
    benchmark = _daily_equivalent_returns(benchmark, period_int)
    ls_benchmark = _daily_equivalent_returns(ls_benchmark, period_int)
    full_benchmark = _daily_equivalent_returns(full_benchmark, period_int)

    result: dict[str, float] = {}
    result.update(_portfolio_stats("long", long_returns, benchmark, long_positions, period_int))
    result.update(_portfolio_stats("short", short_returns, benchmark, short_positions, period_int))

    if benchmark is not None:
        long_exc_returns = long_returns - benchmark.reindex(long_returns.index).fillna(0)
        short_exc_returns = short_returns + benchmark.reindex(short_returns.index).fillna(0)
        result.update(_portfolio_stats("long_exc", long_exc_returns, period_int=period_int))
        result.update(_portfolio_stats("short_exc", short_exc_returns, period_int=period_int))
        short_exc_ann = _stat_value(
            pf.timeseries.perf_stats(short_exc_returns),
            "Annual return",
        )
    else:
        result.update(_empty_portfolio_stats("long_exc"))
        result.update(_empty_portfolio_stats("short_exc"))
        short_exc_ann = float("nan")

    result.update(_portfolio_stats("ls", ls_returns, ls_benchmark, ls_positions, period_int))
    result.update(
        _portfolio_stats("full", full_returns, full_benchmark, full_positions, period_int)
    )

    if index_returns is not None:
        aligned_index = _daily_equivalent_returns(
            index_returns.reindex(long_returns.index).fillna(0),
            period_int,
        )
        result.update(
            _portfolio_stats("idx_exc", long_returns - aligned_index, period_int=period_int)
        )

    result["long_exc_short_exc_ann_ret_ratio"] = _ann_return_ratio(
        result["long_exc_ann_ret"],
        short_exc_ann,
    )
    result["ls_ann_ret_ratio"] = _ann_return_ratio(
        result["ls_ann_ret"],
        result["short_ann_ret"],
    )
    return result


def _create_pyfolio_returns(
    clean_factor_data: pd.DataFrame,
    *,
    period: str,
    quantiles: list[int],
    factor_value: float,
) -> tuple[pd.Series, pd.DataFrame, pd.Series | None]:
    factor_data = clean_factor_data.copy()
    factor_data["factor"] = factor_value
    return alphalens_performance.create_pyfolio_input(
        factor_data,
        period=period,
        capital=None,
        long_short=False,
        group_neutral=False,
        equal_weight=True,
        quantiles=quantiles,
        groups=None,
        benchmark_period="1D",
    )


def _create_long_short_pyfolio_returns(
    clean_factor_data: pd.DataFrame,
    *,
    direction: int,
    period: str,
    equal_weight: bool,
    quantiles: list[int] | None,
) -> tuple[pd.Series, pd.DataFrame, pd.Series | None]:
    factor_data = clean_factor_data.copy()
    factor_data["factor"] = factor_data["factor"] * direction
    return alphalens_performance.create_pyfolio_input(
        factor_data,
        period=period,
        capital=None,
        long_short=True,
        group_neutral=False,
        equal_weight=equal_weight,
        quantiles=quantiles,
        groups=None,
        benchmark_period="1D",
    )


def _portfolio_stats(
    prefix: str,
    returns: pd.Series,
    factor_returns: pd.Series | None = None,
    positions: pd.DataFrame | None = None,
    period_int: int = 1,
) -> dict[str, float]:
    stats = pf.timeseries.perf_stats(
        returns,
        factor_returns=factor_returns,
        positions=positions,
    )
    return {
        f"{prefix}_ann_ret": _stat_value(stats, "Annual return"),
        f"{prefix}_max_dd": _stat_value(stats, "Max drawdown"),
        f"{prefix}_calmar": _stat_value(stats, "Calmar ratio"),
        f"{prefix}_sharpe": _adjusted_sharpe(
            returns,
            _stat_value(stats, "Sharpe ratio"),
            period_int,
        ),
    }


@contextmanager
def _suppress_known_pyfolio_warnings():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="'freq' not set, using business day calendar",
            category=UserWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Series.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="DataFrame.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Downcasting object dtype arrays on \\.fillna.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Non-vectorized DateOffset being applied.*",
            category=pd.errors.PerformanceWarning,
            module=r"alphalens\.utils",
        )
        yield


def _empty_pyfolio_return_metrics(include_idx_exc: bool) -> dict[str, float]:
    result: dict[str, float] = {}
    for prefix in ["long", "short", "long_exc", "short_exc", "ls", "full"]:
        result.update(_empty_portfolio_stats(prefix))
    if include_idx_exc:
        result.update(_empty_portfolio_stats("idx_exc"))
    result["long_exc_short_exc_ann_ret_ratio"] = float("nan")
    result["ls_ann_ret_ratio"] = float("nan")
    return result


def _empty_portfolio_stats(prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_ann_ret": float("nan"),
        f"{prefix}_max_dd": float("nan"),
        f"{prefix}_calmar": float("nan"),
        f"{prefix}_sharpe": float("nan"),
    }


def _ann_return_ratio(numerator: float, denominator: float) -> float:
    if pd.isna(numerator) or pd.isna(denominator) or np.isclose(denominator, 0.0):
        return float("nan")
    return float(numerator / abs(denominator))


def _daily_equivalent_returns(
    returns: pd.Series | None,
    period_int: int,
) -> pd.Series | None:
    if returns is None or period_int <= 1:
        return returns
    return (1 + returns).pow(1 / period_int) - 1


def _adjusted_sharpe(returns: pd.Series, sharpe: float, period_int: int) -> float:
    if pd.isna(sharpe) or period_int <= 1:
        return sharpe
    clean = returns.dropna().astype(float)
    lag_count = min(period_int - 1, len(clean) - 1)
    if lag_count <= 0:
        return sharpe
    weighted_autocorr = 0.0
    for lag in range(1, lag_count + 1):
        if len(clean) <= lag + 1:
            continue
        autocorr = clean.autocorr(lag)
        if pd.isna(autocorr):
            continue
        weighted_autocorr += (1 - lag / period_int) * autocorr
    adjustment = np.sqrt(max(1 + 2 * weighted_autocorr, 1e-12))
    return float(sharpe / adjustment)


def _parse_period_int(period: str) -> int:
    match = re.match(r"^(\d+)[Dd]$", str(period))
    if match is None:
        return 1
    return int(match.group(1))


def _stat_value(stats: pd.Series, key: str) -> float:
    value = stats.get(key, float("nan"))
    return float("nan") if pd.isna(value) else float(value)
