"""Daily time series behind the web workbench charts.

Group curves use equal-weight gross returns; long/short/ls curves reuse the
cost-adjusted portfolio construction behind the summary metrics, so charts and
metric cards agree.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from zer0factor.eval.metrics.returns import build_portfolio_daily_returns, portfolio_key

SERIES_FILES = (
    "quantile_daily_returns.parquet",
    "daily_ic_pearson.parquet",
    "portfolio_daily_returns.parquet",
)
PORTFOLIO_COLUMNS = ["long", "short", "ls", "benchmark"]


def _period_int(period: str) -> int:
    return int(str(period).rstrip("D"))


def _period_columns(clean_factor_data: pd.DataFrame) -> list[str]:
    return [c for c in clean_factor_data.columns if c not in ("factor", "factor_quantile", "group")]


def quantile_daily_returns(clean_factor_data: pd.DataFrame, period: str) -> pd.DataFrame:
    mean = clean_factor_data.groupby(["date", "factor_quantile"])[period].mean().unstack()
    mean.columns = [int(c) for c in mean.columns]
    n = _period_int(period)
    if n > 1:
        mean = (1 + mean) ** (1 / n) - 1
    return mean


def pearson_daily_ic(clean_factor_data: pd.DataFrame) -> pd.DataFrame:
    periods = _period_columns(clean_factor_data)

    def one_day(day: pd.DataFrame) -> pd.Series:
        return pd.Series({p: day["factor"].corr(day[p]) for p in periods})

    ic = clean_factor_data.groupby(level="date").apply(one_day)
    ic.columns = periods
    return ic


def portfolio_daily_returns(
    clean_factor_data: pd.DataFrame,
    summary_row: Mapping,
    precomputed: Mapping | None = None,
) -> pd.DataFrame:
    """Long/short/ls/benchmark daily returns for one summary row.

    ``precomputed`` holds series the summary already built (see
    ``build_pyfolio_return_metrics(portfolio_sink=...)``); a match by
    period, direction, quantiles and cost is reused as is.
    """
    params = dict(
        direction=int(summary_row["factor_direction"]),
        period=str(summary_row["period"]),
        long_quantile=int(summary_row["long_quantile"]),
        short_quantile=int(summary_row["short_quantile"]),
        transaction_cost_bps=float(summary_row.get("transaction_cost_bps") or 0.0),
    )
    series = None
    if precomputed:
        series = precomputed.get(
            portfolio_key(
                params["period"],
                params["direction"],
                params["long_quantile"],
                params["short_quantile"],
                params["transaction_cost_bps"],
            )
        )
    if series is None:
        series = build_portfolio_daily_returns(clean_factor_data, **params, include_full=False)
    frame = pd.DataFrame({"long": series.long, "short": series.short, "ls": series.ls})
    frame["benchmark"] = (
        series.benchmark.reindex(frame.index) if series.benchmark is not None else np.nan
    )
    return frame[PORTFOLIO_COLUMNS]


def build_chart_series(
    clean_factor_data: pd.DataFrame,
    summary: pd.DataFrame,
    portfolio: Mapping | None = None,
) -> dict[str, pd.DataFrame]:
    quantile_parts = []
    portfolio_parts = []
    for row in summary.to_dict("records"):
        period = str(row["period"])
        if period not in clean_factor_data.columns:
            continue
        q = quantile_daily_returns(clean_factor_data, period)
        q.columns = [f"{period}:{c}" for c in q.columns]
        quantile_parts.append(q)
        try:
            p = portfolio_daily_returns(clean_factor_data, row, portfolio)
        except Exception:
            p = pd.DataFrame(index=q.index, columns=PORTFOLIO_COLUMNS, dtype=float)
        p.columns = [f"{period}:{c}" for c in p.columns]
        portfolio_parts.append(p)
    quantile = pd.concat(quantile_parts, axis=1) if quantile_parts else pd.DataFrame()
    portfolio = pd.concat(portfolio_parts, axis=1) if portfolio_parts else pd.DataFrame()
    for frame in (quantile, portfolio):
        frame.index.name = "date"
    return {
        "quantile_daily_returns": quantile,
        "daily_ic_pearson": pearson_daily_ic(clean_factor_data),
        "portfolio_daily_returns": portfolio,
    }


def write_chart_series(directory: Path, series: dict[str, pd.DataFrame]) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in series.items():
        target = directory / f"{name}.parquet"
        tmp = directory / f"{name}.parquet.tmp-{uuid.uuid4().hex}"
        try:
            frame.to_parquet(tmp)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)


def read_chart_series(directory: Path) -> dict[str, pd.DataFrame] | None:
    directory = Path(directory)
    paths = [directory / name for name in SERIES_FILES]
    if not all(p.exists() for p in paths):
        return None
    return {p.name.removesuffix(".parquet"): pd.read_parquet(p) for p in paths}
