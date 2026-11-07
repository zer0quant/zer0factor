"""Deterministic synthetic Alphalens-shaped data for evaluation tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_clean_factor_data(
    n_dates: int = 80,
    n_assets: int = 40,
    quantiles: int = 5,
    periods: tuple[str, ...] = ("1D", "5D"),
    seed: int = 7,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_dates)
    assets = [f"{i:06d}.SZ" for i in range(n_assets)]
    index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    factor = rng.normal(size=len(index))
    frame = pd.DataFrame({"factor": factor}, index=index)
    for period in periods:
        n = int(period.rstrip("D"))
        noise = rng.normal(scale=0.01 * np.sqrt(n), size=len(index))
        frame[period] = 0.001 * n * factor + noise
    frame["factor_quantile"] = (
        frame.groupby(level="date")["factor"]
        .transform(lambda s: pd.qcut(s, quantiles, labels=False) + 1)
        .astype(int)
    )
    return frame[[*periods, "factor", "factor_quantile"]]
