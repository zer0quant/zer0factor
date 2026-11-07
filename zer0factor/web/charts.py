"""Data behind the single-factor detail page."""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from zer0factor.eval.series import (
    SERIES_FILES,
    build_chart_series,
    read_chart_series,
    write_chart_series,
)
from zer0factor.web.runs import RunInfo

TRADING_DAYS = 252
MONTHLY_THRESHOLD = 500
DECAY_MAX_ROWS = 500
_locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks[path]


def _cache_path(cache_dir: Path, run: RunInfo, factor: str) -> Path:
    return Path(cache_dir) / run.run_id / factor


def _clean_path(run: RunInfo, factor: str) -> Path:
    return run.factor_dir(factor) / "clean_factor_data.parquet"


def _write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        tmp.write_text(json.dumps(data))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _derive(run: RunInfo, factor: str, cache_dir: Path, summary: pd.DataFrame) -> bool:
    """Compute and cache series + IC decay from clean_factor_data. False if no raw data."""
    path = _clean_path(run, factor)
    if not path.exists():
        return False
    target = _cache_path(cache_dir, run, factor)
    cfd = pd.read_parquet(path)
    factor_summary = summary[summary["factor_name"] == factor]
    if read_chart_series(run.factor_dir(factor)) is None and read_chart_series(target) is None:
        write_chart_series(target, build_chart_series(cfd, factor_summary))
    if not (target / "ic_decay.json").exists():
        _write_json_atomic(target / "ic_decay.json", ic_decay(cfd))
    return True


def cached_series(run: RunInfo, factor: str, cache_dir: Path) -> dict[str, pd.DataFrame] | None:
    """Series already on disk (run dir or web cache); never derives."""
    return read_chart_series(run.factor_dir(factor)) or read_chart_series(
        _cache_path(cache_dir, run, factor)
    )


def detail_cached(run: RunInfo, factor: str, cache_dir: Path) -> bool:
    """True when the detail page can be served from disk (series + IC decay), without deriving."""
    target = _cache_path(cache_dir, run, factor)
    has_series = any(
        all((Path(d) / name).exists() for name in SERIES_FILES)
        for d in (run.factor_dir(factor), target)
    )
    return has_series and (target / "ic_decay.json").exists()


def ls_sparkline(
    run: RunInfo, factor: str, period: str, cache_dir: Path, points: int = 60
) -> list[float | None] | None:
    """Cumulative long-short return, evenly downsampled to ``points`` values. Cache only."""
    for directory in (run.factor_dir(factor), _cache_path(cache_dir, run, factor)):
        path = Path(directory) / "portfolio_daily_returns.parquet"
        if path.exists():
            break
    else:
        return None
    column = f"{period}:ls"
    frame = pd.read_parquet(path)
    if column not in frame:
        return None
    cum = (1 + frame[column].fillna(0)).cumprod() - 1
    if cum.empty:
        return None
    idx = np.unique(np.linspace(0, len(cum) - 1, min(points, len(cum))).round().astype(int))
    return [_finite(v) for v in cum.iloc[idx]]


def get_series(
    run: RunInfo, factor: str, cache_dir: Path, summary: pd.DataFrame
) -> dict[str, pd.DataFrame] | None:
    own = read_chart_series(run.factor_dir(factor))
    if own is not None:
        return own
    target = _cache_path(cache_dir, run, factor)
    cached = read_chart_series(target)
    if cached is not None:
        return cached
    with _lock_for(target):
        cached = read_chart_series(target)
        if cached is not None:
            return cached
        if not _derive(run, factor, cache_dir, summary):
            return None
        return read_chart_series(target)


def get_decay(
    run: RunInfo, factor: str, cache_dir: Path, summary: pd.DataFrame
) -> dict | None:
    target = _cache_path(cache_dir, run, factor)
    path = target / "ic_decay.json"
    if not path.exists():
        with _lock_for(target):
            if not path.exists() and not _derive(run, factor, cache_dir, summary):
                return None
    return json.loads(path.read_text())


