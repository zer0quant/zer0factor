from __future__ import annotations

import math

import numpy as np
import pandas as pd


def detect_direction(daily_ic: pd.DataFrame) -> int:
    """Returns +1 if overall IC is non-negative, -1 otherwise."""
    overall = daily_ic.mean().mean()
    return 1 if (pd.isna(overall) or overall >= 0) else -1


def annualized_return(daily_returns: pd.Series) -> float:
    n = len(daily_returns.dropna())
    if n == 0:
        return float("nan")
    return float((1 + daily_returns.dropna()).prod() ** (252 / n) - 1)


def max_drawdown(daily_returns: pd.Series) -> float:
    clean = daily_returns.dropna()
    if len(clean) == 0:
        return float("nan")
    cumulative = (1 + clean).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak
    return float(drawdown.min())


def sharpe_ratio(daily_returns: pd.Series) -> float:
    clean = daily_returns.dropna()
    std = clean.std()
    if pd.isna(std) or np.isclose(std, 0.0):
        return float("nan")
    return float(clean.mean() / std * math.sqrt(252))


def calmar_ratio(daily_returns: pd.Series) -> float:
    ann = annualized_return(daily_returns)
    dd = max_drawdown(daily_returns)
    if pd.isna(dd) or np.isclose(dd, 0.0):
        return float("nan")
    return float(ann / abs(dd))


def build_group_return_metrics(
    mean_ret_by_date: pd.DataFrame,
    mean_ret_by_date_demeaned: pd.DataFrame,
    *,
    direction: int,
    period: str,
    n_quantiles: int,
    index_returns: pd.Series | None = None,
) -> dict[str, float]:
    """
    mean_ret_by_date: MultiIndex (date, factor_quantile), columns=periods
    mean_ret_by_date_demeaned: same shape, demeaned
    direction: +1 or -1
    period: e.g. "1D"
    n_quantiles: total number of quantiles
    index_returns: optional Series (DatetimeIndex -> daily return) for index excess
    """
    q_long = n_quantiles if direction == 1 else 1
    q_short = 1 if direction == 1 else n_quantiles

    long_daily = _extract_quantile_daily(mean_ret_by_date, q_long, period)
    short_daily = _extract_quantile_daily(mean_ret_by_date, q_short, period)
    ls_daily = long_daily - short_daily

    long_exc_daily = _extract_quantile_daily(mean_ret_by_date_demeaned, q_long, period)
    short_exc_daily = _extract_quantile_daily(mean_ret_by_date_demeaned, q_short, period)

    result: dict[str, float] = {}

    for prefix, series in [
        ("long", long_daily),
        ("short", short_daily),
        ("ls", ls_daily),
        ("long_exc", long_exc_daily),
    ]:
        result[f"{prefix}_ann_ret"] = annualized_return(series)
        result[f"{prefix}_max_dd"] = max_drawdown(series)
        result[f"{prefix}_calmar"] = calmar_ratio(series)
        result[f"{prefix}_sharpe"] = sharpe_ratio(series)

    long_exc_ann = result["long_exc_ann_ret"]
    short_exc_ann = annualized_return(short_exc_daily)
    if not pd.isna(long_exc_ann) and not pd.isna(short_exc_ann) and not np.isclose(short_exc_ann, 0.0):
        result["ls_ann_ret_ratio"] = float(long_exc_ann / abs(short_exc_ann))
    else:
        result["ls_ann_ret_ratio"] = float("nan")

    if index_returns is not None:
        idx_exc_daily = long_daily - index_returns.reindex(long_daily.index).fillna(0)
        result["idx_exc_ann_ret"] = annualized_return(idx_exc_daily)
        result["idx_exc_max_dd"] = max_drawdown(idx_exc_daily)
        result["idx_exc_calmar"] = calmar_ratio(idx_exc_daily)
        result["idx_exc_sharpe"] = sharpe_ratio(idx_exc_daily)

    return result


def _extract_quantile_daily(
    mean_ret_by_date: pd.DataFrame,
    quantile: int,
    period: str,
) -> pd.Series:
    """Extract daily return Series for a single quantile from by-date quantile returns."""
    if period not in mean_ret_by_date.columns:
        return pd.Series(dtype=float)
    try:
        return mean_ret_by_date[period].xs(quantile, level="factor_quantile")
    except KeyError:
        return pd.Series(dtype=float)
