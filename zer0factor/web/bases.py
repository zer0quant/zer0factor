"""Group factor versions by base factor for the board and the base factor home page.

A systematic factor name is ``[<z|rank>_[<size|industry|size_industry>_neu_]]<base>[_ma<N>]``
(plus the legacy ``z_neu_`` prefix); the same rules live in ``web/src/factorName.ts``.
The board shows one row per base: the primary version's (see ``BoardSetting``) direction and
the median direction-adjusted ICIR across its windows. Other versions never substitute.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass

from zer0factor.config import BoardSetting

_PREP_RE = re.compile(r"^(z|rank)_(?:(size_industry|size|industry)_neu_|(neu)_)?")
_WINDOW_RE = re.compile(r"_ma(\d+)$")

PREP_ORDER = (
    "raw",
    "z",
    "z_size_neu",
    "z_industry_neu",
    "z_size_industry_neu",
    "z_neu",
    "rank",
    "rank_size_neu",
    "rank_industry_neu",
    "rank_size_industry_neu",
)
_FALLBACK_ORDER = PREP_ORDER[:5]

# Board metric columns (keys of Catalog.board_rows()); each is the median over the primary
# version's scored windows, like the ICIR.
METRIC_KEYS = (
    "ic_adj",
    "icir",
    "t_stat",
    "ic_win_rate",
    "long_ann_ret",
    "long_max_dd",
    "long_sharpe",
    "long_exc_ann_ret",
    "monotonicity",
    "turnover_long",
)


@dataclass(frozen=True)
class ParsedName:
    name: str
    prep: str
    base: str
    window: int | None


def parse_factor_name(name: str) -> ParsedName:
    rest, prep = name, "raw"
    m = _PREP_RE.match(name)
    if m and len(m.group(0)) < len(name):
        std, neu, legacy = m.groups()
        prep = f"{std}_{neu}_neu" if neu else f"{std}_neu" if legacy else std
        rest = name[len(m.group(0)):]
    window = None
    w = _WINDOW_RE.search(rest)
    if w and w.start() > 0:
        window = int(w.group(1))
        rest = rest[: w.start()]
    return ParsedName(name=name, prep=prep, base=rest, window=window)


def prep_sort_key(prep: str) -> tuple[int, str]:
    try:
        return PREP_ORDER.index(prep), ""
    except ValueError:
        return len(PREP_ORDER), prep


def primary_prep(base: str, board: BoardSetting) -> str:
    return board.industry_only_prep if base in board.industry_only_bases else board.primary_prep


def _window_key(window: int | None) -> int:
    return -1 if window is None else window


def _version(row: dict, p: ParsedName) -> dict:
    return {
        **{k: row.get(k) for k in (*METRIC_KEYS, "start_date", "end_date")},
        "name": row["name"],
        "prep": p.prep,
        "window": p.window,
        "evaluated": bool(row.get("evaluated")),
        "icir": row.get("icir"),
        "direction": row.get("direction"),
        "run_id": row.get("run_id"),
    }


def _median(values: list) -> float | None:
    nums = [float(v) for v in values if v is not None]
    return float(statistics.median(nums)) if nums else None


def _group(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        p = parse_factor_name(row["name"])
        groups[p.base].append(_version(row, p))
    for versions in groups.values():
        versions.sort(key=lambda v: (prep_sort_key(v["prep"]), _window_key(v["window"])))
    return groups


def _summary(base: str, versions: list[dict], board: BoardSetting) -> dict:
    primary = primary_prep(base, board)
    windows = [v for v in versions if v["prep"] == primary]
    scored = [
        v for v in windows if v["evaluated"] and v["icir"] is not None and v["direction"] is not None
    ]
    directions = {int(v["direction"]) for v in scored}
    direction = icir_median = None
    if not windows:
        status = "missing"
    elif not scored:
        status = "unevaluated"
    elif len(directions) > 1:
        status = "mixed"
    else:
        status = "ok"
        direction = directions.pop()
        icir_median = float(statistics.median(float(v["icir"]) for v in scored))
    shown = scored if status == "ok" else []
    metrics = {k: _median([v[k] for v in shown]) for k in METRIC_KEYS}
    starts = [str(v["start_date"]) for v in shown if v["start_date"]]
    ends = [str(v["end_date"]) for v in shown if v["end_date"]]
    counts: dict[str, list[int]] = {}
    for v in versions:
        c = counts.setdefault(v["prep"], [0, 0])
        c[0] += 1
        c[1] += int(v["evaluated"])
    return {
        "base": base,
        "primary_prep": primary,
        "status": status,
        "direction": direction,
        "icir_median": icir_median,
        "metrics": metrics,
        "start_date": min(starts) if starts else None,
        "end_date": max(ends) if ends else None,
        "run_ids": sorted({v["run_id"] for v in shown if v["run_id"]}),
        "windows": [
            {k: v[k] for k in ("name", "window", "evaluated", "icir", "direction")} for v in windows
        ],
        "preps": [
            {"prep": prep, "n_versions": n, "n_evaluated": e} for prep, (n, e) in counts.items()
        ],
    }


def summarize_bases(rows: list[dict], board: BoardSetting) -> list[dict]:
    groups = _group(rows)
    return [_summary(base, groups[base], board) for base in sorted(groups)]


def base_versions(rows: list[dict], base: str, board: BoardSetting) -> dict | None:
    versions = _group(rows).get(base)
    if not versions:
        return None
    primary = primary_prep(base, board)
    preps = {v["prep"] for v in versions}
    # Fall back along raw → Z → size → industry → size+industry first; legacy z_neu and Rank
    # preps only when none of those exist.
    standard = [p for p in preps if p in _FALLBACK_ORDER]
    default = (
        primary
        if primary in preps
        else max(standard, key=_FALLBACK_ORDER.index)
        if standard
        else max(preps, key=prep_sort_key)
    )
    keys = ("name", "prep", "window", "evaluated", "icir", "direction", "run_id")
    return {
        "base": base,
        "primary_prep": primary,
        "default_prep": default,
        "versions": [{k: v[k] for k in keys} for v in versions],
    }