def _row_corr(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    a = a - a.mean(axis=1).to_numpy()[:, None]
    b = b - b.mean(axis=1).to_numpy()[:, None]
    num = (a * b).sum(axis=1)
    den = np.sqrt((a**2).sum(axis=1) * (b**2).sum(axis=1))
    return num / den.replace(0, np.nan)


def ic_decay(clean_factor_data: pd.DataFrame, max_lag: int = 20) -> dict:
    """Mean cross-sectional IC of factor_t against the 1-day return k days later.

    On long histories the factor dates are sampled evenly (every ``step``-th day,
    ~DECAY_MAX_ROWS rows) — an unbiased estimate of the mean that keeps the
    per-lag cross-sectional ranking affordable.
    """
    periods = [c for c in clean_factor_data.columns if c not in ("factor", "factor_quantile")]
    ret_col = "1D" if "1D" in periods else periods[0]
    factor = clean_factor_data["factor"].unstack()
    ret = clean_factor_data[ret_col].unstack().reindex(index=factor.index, columns=factor.columns)
    step = max(1, len(factor) // DECAY_MAX_ROWS)
    rows = factor.index[::step]
    out: dict[str, list] = {"rank": [], "ic": [], "sampled_step": step}
    for lag in range(max_lag + 1):
        shifted = ret.shift(-lag).loc[rows]
        sampled = factor.loc[rows]
        mask = sampled.notna() & shifted.notna()
        f, r = sampled.where(mask), shifted.where(mask)
        pearson = _row_corr(f, r)
        spearman = _row_corr(f.rank(axis=1), r.rank(axis=1))
        out["ic"].append(_finite(pearson.mean()))
        out["rank"].append(_finite(spearman.mean()))
    return out


def _finite(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def autocorr_with_ci(series: pd.Series, max_lag: int = 23) -> dict:
    s = series.dropna()
    n = len(s)
    acf = [_finite(s.autocorr(lag)) if lag else (1.0 if n else None) for lag in range(max_lag + 1)]
    return {"acf": acf, "ci": 1.96 / np.sqrt(n) if n else None}


def histogram_with_normal(series: pd.Series, bins: int = 40) -> dict:
    s = series.dropna()
    if s.empty:
        return {"edges": [], "density": [], "normal": []}
    density, edges = np.histogram(s, bins=bins, density=True)
    centers = (edges[:-1] + edges[1:]) / 2
    mu, sigma = s.mean(), s.std()
    if sigma and np.isfinite(sigma):
        normal = np.exp(-((centers - mu) ** 2) / (2 * sigma**2)) / (sigma * np.sqrt(2 * np.pi))
    else:
        normal = np.full_like(centers, np.nan)
    return {"edges": edges.tolist(), "density": density.tolist(), "normal": normal.tolist()}


def _perf(r: pd.Series, benchmark: pd.Series | None) -> dict:
    r = r.dropna()
    if r.empty:
        return {k: None for k in ("ann_ret", "exc_ann_ret", "max_dd", "ann_vol", "sharpe")}
    years = len(r) / TRADING_DAYS
    nav = (1 + r).cumprod()
    ann_ret = nav.iloc[-1] ** (1 / years) - 1
    max_dd = float((nav / nav.cummax() - 1).min())  # negative, same sign as summary *_max_dd
    std = r.std()
    exc = None
    if benchmark is not None:
        b = benchmark.reindex(r.index)
        if b.notna().any():
            exc_r = r - b.fillna(0)
            exc = (1 + exc_r).prod() ** (1 / years) - 1
    return {
        "ann_ret": _finite(ann_ret),
        "exc_ann_ret": _finite(exc),
        "max_dd": min(max_dd, 0.0),
        "ann_vol": _finite(std * np.sqrt(TRADING_DAYS)),
        "sharpe": _finite(r.mean() / std * np.sqrt(TRADING_DAYS)) if std else None,
    }


def group_table(qret: pd.DataFrame, port: pd.DataFrame) -> list[dict]:
    benchmark = port["benchmark"] if "benchmark" in port else None
    rows = [{"group": str(g), **_perf(qret[g], benchmark)} for g in qret.columns]
    if "ls" in port:
        rows.append({"group": "多空", **_perf(port["ls"], None)})
    return rows


def _period_frame(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    prefix = f"{period}:"
    cols = [c for c in frame.columns if str(c).startswith(prefix)]
    out = frame[cols].copy()
    out.columns = [str(c)[len(prefix):] for c in cols]
    return out


def _cum(r: pd.Series) -> list:
    return ((1 + r.fillna(0)).cumprod() - 1).tolist()


def _dates(index) -> list[str]:
    return [pd.Timestamp(d).strftime("%Y-%m-%d") for d in index]


def _ic_block(ic: pd.Series | None, decay: list | None) -> dict:
    if ic is None:
        return {"series": None, "monthly": False, "hist": None, "acf": None, "decay": decay}
    ic = ic.astype(float)
    ic.index = pd.to_datetime(ic.index)
    cumulative = ic.fillna(0).cumsum()
    monthly = len(ic) > MONTHLY_THRESHOLD
    values = ic.resample("ME").mean() if monthly else ic
    cum = cumulative.resample("ME").last() if monthly else cumulative
    return {
        "series": {
            "dates": _dates(values.index),
            "values": values.tolist(),
            "cumulative": cum.tolist(),
        },
        "monthly": monthly,
        "hist": histogram_with_normal(ic),
        "acf": autocorr_with_ci(ic),
        "decay": decay,
    }


def detail_payload(
    run: RunInfo, factor: str, period: str, cache_dir: Path, summary: pd.DataFrame
) -> dict:
    rows = summary[(summary["factor_name"] == factor) & (summary["period"] == period)]
    row = rows.iloc[0].to_dict() if not rows.empty else {}
    cost = row.get("transaction_cost_bps", run.transaction_cost_bps) or 0
    notes = [
        "分组曲线为等权毛收益（未扣费）",
        f"多头/空头/多空为扣费后组合收益（单边 {float(cost):g}bps）",
    ]

    rank_ic = None
    ic_path = run.factor_dir(factor) / "daily_ic.parquet"
    if ic_path.exists():
        daily_ic = pd.read_parquet(ic_path)
        if period in daily_ic.columns:
            rank_ic = daily_ic[period]

    try:
        series = get_series(run, factor, cache_dir, summary)
        decay = get_decay(run, factor, cache_dir, summary) if series is not None else None
    except Exception as exc:
        logger.warning(f"chart series unavailable for {run.run_id}/{factor}: {exc!r}")
        series, decay = None, None

    if decay and decay.get("sampled_step", 1) > 1:
        notes.append(f"IC 衰减按每 {decay['sampled_step']} 个交易日抽样计算")

    cumulative = None
    table = None
    pearson = None
    if series is not None:
        qret = _period_frame(series["quantile_daily_returns"], period)
        port = _period_frame(series["portfolio_daily_returns"], period)
        qret = qret[sorted(qret.columns, key=int)]
        qret.columns = [int(c) for c in qret.columns]
        index = qret.index.union(port.index)
        cumulative = {
            "dates": _dates(index),
            "groups": {str(g): _cum(qret[g].reindex(index)) for g in qret.columns},
            **{k: _cum(port[k].reindex(index)) for k in ("long", "short", "ls") if k in port},
        }
        table = group_table(qret, port)
        if period in series["daily_ic_pearson"].columns:
            pearson = series["daily_ic_pearson"][period]

    return {
        "summary": row,
        "direction": row.get("factor_direction"),
        "period": period,
        "notes": notes,
        "cumulative": cumulative,
        "group_table": table,
        "rank_ic": _ic_block(rank_ic, decay["rank"] if decay else None),
        "ic": _ic_block(pearson, decay["ic"] if decay else None),
    }


def latest_values(
    run: RunInfo,
    factor: str,
    names: Mapping[str, str],
    page: int,
    size: int,
    cache_dir: Path,
) -> dict:
    target = _cache_path(cache_dir, run, factor) / "latest.parquet"
    if target.exists():
        latest = pd.read_parquet(target)
    else:
        path = _clean_path(run, factor)
        if not path.exists():
            return {"date": None, "total": 0, "items": []}
        cfd = pd.read_parquet(path, columns=["factor", "factor_quantile"])
        last = cfd.index.get_level_values("date").max()
        latest = cfd.xs(last, level="date").reset_index()
        latest["date"] = pd.Timestamp(last)
        latest = latest.sort_values("factor", ascending=False, kind="stable")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"latest.parquet.tmp-{uuid.uuid4().hex}")
        try:
            latest.to_parquet(tmp, index=False)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
    start = max(page - 1, 0) * size
    chunk = latest.iloc[start : start + size]
    return {
        "date": pd.Timestamp(latest["date"].iloc[0]).strftime("%Y-%m-%d") if len(latest) else None,
        "total": len(latest),
        "items": [
            {
                "ts_code": r["asset"],
                "name": names.get(r["asset"]),
                "value": _finite(r["factor"]),
                "quantile": int(r["factor_quantile"]),
            }
            for r in chunk.to_dict("records")
        ],
    }


def load_stock_names(zer0share_data_dir: Path) -> dict[str, str]:
    path = Path(zer0share_data_dir) / "stock" / "basic" / "data.parquet"
    try:
        frame = pd.read_parquet(path, columns=["ts_code", "name"])
    except Exception as exc:
        logger.warning(f"stock names unavailable ({path}): {exc!r}")
        return {}
    return dict(zip(frame["ts_code"], frame["name"]))
