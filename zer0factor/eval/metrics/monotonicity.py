from __future__ import annotations

import math

import numpy as np
import pandas as pd


def calculate_monotonicity(
    quantile_returns: pd.Series,
    *,
    direction: int,
) -> float:
    """
    Spearman correlation × direction between quantile rank and return.
    quantile_returns: index=factor_quantile, values=period return
    Returns NaN if fewer than 2 valid data points.
    """
    clean = quantile_returns.dropna()
    if len(clean) < 2:
        return float("nan")
    quantile_order = pd.Series(
        range(1, len(clean) + 1),
        index=clean.index,
        dtype="float64",
    )
    raw = float(quantile_order.corr(clean, method="spearman"))
    return raw * direction


def calculate_quarterly_monotonicity_stats(
    mean_ret_by_date: pd.DataFrame,
    *,
    direction: int,
    period: str,
) -> dict[str, float]:
    """
    Per-quarter cumulative returns → Spearman monotonicity → summary stats.
    mean_ret_by_date: MultiIndex (date, factor_quantile), columns contain period
    Returns NaN stats if fewer than 2 quarters have valid data.
    """
    if period not in mean_ret_by_date.columns:
        return _nan_stats()

    period_ret = mean_ret_by_date[period].unstack(level="factor_quantile")

    quarterly_mono = []
    try:
        grouped = period_ret.groupby(pd.Grouper(freq="QE"))
    except ValueError:
        grouped = period_ret.groupby(pd.Grouper(freq="Q"))

    for _quarter, group in grouped:
        if group.empty:
            continue
        cum_ret = (1 + group).prod(skipna=False) - 1
        if len(cum_ret.dropna()) < 2:
            continue
        quantile_order = pd.Series(
            range(1, len(cum_ret) + 1),
            index=cum_ret.index,
            dtype=float,
        )
        mono = float(quantile_order.corr(cum_ret, method="spearman")) * direction
        if not math.isnan(mono):
            quarterly_mono.append(mono)

    if len(quarterly_mono) < 2:
        return _nan_stats()

    s = pd.Series(quarterly_mono)
    mean = float(s.mean())
    std = float(s.std())
    ir = mean / std if not np.isclose(std, 0.0) else float("nan")
    pos_rate = float((s > 0).mean() * 100)
    gt_50_rate = float((s > 0.5).mean() * 100)

    return {
        "monotonicity_q_mean": mean,
        "monotonicity_q_ir": ir,
        "monotonicity_q_pos_rate": pos_rate,
        "monotonicity_q_gt_50_rate": gt_50_rate,
    }


def _nan_stats() -> dict[str, float]:
    return {
        "monotonicity_q_mean": float("nan"),
        "monotonicity_q_ir": float("nan"),
        "monotonicity_q_pos_rate": float("nan"),
        "monotonicity_q_gt_50_rate": float("nan"),
    }
