"""Sampled cross-sectional Spearman correlation between stored factors."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

THRESHOLD = 0.7


def sample_dates(available: list[str], start: str, end: str, n: int = 60) -> list[str]:
    candidates = sorted(d for d in available if start <= d <= end)
    if len(candidates) <= n:
        return candidates
    idx = np.unique(np.linspace(0, len(candidates) - 1, n).round().astype(int))
    return [candidates[i] for i in idx]


def _partition_dates(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {p.name.removeprefix("date=") for p in directory.iterdir() if p.name.startswith("date=")}


def _read_day(factors: tuple[str, ...], factor_dir: Path, universe_dir: Path, date: str):
    members = pd.read_parquet(universe_dir / f"date={date}", columns=["ts_code"])["ts_code"]
    columns = {}
    for name in factors:
        frame = pd.read_parquet(factor_dir / name / f"date={date}", columns=["ts_code", "value"])
        columns[name] = frame.drop_duplicates("ts_code").set_index("ts_code")["value"]
    day = pd.DataFrame(columns).reindex(pd.Index(members.unique()))
    return day.corr(method="spearman", min_periods=3)


@lru_cache(maxsize=64)
def _cached(
    factors: tuple[str, ...],
    factor_dir: Path,
    universe_dir: Path,
    start: str,
    end: str,
    n_dates: int,
) -> dict:
    available = _partition_dates(universe_dir)
    for name in factors:
        available &= _partition_dates(factor_dir / name)
    dates = sample_dates(sorted(available), start, end, n_dates)
    with ThreadPoolExecutor(max_workers=8) as pool:
        mats = list(pool.map(lambda d: _read_day(factors, factor_dir, universe_dir, d), dates))
    if mats:
        stacked = np.stack([m.loc[list(factors), list(factors)].to_numpy() for m in mats])
        with np.errstate(invalid="ignore"):
            matrix = np.nanmean(stacked, axis=0)
    else:
        matrix = np.full((len(factors), len(factors)), np.nan)
    pairs = [
        {"a": factors[i], "b": factors[j], "rho": float(matrix[i, j])}
        for i in range(len(factors))
        for j in range(i + 1, len(factors))
        if np.isfinite(matrix[i, j]) and abs(matrix[i, j]) >= THRESHOLD
    ]
    return {
        "factors": list(factors),
        "matrix": matrix.tolist(),
        "dates_used": len(dates),
        "start": start,
        "end": end,
        "threshold": THRESHOLD,
        "pairs_over_threshold": pairs,
    }


def factor_correlation(
    factors: list[str],
    factor_dir: Path,
    universe_dir: Path,
    ranges: dict[str, tuple[str, str]],
    n_dates: int = 60,
) -> dict:
    start = max(ranges[f][0] for f in factors)
    end = min(ranges[f][1] for f in factors)
    return _cached(tuple(factors), Path(factor_dir), Path(universe_dir), start, end, n_dates)
