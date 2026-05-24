from __future__ import annotations

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
) -> pd.DataFrame:
    lowest_quantile = quantile_returns.index.min()
    highest_quantile = quantile_returns.index.max()
    long_short_spread = calculate_long_short_spread(quantile_returns)
    ic_freq_win_rates = calculate_ic_freq_win_rates(daily_ic)
    ic_near_far_ratio = calculate_ic_near_far_ratio(daily_ic)

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
) -> dict[str, object]:
    ic_mean = ic_values.mean()
    ic_std = ic_values.std()
    valid_count = ic_values.count()
    positive_percent = (ic_values.gt(0).sum() / valid_count * 100) if valid_count else pd.NA
    icir = _safe_ratio(ic_mean, ic_std)
    t_stat = (
        _safe_ratio(ic_mean, ic_std / valid_count**0.5)
        if valid_count and not _is_null_or_effectively_zero(ic_std)
        else pd.NA
    )
    spread = long_short_spread[period]

    return {
        "factor_name": factor_name,
        "return_type": return_type,
        "period": str(period),
        "sample_count": clean_factor_data_sample_count,
        "start_date": pd.Timestamp(clean_factor_data_start).strftime("%Y%m%d"),
        "end_date": pd.Timestamp(clean_factor_data_end).strftime("%Y%m%d"),
        "quantiles": quantiles,
        "IC Mean": ic_mean,
        "IC Std": ic_std,
        "ICIR": icir,
        "t-stat": t_stat,
        "IC>0 %": positive_percent,
        "mean_return_q1": quantile_returns.loc[lowest_quantile, period],
        "mean_return_qN": quantile_returns.loc[highest_quantile, period],
        "long_short_spread": spread,
        "long_short_spread_bps": spread * 10000,
        "IC>0 %(W)": _get_freq_win_rate(ic_freq_win_rates["weekly"], period),
        "IC>0 %(M)": _get_freq_win_rate(ic_freq_win_rates["monthly"], period),
        "IC_near_far_ratio": float(ic_near_far_ratio[period]) if period in ic_near_far_ratio.index and not pd.isna(ic_near_far_ratio[period]) else pd.NA,
    }


def _safe_ratio(numerator: object, denominator: object) -> object:
    if pd.isna(numerator) or _is_null_or_effectively_zero(denominator):
        return pd.NA
    return numerator / denominator


def _is_null_or_effectively_zero(value: object) -> bool:
    return bool(pd.isna(value) or np.isclose(value, 0.0))


def _get_freq_win_rate(win_rate_series: pd.Series, period) -> object:
    if period not in win_rate_series.index:
        return pd.NA
    val = win_rate_series[period]
    return float(val) if not pd.isna(val) else pd.NA
