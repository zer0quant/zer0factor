from __future__ import annotations

import re
from collections.abc import Hashable

import numpy as np
import pandas as pd
from alphalens.performance import (
    factor_information_coefficient,
    mean_return_by_quantile,
)

from zer0factor.eval.metrics.ic import (
    calculate_ic_freq_win_rates,
    calculate_ic_near_far_ratio,
)
from zer0factor.eval.metrics.monotonicity import (
    calculate_monotonicity,
    calculate_quarterly_monotonicity_stats,
)
from zer0factor.eval.metrics.returns import (
    build_pyfolio_return_metrics,
    detect_direction,
)
from zer0factor.eval.metrics.turnover import calculate_quantile_turnover


def calculate_daily_ic(clean_factor_data: pd.DataFrame) -> pd.DataFrame:
    return factor_information_coefficient(clean_factor_data)


def calculate_quantile_returns(clean_factor_data: pd.DataFrame) -> pd.DataFrame:
    mean_returns, _ = mean_return_by_quantile(clean_factor_data, by_date=False)
    return mean_returns


def calculate_long_short_spread(quantile_returns: pd.DataFrame) -> pd.Series:
    lowest_quantile = quantile_returns.index.min()
    highest_quantile = quantile_returns.index.max()
    return quantile_returns.loc[highest_quantile] - quantile_returns.loc[lowest_quantile]


def build_summary(
    *,
    factor_name: str,
    return_type: str,
    clean_factor_data_sample_count: int,
    clean_factor_data_start: pd.Timestamp,
    clean_factor_data_end: pd.Timestamp,
    quantiles: int,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
    clean_factor_data: pd.DataFrame | None = None,
    index_returns: "pd.Series | None" = None,
    period_sample_counts: dict[str, int] | None = None,
) -> pd.DataFrame:
    lowest_quantile = quantile_returns.index.min()
    highest_quantile = quantile_returns.index.max()
    long_short_spread = calculate_long_short_spread(quantile_returns)
    ic_freq_win_rates = calculate_ic_freq_win_rates(daily_ic)
    ic_near_far_ratio = calculate_ic_near_far_ratio(daily_ic)

    direction = detect_direction(daily_ic)
    sample_counts = period_sample_counts or _calculate_period_sample_counts(clean_factor_data)

    _mean_ret_by_date = None
    if clean_factor_data is not None:
        _mean_ret_by_date, _ = mean_return_by_quantile(
            clean_factor_data,
            by_date=True,
            demeaned=False,
        )

    rows = [
        _build_period_summary(
            factor_name=factor_name,
            return_type=return_type,
            clean_factor_data_sample_count=clean_factor_data_sample_count,
            clean_factor_data_start=clean_factor_data_start,
            clean_factor_data_end=clean_factor_data_end,
            quantiles=quantiles,
            period=period,
            ic_values=daily_ic[period],
            quantile_returns=quantile_returns,
            lowest_quantile=lowest_quantile,
            highest_quantile=highest_quantile,
            long_short_spread=long_short_spread,
            ic_freq_win_rates=ic_freq_win_rates,
            ic_near_far_ratio=ic_near_far_ratio,
            direction=direction,
            period_sample_counts=sample_counts,
            n_quantiles=quantiles,
            mean_ret_by_date=_mean_ret_by_date,
            index_returns=index_returns,
            clean_factor_data=clean_factor_data,
        )
        for period in daily_ic.columns
    ]
    return pd.DataFrame(rows)


