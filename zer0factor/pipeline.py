from __future__ import annotations

import logging
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from zer0factor.core import to_factor_output
from zer0factor.exposures import build_sw_l1_industry_panel
from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    derive_rolling_mean_panel,
    raw_factor_name,
)
from zer0factor.preprocess import impute_missing, neutralize, standardize, winsorize

LOGGER = logging.getLogger(__name__)
SIZE_FACTOR_NAME = "z_log_circulating_market_cap"


@dataclass(frozen=True)
class PreprocessProfile:
    key: str
    prefix: str
    neutralize_method: str | None

    def output_name(self, raw_factor_name: str) -> str:
        return f"{self.prefix}{raw_factor_name}"


PROFILES = (
    PreprocessProfile("z", "z_", None),
    PreprocessProfile("z_size_neu", "z_size_neu_", "size"),
    PreprocessProfile("z_industry_neu", "z_industry_neu_", "industry"),
    PreprocessProfile("z_size_industry_neu", "z_size_industry_neu_", "size_industry"),
)


@dataclass(frozen=True)
class FactorFamily:
    name: str
    base_factors: tuple[str, ...]
    windows: tuple[int, ...]
    raw_name: Callable[[str, int], str]
    derive: Callable[[pd.DataFrame, int], pd.DataFrame]
    profiles: tuple[PreprocessProfile, ...] = PROFILES

    def raw_names(self) -> tuple[str, ...]:
        return tuple(
            self.raw_name(base_factor, window)
            for base_factor in self.base_factors
            for window in self.windows
        )

    def preprocess_output_names(self) -> list[str]:
        return [
            profile.output_name(raw_name)
            for raw_name in self.raw_names()
            for profile in self.profiles
        ]

    def all_factor_names(self) -> list[str]:
        return [*self.raw_names(), *self.preprocess_output_names()]


FAMILIES = {
    "rolling_return": FactorFamily(
        name="rolling_return",
        base_factors=BASE_RETURN_FACTORS,
        windows=WINDOWS,
        raw_name=raw_factor_name,
        derive=derive_rolling_mean_panel,
    ),
}


def get_family(name: str) -> FactorFamily:
    try:
        return FAMILIES[name]
    except KeyError as exc:
        known = ", ".join(sorted(FAMILIES))
        raise ValueError(f"unknown factor family: {name}; known families: {known}") from exc


def compute_raw_family_factors(
    family: FactorFamily,
    *,
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    windows: tuple[int, ...] | None = None,
) -> dict[str, int]:
    windows = family.windows if windows is None else windows
    rows: dict[str, int] = {}
    for base_factor in family.base_factors:
        source = _read_required_factor(storage, base_factor, None, end_date)
        panel = _long_to_wide(source)
        for window in windows:
            output_name = family.raw_name(base_factor, window)
            output_panel = family.derive(panel, window)
            output = to_factor_output(output_panel, output_name)
            output = _filter_long_by_date(output, start_date, end_date)
            if output.empty:
                LOGGER.warning("raw factor output is empty: %s", output_name)
            storage.write(output_name, output)
            rows[output_name] = len(output)
    return rows


def compute_raw_rolling_return_factors(
    *,
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    windows: tuple[int, ...] = WINDOWS,
) -> dict[str, int]:
    return compute_raw_family_factors(
        get_family("rolling_return"),
        storage=storage,
        start_date=start_date,
        end_date=end_date,
        windows=windows,
    )


def preprocess_one_factor(
    raw_factor_name: str,
    *,
    storage: Any,
    industry_panel: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
    universe: pd.DataFrame | None = None,
    profiles: tuple[PreprocessProfile, ...] = PROFILES,
) -> dict[str, int]:
    raw = _read_required_factor(storage, raw_factor_name, start_date, end_date)
    size = _read_required_factor(storage, SIZE_FACTOR_NAME, start_date, end_date)

    raw_panel = _filter_panel_by_universe(_long_to_wide(raw), universe)
    size_panel = _long_to_wide(size).reindex(
        index=raw_panel.index,
        columns=raw_panel.columns,
    )
    aligned_industry = industry_panel.reindex(
        index=raw_panel.index,
        columns=raw_panel.columns,
    )

    base = _winsorize_impute_zscore(raw_panel)
    rows: dict[str, int] = {}
    for profile in profiles:
        output_name = profile.output_name(raw_factor_name)
        if profile.neutralize_method is None:
            output_panel = base
        else:
            output_panel = _neutralize_then_zscore(
                base,
                method=profile.neutralize_method,
                size=size_panel,
                industry=aligned_industry,
            )
        output = _wide_to_long(output_panel)
        storage.write(output_name, output)
        rows[output_name] = len(output)
    return rows


