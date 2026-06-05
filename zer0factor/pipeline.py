from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from zer0factor.core import to_factor_output
from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    derive_rolling_mean_panel,
    raw_factor_names,
)

LOGGER = logging.getLogger(__name__)


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
    raw_names: Callable[[], tuple[str, ...]]
    profiles: tuple[PreprocessProfile, ...] = PROFILES

    def preprocess_output_names(self) -> list[str]:
        return [
            profile.output_name(raw_name)
            for raw_name in self.raw_names()
            for profile in self.profiles
        ]

    def all_factor_names(self) -> list[str]:
        return [*self.raw_names(), *self.preprocess_output_names()]


FAMILIES = {
    "rolling_return": FactorFamily("rolling_return", raw_factor_names),
}


def get_family(name: str) -> FactorFamily:
    try:
        return FAMILIES[name]
    except KeyError as exc:
        known = ", ".join(sorted(FAMILIES))
        raise ValueError(f"unknown factor family: {name}; known families: {known}") from exc


def compute_raw_rolling_return_factors(
    *,
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    windows: tuple[int, ...] = WINDOWS,
) -> dict[str, int]:
    rows: dict[str, int] = {}
    for base_factor in BASE_RETURN_FACTORS:
        source = _read_required_factor(storage, base_factor, None, end_date)
        panel = _long_to_wide(source)
        for window in windows:
            output_name = f"{base_factor}_ma{window}"
            output_panel = derive_rolling_mean_panel(panel, window)
            output = to_factor_output(output_panel, output_name)
            output = _filter_long_by_date(output, start_date, end_date)
            if output.empty:
                LOGGER.warning("rolling factor output is empty: %s", output_name)
            storage.write(output_name, output)
            rows[output_name] = len(output)
    return rows


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
    "FactorFamily",
    "PreprocessProfile",
    "compute_raw_rolling_return_factors",
    "get_family",
]