def _build_period_summary(
    *,
    factor_name: str,
    return_type: str,
    clean_factor_data_sample_count: int,
    clean_factor_data_start: pd.Timestamp,
    clean_factor_data_end: pd.Timestamp,
    quantiles: int,
    period: Hashable,
    ic_values: pd.Series,
    quantile_returns: pd.DataFrame,
    lowest_quantile: Hashable,
    highest_quantile: Hashable,
    long_short_spread: pd.Series,
    ic_freq_win_rates: dict,
    ic_near_far_ratio: pd.Series,
    direction: int,
    period_sample_counts: dict[str, int],
    n_quantiles: int,
    mean_ret_by_date: pd.DataFrame | None,
    index_returns: pd.Series | None,
    clean_factor_data: pd.DataFrame | None = None,
) -> dict[str, object]:
    ic_mean = ic_values.mean()
    ic_std = ic_values.std()
    valid_count = ic_values.count()
    positive_percent = (ic_values.gt(0).sum() / valid_count * 100) if valid_count else pd.NA
    icir = _safe_ratio(ic_mean, ic_std)
    t_stat = _hac_t_stat(ic_values, max_lag=max(_parse_period_int(str(period)) - 1, 0))
    adjusted_icir = _direction_adjust_value(icir, direction)
    adjusted_t_stat = _direction_adjust_value(t_stat, direction)
    directional_positive_percent = _direction_adjust_win_rate(positive_percent, direction)
    ic_weekly_win_rate = _get_freq_win_rate(ic_freq_win_rates["weekly"], period)
    ic_monthly_win_rate = _get_freq_win_rate(ic_freq_win_rates["monthly"], period)
    raw_spread = long_short_spread[period]
    spread = raw_spread * direction
    long_quantile = highest_quantile if direction == 1 else lowest_quantile
    short_quantile = lowest_quantile if direction == 1 else highest_quantile
    period_key = str(period)

    base = {
        "factor_name": factor_name,
        "return_type": return_type,
        "period": str(period),
        "sample_count": period_sample_counts.get(period_key, clean_factor_data_sample_count),
        "start_date": pd.Timestamp(clean_factor_data_start).strftime("%Y%m%d"),
        "end_date": pd.Timestamp(clean_factor_data_end).strftime("%Y%m%d"),
        "quantiles": quantiles,
        "factor_direction": direction,
        "long_quantile": long_quantile,
        "short_quantile": short_quantile,
        "IC Mean": ic_mean,
        "IC Std": ic_std,
        "adjusted_ICIR": adjusted_icir,
        "adjusted_t-stat": adjusted_t_stat,
        "directional_IC>0 %": directional_positive_percent,
        "mean_return_q1": quantile_returns.loc[lowest_quantile, period],
        "mean_return_qN": quantile_returns.loc[highest_quantile, period],
        "long_short_spread": spread,
        "long_short_spread_bps": spread * 10000,
        "directional_IC>0 %(W)": _direction_adjust_win_rate(ic_weekly_win_rate, direction),
        "directional_IC>0 %(M)": _direction_adjust_win_rate(ic_monthly_win_rate, direction),
        "IC_near_far_ratio": _get_near_far_ratio(ic_near_far_ratio, period),
        "monotonicity": calculate_monotonicity(
            quantile_returns[period],
            direction=direction,
        ),
    }

    if clean_factor_data is not None:
        to_metrics = calculate_quantile_turnover(
            clean_factor_data,
            long_quantile=n_quantiles if direction == 1 else 1,
            short_quantile=1 if direction == 1 else n_quantiles,
            period=str(period),
        )
        base.update(to_metrics)
        base.update(
            build_pyfolio_return_metrics(
                clean_factor_data,
                direction=direction,
                period=str(period),
                long_quantile=int(long_quantile),
                short_quantile=int(short_quantile),
                index_returns=index_returns,
            )
        )

    if mean_ret_by_date is not None:
        q_stats = calculate_quarterly_monotonicity_stats(
            mean_ret_by_date,
            direction=direction,
            period=str(period),
        )
        base.update(q_stats)

    return base


def _safe_ratio(numerator: object, denominator: object) -> object:
    if pd.isna(numerator) or _is_null_or_effectively_zero(denominator):
        return pd.NA
    return numerator / denominator


def _direction_adjust_value(value: object, direction: int) -> object:
    if pd.isna(value):
        return pd.NA
    return value * direction


def _direction_adjust_win_rate(value: object, direction: int) -> object:
    if pd.isna(value):
        return pd.NA
    return value if direction == 1 else 100 - value


def _hac_t_stat(values: pd.Series, *, max_lag: int) -> object:
    clean = values.dropna().astype(float)
    n = len(clean)
    if n < 2:
        return pd.NA
    if max_lag <= 0:
        std = clean.std()
        return _safe_ratio(clean.mean(), std / n**0.5)
    centered = clean - clean.mean()
    gamma0 = float((centered * centered).sum() / n)
    if np.isclose(gamma0, 0.0):
        return pd.NA
    long_run_var = gamma0
    lag_count = min(max_lag, n - 1)
    for lag in range(1, lag_count + 1):
        cov = float((centered.iloc[lag:].to_numpy() * centered.iloc[:-lag].to_numpy()).sum() / n)
        weight = 1 - lag / (lag_count + 1)
        long_run_var += 2 * weight * cov
    if long_run_var <= 0 or np.isclose(long_run_var, 0.0):
        return pd.NA
    return float(clean.mean() / (long_run_var / n) ** 0.5)


def _calculate_period_sample_counts(clean_factor_data: pd.DataFrame | None) -> dict[str, int]:
    if clean_factor_data is None:
        return {}
    counts = {}
    for column in clean_factor_data.columns:
        if re.match(r"^\d+[Dd]$", str(column)):
            counts[str(column)] = int(clean_factor_data[column].count())
    return counts


def _parse_period_int(period: str) -> int:
    m = re.match(r"^(\d+)[Dd]$", period)
    if not m:
        return 1
    return int(m.group(1))


def _is_null_or_effectively_zero(value: object) -> bool:
    return bool(pd.isna(value) or np.isclose(value, 0.0))


def _get_near_far_ratio(ratio_series: pd.Series, period) -> float:
    if period not in ratio_series.index:
        return float("nan")
    val = ratio_series[period]
    return float(val) if not pd.isna(val) else float("nan")


def _get_freq_win_rate(win_rate_series: pd.Series, period) -> object:
    if period not in win_rate_series.index:
        return pd.NA
    val = win_rate_series[period]
    return float(val) if not pd.isna(val) else pd.NA
