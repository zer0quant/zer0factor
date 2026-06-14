from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from zer0factor.core import to_factor_output
from zer0factor.panel import parse_trade_dates
from zer0factor.preprocess.impute import impute_missing
from zer0factor.preprocess.neutralize import neutralize
from zer0factor.preprocess.standardize import standardize
from zer0factor.preprocess.winsorize import winsorize

WinsorizeMethod = Literal["mad", "quantile", "none"]
ImputeMethod = Literal["cross_section_median", "industry_median", "none"]
StandardizeMethod = Literal["zscore", "rank_pct", "none"]
NeutralizeMethod = Literal["size", "industry", "size_industry", "none"]

_LONG_COLUMNS = {"trade_date", "ts_code", "value"}


@dataclass(frozen=True)
class PreprocessConfig:
    winsorize_method: WinsorizeMethod = "mad"
    winsorize_n: float = 5.0
    winsorize_lower_quantile: float = 0.01
    winsorize_upper_quantile: float = 0.99
    impute_method: ImputeMethod = "cross_section_median"
    standardize_method: StandardizeMethod = "zscore"
    neutralize_method: NeutralizeMethod | None = None

    def __post_init__(self) -> None:
        _validate_choice(
            self.winsorize_method,
            {"mad", "quantile", "none"},
            "winsorize_method",
        )
        _validate_choice(
            self.impute_method,
            {"cross_section_median", "industry_median", "none"},
            "impute_method",
        )
        _validate_choice(
            self.standardize_method,
            {"zscore", "rank_pct", "none"},
            "standardize_method",
        )
        if self.neutralize_method is not None:
            _validate_choice(
                self.neutralize_method,
                {"size", "industry", "size_industry", "none"},
                "neutralize_method",
            )
        if self.winsorize_n <= 0:
            raise ValueError("winsorize_n must be positive")
        if not (
            0
            <= self.winsorize_lower_quantile
            < self.winsorize_upper_quantile
            <= 1
        ):
            raise ValueError("quantile bounds must satisfy 0 <= lower < upper <= 1")


class FactorPreprocessPipeline:
    def __init__(self, config: PreprocessConfig | None = None) -> None:
        self.config = config or PreprocessConfig()

    def transform(
        self,
        factor: pd.DataFrame,
        *,
        industry: pd.DataFrame | None = None,
        exposures: dict[str, pd.DataFrame] | None = None,
    ) -> pd.DataFrame:
        wide, was_long = _to_wide(factor)
        cfg = self.config

        processed = winsorize(
            wide,
            method=cfg.winsorize_method,
            n=cfg.winsorize_n,
            lower_quantile=cfg.winsorize_lower_quantile,
            upper_quantile=cfg.winsorize_upper_quantile,
        )
        processed = impute_missing(
            processed,
            method=cfg.impute_method,
            industry=industry,
        )
        processed = standardize(processed, method=cfg.standardize_method)
        processed = neutralize(
            processed,
            method=cfg.neutralize_method,
            exposures=exposures,
        )

        if was_long:
            return to_factor_output(processed)
        return processed


def _to_wide(factor: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if not isinstance(factor, pd.DataFrame):
        raise TypeError("factor input must be a pandas DataFrame")

    present_long_columns = _LONG_COLUMNS.intersection(factor.columns)
    if present_long_columns and not _LONG_COLUMNS.issubset(factor.columns):
        raise ValueError(
            "long factor input must contain columns: trade_date, ts_code, value"
        )

    if _LONG_COLUMNS.issubset(factor.columns):
        long = factor.loc[:, ["trade_date", "ts_code", "value"]].copy()
        long["trade_date"] = parse_trade_dates(long["trade_date"])
        duplicates = long.duplicated(["trade_date", "ts_code"])
        if duplicates.any():
            raise ValueError("long factor input contains duplicate trade_date/ts_code")
        wide = long.pivot(index="trade_date", columns="ts_code", values="value")
        return wide.sort_index().sort_index(axis=1), True

    wide = factor.copy()
    wide.index = parse_trade_dates(pd.Series(wide.index, index=wide.index)).to_numpy()
    return wide.sort_index().sort_index(axis=1), False


def _validate_choice(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}")