def preprocess_all_factors(
    raw_names: list[str],
    *,
    storage: Any,
    pro: Any,
    start_date: str | None,
    end_date: str | None,
    process_universe: str,
    profiles: tuple[PreprocessProfile, ...] = PROFILES,
) -> dict[str, int]:
    universe = _read_universe_panel(
        pro,
        universe_name=process_universe,
        start_date=start_date,
        end_date=end_date,
    )
    if universe.empty:
        raise ValueError("process universe returned no rows")

    raw_panels = [
        _filter_panel_by_universe(
            _long_to_wide(_read_required_factor(storage, name, start_date, end_date)),
            universe,
        )
        for name in raw_names
    ]
    raw_dates = raw_panels[0].index
    raw_codes = raw_panels[0].columns
    for panel in raw_panels[1:]:
        raw_dates = raw_dates.union(panel.index)
        raw_codes = raw_codes.union(panel.columns)

    industry_panel = build_sw_l1_industry_panel(pro, dates=raw_dates, ts_codes=raw_codes)
    rows: dict[str, int] = {}
    for raw_name in raw_names:
        rows.update(
            preprocess_one_factor(
                raw_name,
                storage=storage,
                industry_panel=industry_panel,
                start_date=start_date,
                end_date=end_date,
                universe=universe,
                profiles=profiles,
            )
        )
    return rows


def run_build_stage(
    family_name: str,
    stage: str,
    *,
    storage: Any,
    pro: Any | None = None,
    start_date: str | None,
    end_date: str | None,
    process_universe: str | None = None,
) -> dict[str, int]:
    family = get_family(family_name)
    if stage not in {"raw", "preprocess", "all"}:
        raise ValueError(f"unknown build stage: {stage}")

    rows: dict[str, int] = {}
    if stage in {"raw", "all"}:
        rows.update(
            compute_raw_family_factors(
                family,
                storage=storage,
                start_date=start_date,
                end_date=end_date,
            )
        )
    if stage in {"preprocess", "all"}:
        if pro is None:
            raise ValueError("pro is required for preprocess stage")
        if process_universe is None:
            raise ValueError("process_universe is required for preprocess stage")
        rows.update(
            preprocess_all_factors(
                list(family.raw_names()),
                storage=storage,
                pro=pro,
                start_date=start_date,
                end_date=end_date,
                process_universe=process_universe,
                profiles=family.profiles,
            )
        )
    return rows


def update_factor_registry(registry_path: Path, *, family_name: str) -> list[str]:
    family = get_family(family_name)
    existing = _read_registry_names(registry_path)
    entries = _registry_entries_for_family(family)
    missing = [entry for entry in entries if entry["name"] not in existing]
    if not missing:
        return []

    if registry_path.exists():
        prefix = registry_path.read_text(encoding="utf-8").rstrip() + "\n\n"
    else:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = '# Factor Registry\n\n[registry]\nversion = "1"\n\n'

    body = "\n\n".join(_format_registry_entry(entry) for entry in missing)
    registry_path.write_text(prefix + body + "\n", encoding="utf-8")
    return [entry["name"] for entry in missing]


def _read_registry_names(registry_path: Path) -> set[str]:
    if not registry_path.exists():
        return set()
    with open(registry_path, "rb") as f:
        raw = tomllib.load(f)
    return {str(entry["name"]) for entry in raw.get("factors", [])}


def _registry_entries_for_family(family: FactorFamily) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for base_factor in family.base_factors:
        for window in family.windows:
            raw_name = family.raw_name(base_factor, window)
            window_tags = [family.name, base_factor, "ma", f"ma{window}"]
            entries.append({
                "name": raw_name,
                "category": "price",
                "source_type": "derived",
                "source_factor": base_factor,
                "enabled": False,
                "tags": [*window_tags, "raw"],
                "description": f"Rolling mean of {base_factor} over {window} trading days",
                "evaluate_default": False,
            })
            for profile in family.profiles:
                entries.append({
                    "name": profile.output_name(raw_name),
                    "category": "price",
                    "source_type": "derived" if profile.neutralize_method is None else "neutralized",
                    "source_factor": raw_name,
                    "enabled": True,
                    "tags": [*window_tags, profile.key],
                    "description": f"{profile.key} profile for {raw_name}",
                    "evaluate_default": True,
                })
    return entries


