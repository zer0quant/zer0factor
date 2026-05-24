from __future__ import annotations

import math
import re

import pandas as pd


def calculate_quantile_turnover(
    clean_factor_data: pd.DataFrame,
    *,
    long_quantile: int,
    short_quantile: int,
    period: str,
) -> dict[str, float]:
    """
    计算多头组和空头组的单边日均换手率及年化换手率。

    换手率定义：symmetric_difference / (2 × max(prev_size, curr_size))。
    """
    period_int = _parse_period_int(period)

    long_daily = _quantile_daily_turnover(clean_factor_data, long_quantile)
    short_daily = _quantile_daily_turnover(clean_factor_data, short_quantile)

    long_mean = float(long_daily.mean()) if len(long_daily) > 0 else float("nan")
    short_mean = float(short_daily.mean()) if len(short_daily) > 0 else float("nan")

    return {
        "turnover_daily_long": long_mean,
        "turnover_annual_long": long_mean * 252 / period_int if not math.isnan(long_mean) else float("nan"),
        "turnover_daily_short": short_mean,
        "turnover_annual_short": short_mean * 252 / period_int if not math.isnan(short_mean) else float("nan"),
    }


def _quantile_daily_turnover(
    clean_factor_data: pd.DataFrame,
    quantile: int,
) -> pd.Series:
    quant_data = clean_factor_data[clean_factor_data["factor_quantile"] == quantile]
    stocks_by_date = (
        quant_data.groupby(level="date")
        .apply(lambda x: set(x.index.get_level_values("asset")))
    )
    dates = stocks_by_date.index.tolist()
    if len(dates) < 2:
        return pd.Series(dtype=float)

    turnovers = []
    for i in range(1, len(dates)):
        prev = stocks_by_date[dates[i - 1]]
        curr = stocks_by_date[dates[i]]
        size = max(len(prev), len(curr), 1)
        sym_diff = len(prev.symmetric_difference(curr))
        turnovers.append(sym_diff / (2 * size))

    return pd.Series(turnovers, index=dates[1:])


def _parse_period_int(period: str) -> int:
    m = re.match(r"^(\d+)[Dd]$", period)
    if not m:
        raise ValueError(f"Cannot parse period '{period}': expected format like '1D' or '5D'")
    return int(m.group(1))
