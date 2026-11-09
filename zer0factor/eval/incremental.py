"""Incremental evaluation: extend a base run's clean factor data with new dates.

Design 2026-11-09 (decision 2): per-date rows (quantiles, forward returns) of the
base run are kept; only the last ``horizon`` dates of the base and the new dates
are recomputed, then every summary metric is recomputed on the merged data with
the unchanged metric code. The one known difference from a full run is
Alphalens' ``filter_zscore``, a per-asset outlier filter over the loaded window;
a monthly full run resets it (decision 4).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from zer0factor.eval.domain import EvaluationRunConfig

CLEAN_FACTOR_DATA = "clean_factor_data.parquet"
# Settings that change per-date clean rows; they must match the base run.
MATCHED_SETTINGS = ("start_date", "periods", "quantiles", "return_type", "universe", "max_loss")


def evaluation_horizon(config: EvaluationRunConfig) -> int:
    """Trading days the last evaluable date trails the last factor date."""
    return max(config.periods) + (1 if config.return_type == "open_t1" else 0)


def _read_metadata(run_dir: Path) -> dict | None:
    try:
        return json.loads((Path(run_dir) / "metadata.json").read_text())
    except (OSError, ValueError):
        return None


def setting_mismatches(meta: dict, config: EvaluationRunConfig) -> list[str]:
    expected = {
        "start_date": config.start_date,
        "periods": [int(p) for p in config.periods],
        "quantiles": config.quantiles,
        "return_type": config.return_type,
        "universe": config.universe,
        "max_loss": config.max_loss,
    }
    mismatches = []
    for key in MATCHED_SETTINGS:
        actual = meta.get(key)
        if key == "periods":
            actual = [int(str(p).rstrip("Dd")) for p in actual or ()]
        if actual != expected[key]:
            mismatches.append(f"{key}: base={actual!r} requested={expected[key]!r}")
    if meta.get("end_date"):
        mismatches.append(f"end_date: base run is fixed at {meta['end_date']}")
    return mismatches


def find_base_run(output_dir: Path, config: EvaluationRunConfig) -> Path | None:
    """Newest run in ``output_dir`` with a summary and matching settings."""
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return None
    for run_dir in sorted((p for p in output_dir.iterdir() if p.is_dir()), reverse=True):
        if (run_dir / ".cancelled").exists() or not (run_dir / "summary.parquet").exists():
            continue
        meta = _read_metadata(run_dir)
        if meta is not None and not setting_mismatches(meta, config):
            return run_dir
    return None


def check_base_run(base_run_dir: Path, config: EvaluationRunConfig) -> None:
    if len(config.periods) != 1:
        raise ValueError(
            "incremental evaluation supports a single period; per-period sample "
            "counts of multi-period runs are not recoverable from the base run"
        )
    meta = _read_metadata(base_run_dir)
    if meta is None:
        raise ValueError(f"base run has no readable metadata.json: {base_run_dir}")
    if not (Path(base_run_dir) / "summary.parquet").exists():
        raise ValueError(f"base run has no summary.parquet: {base_run_dir}")
    mismatches = setting_mismatches(meta, config)
    if mismatches:
        raise ValueError(
            f"base run {Path(base_run_dir).name} settings differ: " + "; ".join(mismatches)
        )


def shared_load_start(base_run_dir: Path, config: EvaluationRunConfig) -> str:
    """Earliest date any factor's recomputed chunk can start; prices load from here.

    Uses the base summary's end dates (no clean data read) and a generous
    calendar-day margin for the ``horizon`` trading days recomputed per factor.
    """
    try:
        summary = pd.read_parquet(Path(base_run_dir) / "summary.parquet")
        ends = summary.loc[summary["factor_name"].isin(config.factor_names), "end_date"]
        ends = ends.dropna().astype(str)
    except Exception:
        ends = pd.Series(dtype=str)
    if ends.empty:
        return config.start_date
    margin = evaluation_horizon(config) * 2 + 20
    start = (datetime.strptime(ends.min(), "%Y%m%d") - timedelta(days=margin)).strftime("%Y%m%d")
    return max(start, config.start_date)


def chunk_start(base_clean: pd.DataFrame, horizon: int) -> pd.Timestamp | None:
    """First date to recompute: the base's last ``horizon`` dates are redone."""
    dates = base_clean.index.get_level_values("date").unique().sort_values()
    if len(dates) == 0:
        return None
    return dates[max(len(dates) - max(horizon, 1), 0)]


def merge_clean(base_clean: pd.DataFrame, chunk: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    kept = base_clean[base_clean.index.get_level_values("date") < start]
    merged = pd.concat([kept, chunk.loc[:, base_clean.columns]]) if len(chunk) else kept
    for column, dtype in base_clean.dtypes.items():
        if merged[column].dtype != dtype:
            merged[column] = merged[column].astype(dtype)
    return merged


__all__ = [
    "CLEAN_FACTOR_DATA",
    "chunk_start",
    "check_base_run",
    "evaluation_horizon",
    "find_base_run",
    "merge_clean",
    "setting_mismatches",
    "shared_load_start",
]
