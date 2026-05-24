from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_ic_freq_win_rates(daily_ic: pd.DataFrame) -> dict[str, pd.Series]:
    """
    返回按周/月重采样后的 IC 胜率（%）。
    daily_ic: index=date, columns=period labels
    """
    return {
        "weekly": _win_rate_by_freq(daily_ic, "W"),
        "monthly": _win_rate_by_freq(daily_ic, "ME"),
    }


def calculate_ic_near_far_ratio(daily_ic: pd.DataFrame) -> pd.Series:
    """
    近远期比值：每个周期的 IC 序列前半段均值 / 全段均值。
    衡量因子有效性的时间稳定性，> 1 表示近期更有效。
    """
    ratios = {}
    for period in daily_ic.columns:
        series = daily_ic[period].dropna()
        if len(series) < 2:
            ratios[period] = float("nan")
            continue
        full_mean = series.mean()
        if np.isclose(full_mean, 0.0) or pd.isna(full_mean):
            ratios[period] = float("nan")
            continue
        half = len(series) // 2
        near_mean = series.iloc[:half].mean()
        ratios[period] = float(near_mean / full_mean)
    return pd.Series(ratios)


def _win_rate_by_freq(daily_ic: pd.DataFrame, freq: str) -> pd.Series:
    resampled = daily_ic.resample(freq).mean()
    count = resampled.count()
    positive = resampled.gt(0).sum()
    result = (positive / count * 100).where(count > 0, other=float("nan"))
    return result
