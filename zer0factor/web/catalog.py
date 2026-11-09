"""Factor catalog: stored factors + registry metadata + standard evaluation rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property

from loguru import logger

from zer0factor.config import Config, StandardSetting
from zer0factor.registry import FactorMeta, FactorRegistry
from zer0factor.web.runs import (
    RunInfo,
    SummaryCache,
    is_standard,
    latest_data_end,
    scan_runs,
    standard_rows,
)

# summary column -> board field
BOARD_COLUMNS: dict[str, str] = {
    "adjusted_ICIR": "icir",
    "adjusted_t-stat": "t_stat",
    "directional_IC>0 %": "ic_win_rate",
    "ls_ann_ret": "ls_ann_ret",
    "ls_max_dd": "ls_max_dd",
    "ls_sharpe": "ls_sharpe",
    "long_ann_ret": "long_ann_ret",
    "long_max_dd": "long_max_dd",
    "long_sharpe": "long_sharpe",
    "long_exc_ann_ret": "long_exc_ann_ret",
    "monotonicity": "monotonicity",
    "turnover_daily_long": "turnover_long",
    "start_date": "start_date",
    "end_date": "end_date",
}


def _load_registry(cfg: Config) -> dict[str, FactorMeta]:
    try:
        return {m.name: m for m in FactorRegistry(cfg.web.registry_path).all()}
    except Exception as exc:
        logger.warning(f"factor registry unavailable ({cfg.web.registry_path}): {exc!r}")
        return {}


def _value(row: dict, key: str):
    value = row.get(key)
    try:
        return None if value is None or value != value else value
    except (TypeError, ValueError):
        return None


@dataclass
class Catalog:
    factor_names: list[str]
    runs: list[RunInfo]
    scanned_at: datetime
    standard: StandardSetting
    registry: dict[str, FactorMeta] = field(default_factory=dict)
    summary_cache: SummaryCache = field(default_factory=SummaryCache)

    def __post_init__(self) -> None:
        self._factor_set = set(self.factor_names)
        self._runs_by_id = {r.run_id: r for r in self.runs}

    def has_factor(self, name: str) -> bool:
        return name in self._factor_set

    def get_run(self, run_id: str) -> RunInfo | None:
        return self._runs_by_id.get(run_id)

    def runs_for(self, factor: str) -> list[RunInfo]:
        return sorted(
            (r for r in self.runs if factor in r.factor_names),
            key=lambda r: r.run_id,
            reverse=True,
        )

    @cached_property
    def latest_end(self) -> str | None:
        """Latest data date any run reached; fixed per catalog (rebuilt on rescan)."""
        return latest_data_end(self.runs, self.summary_cache)

    def is_standard(self, run: RunInfo) -> bool:
        return is_standard(run, self.standard, self.latest_end)

    def standard_rows(self) -> dict[str, tuple[RunInfo, dict]]:
        return standard_rows(self.runs, self.standard, self.summary_cache, self.latest_end)

    def meta(self, name: str) -> dict:
        m = self.registry.get(name)
        return {
            "category": m.category if m else None,
            "tags": list(m.tags) if m else [],
            "description": m.description if m else "",
        }

    def board_row(self, name: str, hit: tuple[RunInfo, dict] | None) -> dict:
        row = {"name": name, **self.meta(name), "evaluated": hit is not None}
        summary = hit[1] if hit else {}
        direction = _value(summary, "factor_direction")
        ic_mean = _value(summary, "IC Mean")
        row["direction"] = int(direction) if direction is not None else None
        row["ic_adj"] = (
            float(ic_mean) * int(direction) if ic_mean is not None and direction else None
        )
        for column, key in BOARD_COLUMNS.items():
            row[key] = _value(summary, column)
        row["run_id"] = hit[0].run_id if hit else None
        return row

    def board_rows(self) -> list[dict]:
        hits = self.standard_rows()
        return [self.board_row(name, hits.get(name)) for name in self.factor_names]


def build_catalog(cfg: Config, exclude_runs: frozenset[str] | set[str] = frozenset()) -> Catalog:
    factor_dir = cfg.factor_dir
    names = (
        sorted(p.name for p in factor_dir.iterdir() if p.is_dir()) if factor_dir.exists() else []
    )
    return Catalog(
        factor_names=names,
        runs=scan_runs(cfg.web.evaluations_dir, exclude=exclude_runs),
        scanned_at=datetime.now(),
        standard=cfg.web.standard,
        registry=_load_registry(cfg),
    )
