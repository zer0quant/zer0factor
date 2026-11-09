"""Scan evaluation runs and match them against the board's standard setting."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from loguru import logger

from zer0factor.config import StandardSetting


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    path: Path
    start_date: str | None
    end_date: str | None
    periods: tuple[str, ...]
    quantiles: int | None
    return_type: str | None
    universe: str | None
    transaction_cost_bps: float | None
    factor_names: tuple[str, ...]
    has_summary: bool

    @property
    def summary_path(self) -> Path:
        return self.path / "summary.parquet"

    def factor_dir(self, factor: str) -> Path:
        return self.path / "factors" / factor


def _period_label(value) -> str:
    text = str(value)
    return text if text.endswith("D") else f"{int(text)}D"


def _load_run(run_dir: Path) -> RunInfo | None:
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text())
        factors_dir = run_dir / "factors"
        present = (
            {p.name for p in factors_dir.iterdir() if p.is_dir()} if factors_dir.exists() else set()
        )
        listed = meta.get("factor_names") or sorted(present)
        factor_names = tuple(name for name in listed if name in present)
        cost = meta.get("transaction_cost_bps")
        quantiles = meta.get("quantiles")
        return RunInfo(
            run_id=run_dir.name,
            path=run_dir,
            start_date=meta.get("start_date") or None,
            end_date=meta.get("end_date") or None,
            periods=tuple(_period_label(p) for p in meta.get("periods") or ()),
            quantiles=int(quantiles) if quantiles is not None else None,
            return_type=meta.get("return_type"),
            universe=meta.get("universe"),
            transaction_cost_bps=float(cost) if cost is not None else None,
            factor_names=factor_names,
            has_summary=(run_dir / "summary.parquet").exists(),
        )
    except Exception as exc:
        logger.warning(f"skip evaluation run {run_dir}: {exc!r}")
        return None


CANCELLED_MARKER = ".cancelled"


def scan_runs(evaluations_dir: Path, exclude: frozenset[str] | set[str] = frozenset()) -> list[RunInfo]:
    """Evaluation runs on disk, skipping cancelled runs and ``exclude`` (runs still being written)."""
    evaluations_dir = Path(evaluations_dir)
    if not evaluations_dir.exists():
        return []
    runs = []
    for run_dir in sorted(p for p in evaluations_dir.iterdir() if p.is_dir()):
        if run_dir.name in exclude or (run_dir / CANCELLED_MARKER).exists():
            continue
        run = _load_run(run_dir)
        if run is not None:
            runs.append(run)
    return runs


def is_standard(run: RunInfo, std: StandardSetting, latest_end: str | None = None) -> bool:
    """Matches ``[web.standard]`` and runs to the latest data: no end date, or an end date
    on or after ``latest_end`` (the latest data date any evaluation has reached)."""
    to_latest = run.end_date is None or (latest_end is not None and run.end_date >= latest_end)
    return (
        run.start_date == std.start_date
        and to_latest
        and run.quantiles == std.quantiles
        and run.return_type == std.return_type
        and run.universe == std.universe
        and std.period in run.periods
    )


class SummaryCache:
    def __init__(self) -> None:
        self._entries: dict[Path, tuple[float, pd.DataFrame]] = {}
        self._lock = threading.Lock()

    def get(self, run: RunInfo) -> pd.DataFrame | None:
        path = run.summary_path
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return None
        with self._lock:
            cached = self._entries.get(path)
            if cached and cached[0] == mtime:
                return cached[1]
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            logger.warning(f"cannot read summary {path}: {exc!r}")
            return None
        frame["period"] = frame["period"].astype(str)
        with self._lock:
            self._entries[path] = (mtime, frame)
        return frame


def summary_row(
    run: RunInfo, factor: str, period: str, cache: SummaryCache
) -> dict | None:
    summary = cache.get(run)
    if summary is None:
        return None
    rows = summary[(summary["factor_name"] == factor) & (summary["period"] == period)]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def _yyyymmdd(value) -> str | None:
    try:
        ts = pd.Timestamp(str(value))
    except (TypeError, ValueError):
        return None
    return None if pd.isna(ts) else ts.strftime("%Y%m%d")


def latest_data_end(runs: list[RunInfo], cache: SummaryCache) -> str | None:
    """Latest ``end_date`` in any run's summary (``YYYYMMDD``), i.e. the latest data date."""
    ends = []
    for run in runs:
        if not run.has_summary:
            continue
        summary = cache.get(run)
        if summary is None or "end_date" not in summary:
            continue
        ends += [d for d in map(_yyyymmdd, summary["end_date"].dropna().unique()) if d]
    return max(ends) if ends else None


_UNSET = object()


def standard_rows(
    runs: list[RunInfo], std: StandardSetting, cache: SummaryCache, latest_end=_UNSET
) -> dict[str, tuple[RunInfo, dict]]:
    """Latest standard run's summary row per factor. ``latest_end`` defaults to
    ``latest_data_end(runs, cache)``; pass a precomputed value to skip that scan."""
    result: dict[str, tuple[RunInfo, dict]] = {}
    if latest_end is _UNSET:
        latest_end = latest_data_end(runs, cache)
    for run in sorted(runs, key=lambda r: r.run_id, reverse=True):
        if not run.has_summary or not is_standard(run, std, latest_end):
            continue
        summary = cache.get(run)
        if summary is None:
            continue
        rows = summary[summary["period"] == std.period]
        for row in rows.to_dict("records"):
            name = row["factor_name"]
            if name not in result:
                result[name] = (run, row)
    return result
