"""Cut-off date consistency across market data, universes, factors and evaluations.

Everything is read from ``date=YYYYMMDD`` partition directory names, so a check
takes milliseconds. The rule (design 2026-11-09, decision 1): the target date is
``min(market, universe)``; a lagging universe raises an alert, and downstream
updates stop at the universe's cut-off instead of failing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from zer0factor.storage import last_partition_date, partition_dates

MARKET_TABLES = ("daily_kline", "daily_basic", "adj_factor")
BASE_FACTORS = (
    "daily_return",
    "open_return",
    "intraday_return",
    "overnight_return",
    "log_total_market_cap",
    "log_circulating_market_cap",
    "z_log_total_market_cap",
    "z_log_circulating_market_cap",
)
BASE_GROUP = "基础因子（收益率、市值）"


@dataclass(frozen=True)
class FactorGroupStatus:
    name: str
    first_last_date: str | None  # min last date over the group's built outputs
    latest_date: str | None  # max last date over the group's built outputs
    built: int
    lagging: tuple[str, ...]  # outputs whose last date is before the target


@dataclass(frozen=True)
class EvaluationStatus:
    run_id: str
    data_end_date: str | None
    factors_end_date: str | None  # min last date of the run's factors
    expected_end_date: str | None  # latest date the run can cover given the horizon


@dataclass(frozen=True)
class FreshnessReport:
    market: Mapping[str, str | None]
    universes: Mapping[str, str | None]
    factor_groups: tuple[FactorGroupStatus, ...]
    evaluation: EvaluationStatus | None
    market_end: str | None
    universe_end: str | None
    target_end: str | None
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {
            "market": dict(self.market),
            "universes": dict(self.universes),
            "market_end": self.market_end,
            "universe_end": self.universe_end,
            "target_end": self.target_end,
            "factor_groups": [
                {
                    "name": g.name,
                    "first_last_date": g.first_last_date,
                    "latest_date": g.latest_date,
                    "built": g.built,
                    "lagging": list(g.lagging),
                }
                for g in self.factor_groups
            ],
            "evaluation": None
            if self.evaluation is None
            else {
                "run_id": self.evaluation.run_id,
                "data_end_date": self.evaluation.data_end_date,
                "factors_end_date": self.evaluation.factors_end_date,
                "expected_end_date": self.evaluation.expected_end_date,
            },
            "issues": list(self.issues),
            "ok": self.ok,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _min(values: Iterable[str | None]) -> str | None:
    present = [v for v in values if v]
    return min(present) if present else None


def check_freshness(
    *,
    zer0share_data_dir: Path,
    factor_dir: Path,
    universes: Iterable[str],
    factor_groups: Mapping[str, Iterable[str]],
    evaluation: tuple[str, str | None, tuple[str, ...], int] | None = None,
) -> FreshnessReport:
    """Compare cut-off dates.

    ``factor_groups`` maps a group name to its output factor names; outputs never
    built are ignored. ``evaluation`` is ``(run_id, data_end_date, factor_names,
    horizon)`` of the latest standard run, or None when there is none. ``horizon``
    is how many trading days the last evaluated date trails the last factor date
    (forward returns are unknown for the newest dates).
    """
    stock_dir = Path(zer0share_data_dir) / "stock"
    factor_dir = Path(factor_dir)
    issues: list[str] = []

    market = {t: last_partition_date(stock_dir / t) for t in MARKET_TABLES}
    missing_tables = [t for t, d in market.items() if d is None]
    if missing_tables:
        issues.append(f"行情表没有数据：{', '.join(missing_tables)}")
    market_end = None if missing_tables else _min(market.values())

    universe_names = list(dict.fromkeys(universes))
    universe_dates = {
        name: last_partition_date(stock_dir / "universe" / f"name={name}")
        for name in universe_names
    }
    missing_universes = [n for n, d in universe_dates.items() if d is None]
    if missing_universes:
        issues.append(f"股票池没有数据：{', '.join(missing_universes)}")
    universe_end = None if missing_universes else _min(universe_dates.values())

    if market_end and universe_end and universe_end < market_end:
        lagging = ", ".join(
            f"{n} 截止 {d}" for n, d in universe_dates.items() if d and d < market_end
        )
        issues.append(
            f"股票池落后于行情（行情截止 {market_end}）：{lagging}。"
            f"下游只更新到 {universe_end}；请在 zer0share 运行 build-universe 续建"
        )

    target_end = _min([market_end, universe_end]) if market_end and universe_end else None

    factor_last: dict[str, str | None] = {}
    groups: list[FactorGroupStatus] = []
    for group_name, names in factor_groups.items():
        dates = {}
        for name in dict.fromkeys(names):
            if name not in factor_last:
                factor_last[name] = last_partition_date(factor_dir / name)
            if factor_last[name] is not None:
                dates[name] = factor_last[name]
        if not dates:
            continue
        lagging_names = tuple(
            sorted(n for n, d in dates.items() if target_end and d < target_end)
        )
        status = FactorGroupStatus(
            name=group_name,
            first_last_date=min(dates.values()),
            latest_date=max(dates.values()),
            built=len(dates),
            lagging=lagging_names,
        )
        groups.append(status)
        if lagging_names:
            issues.append(
                f"因子落后：{group_name} 有 {len(lagging_names)}/{len(dates)} 个因子"
                f"截止早于 {target_end}（最早 {status.first_last_date}），待增量构建"
            )

    eval_status = None
    if evaluation is not None:
        run_id, data_end, factor_names, horizon = evaluation
        for name in factor_names:
            if name not in factor_last:
                factor_last[name] = last_partition_date(factor_dir / name)
        built = [n for n in factor_names if factor_last.get(n)]
        factors_end = _min(factor_last[n] for n in built)
        expected_end = None
        if factors_end:
            oldest = min(built, key=lambda n: factor_last[n])
            dates = partition_dates(factor_dir / oldest)
            expected_end = dates[max(len(dates) - 1 - max(horizon, 0), 0)]
        eval_status = EvaluationStatus(run_id, data_end, factors_end, expected_end)
        if data_end and expected_end and data_end < expected_end:
            issues.append(
                f"评估落后：标准评估 {run_id} 截止 {data_end}，"
                f"其因子已更新到 {factors_end}（评估最多可到 {expected_end}），待增量评估"
            )
    else:
        issues.append("没有找到标准口径的评估 run")

    return FreshnessReport(
        market=market,
        universes=universe_dates,
        factor_groups=tuple(groups),
        evaluation=eval_status,
        market_end=market_end,
        universe_end=universe_end,
        target_end=target_end,
        issues=tuple(issues),
    )


def evaluation_horizon(periods: Iterable[str], return_type: str | None) -> int:
    """Trading days between the last evaluable date and the last factor date.

    An N-day forward return at t needs the price N days later; ``open_t1`` prices
    a date by the next day's open, adding one more day.
    """
    longest = max((int(str(p).rstrip("Dd")) for p in periods), default=1)
    return longest + (1 if return_type == "open_t1" else 0)


def latest_standard_evaluation(
    evaluations_dir: Path, standard
) -> tuple[str, str | None, tuple[str, ...], int] | None:
    """``(run_id, data_end_date, factor_names, horizon)`` of the newest standard run."""
    from zer0factor.web.runs import is_standard, scan_runs

    runs = [
        r for r in scan_runs(Path(evaluations_dir)) if r.has_summary and is_standard(r, standard)
    ]
    if not runs:
        return None
    run = max(runs, key=lambda r: r.run_id)
    try:
        ends = pd.read_parquet(run.summary_path, columns=["end_date"])["end_date"]
        data_end = str(ends.astype(str).max()) if len(ends) else None
    except Exception:
        data_end = None
    return run.run_id, data_end, run.factor_names, evaluation_horizon(run.periods, run.return_type)


def format_report(report: FreshnessReport) -> str:
    def show(value: str | None) -> str:
        return value or "—"

    lines = ["行情："]
    lines += [f"  {t:<24}{show(d)}" for t, d in report.market.items()]
    lines.append("股票池：")
    lines += [f"  {n:<24}{show(d)}" for n, d in report.universes.items()]
    lines.append(f"目标截止日：{show(report.target_end)}")
    lines.append("因子（已构建的输出中最早 / 最晚的截止日）：")
    for g in report.factor_groups:
        mark = "  落后" if g.lagging else ""
        lines.append(
            f"  {g.name:<36}{show(g.first_last_date)} / {show(g.latest_date)}"
            f"  共 {g.built} 个{mark}"
        )
    if report.evaluation is not None:
        e = report.evaluation
        lines.append(
            f"标准评估：{e.run_id}  数据截止 {show(e.data_end_date)}"
            f"  所用因子截止 {show(e.factors_end_date)}"
            f"  可评估到 {show(e.expected_end_date)}"
        )
    if report.issues:
        lines.append("问题：")
        lines += [f"  - {issue}" for issue in report.issues]
    else:
        lines.append("全部一致。")
    return "\n".join(lines)


__all__ = [
    "BASE_FACTORS",
    "BASE_GROUP",
    "FreshnessReport",
    "check_freshness",
    "format_report",
    "latest_standard_evaluation",
]