def _format_registry_entry(entry: dict[str, object]) -> str:
    lines = [
        "[[factors]]",
        f'name = "{entry["name"]}"',
        f'category = "{entry["category"]}"',
        f'source_type = "{entry["source_type"]}"',
        f'source_factor = "{entry["source_factor"]}"',
        f'enabled = {str(entry["enabled"]).lower()}',
        "tags = [" + ", ".join(f'"{tag}"' for tag in entry["tags"]) + "]",
        f'description = "{entry["description"]}"',
        "",
        "[factors.evaluate]",
        f'default = {str(entry["evaluate_default"]).lower()}',
        "quantiles = 5",
        "periods = [1, 5, 10]",
        'return_type = "open_t1"',
    ]
    return "\n".join(lines)


def _read_universe_panel(
    pro: Any,
    *,
    universe_name: str,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    rows = pro.universe(
        universe=universe_name,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,universe,ts_code",
    )
    if rows.empty:
        return pd.DataFrame(dtype=bool)
    frame = rows.loc[:, ["trade_date", "ts_code"]].copy()
    frame["trade_date"] = _parse_trade_dates(frame["trade_date"])
    frame["in_universe"] = True
    return (
        frame.drop_duplicates(["trade_date", "ts_code"])
        .pivot(index="trade_date", columns="ts_code", values="in_universe")
        .pipe(lambda df: df.where(df.notna(), False))
        .astype(bool)
        .sort_index()
        .sort_index(axis=1)
    )


def _read_required_factor(
    storage: Any,
    factor_name: str,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    try:
        return storage.read(factor_name, start_date=start_date, end_date=end_date)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required factor missing: {factor_name}") from exc


def _long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "ts_code", "value"}
    if not required.issubset(df.columns):
        raise ValueError(f"factor data must contain columns: {sorted(required)}")

    frame = df.loc[:, ["trade_date", "ts_code", "value"]].copy()
    frame["trade_date"] = _parse_trade_dates(frame["trade_date"])
    if frame.duplicated(["trade_date", "ts_code"]).any():
        raise ValueError("factor data contains duplicate trade_date/ts_code")
    return (
        frame.pivot(index="trade_date", columns="ts_code", values="value")
        .sort_index()
        .sort_index(axis=1)
    )


def _wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    return to_factor_output(df)


def _winsorize_impute_zscore(panel: pd.DataFrame) -> pd.DataFrame:
    processed = winsorize(panel, method="mad", n=5.0)
    processed = impute_missing(processed, method="cross_section_median")
    return standardize(processed, method="zscore")


def _neutralize_then_zscore(
    panel: pd.DataFrame,
    *,
    method: str,
    size: pd.DataFrame,
    industry: pd.DataFrame,
) -> pd.DataFrame:
    exposures = {"size": size, "industry": industry}
    neutralized = neutralize(panel, method=method, exposures=exposures)
    return standardize(neutralized, method="zscore")


def _filter_panel_by_universe(
    panel: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return panel
    aligned = universe.reindex(index=panel.index, columns=panel.columns).fillna(False)
    return panel.where(aligned.astype(bool)).dropna(axis=1, how="all")


def _filter_long_by_date(
    df: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    result = df
    if start_date is not None:
        result = result[result["trade_date"] >= start_date]
    if end_date is not None:
        result = result[result["trade_date"] <= end_date]
    return result.reset_index(drop=True)


def _parse_trade_dates(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d")
    return pd.to_datetime(values)


__all__ = [
    "FAMILIES",
    "PROFILES",
    "SIZE_FACTOR_NAME",
    "FactorFamily",
    "PreprocessProfile",
    "compute_raw_family_factors",
    "compute_raw_rolling_return_factors",
    "get_family",
    "preprocess_all_factors",
    "preprocess_one_factor",
    "run_build_stage",
    "update_factor_registry",
]
