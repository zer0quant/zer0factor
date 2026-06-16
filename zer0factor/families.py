from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from zer0factor.factors.rolling_returns import BASE_RETURN_FACTORS, WINDOWS


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


class FactorFamily(ABC):
    name: str
    base_factors: tuple[str, ...]
    windows: tuple[int, ...]
    profiles: tuple[PreprocessProfile, ...] = PROFILES

    @abstractmethod
    def raw_name(self, base_factor: str, window: int) -> str: ...

    @abstractmethod
    def derive(self, panel: pd.DataFrame, window: int) -> pd.DataFrame: ...

    @abstractmethod
    def parse_name(self, factor_name: str) -> dict: ...

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


class RollingReturnFamily(FactorFamily):
    name = "rolling_return"
    base_factors = BASE_RETURN_FACTORS
    windows = WINDOWS

    # Matches: [preprocess_]base_factor_ma{window}
    # preprocess: z | z_size_neu | z_industry_neu | z_size_industry_neu  (optional)
    # base_factor: daily_return | open_return | intraday_return | overnight_return
    # window: one or more digits
    _NAME_RE = re.compile(
        r"^(?:(?P<preprocess>z(?:_size_industry_neu|_industry_neu|_size_neu)?)_)?"
        r"(?P<base>daily_return|open_return|intraday_return|overnight_return)"
        r"_ma(?P<window>\d+)$"
    )

    def raw_name(self, base_factor: str, window: int) -> str:
        return f"{base_factor}_ma{window}"

    def derive(self, panel: pd.DataFrame, window: int) -> pd.DataFrame:
        return panel.rolling(window=window, min_periods=window // 2).mean()

    def parse_name(self, factor_name: str) -> dict:
        m = self._NAME_RE.match(factor_name)
        if m is None:
            raise ValueError(f"unknown rolling return factor name: {factor_name}")
        window = int(m["window"])
        if window not in self.windows:
            raise ValueError(f"unsupported rolling return window: {factor_name}")
        return {
            "base_factor": m["base"],
            "preprocess": m["preprocess"] or "raw",
            "window": window,
        }


FAMILIES: dict[str, FactorFamily] = {
    "rolling_return": RollingReturnFamily(),
}


def get_family(name: str) -> FactorFamily:
    try:
        return FAMILIES[name]
    except KeyError as exc:
        known = ", ".join(sorted(FAMILIES))
        raise ValueError(f"unknown factor family: {name}; known families: {known}") from exc


__all__ = [
    "FAMILIES",
    "PROFILES",
    "FactorFamily",
    "PreprocessProfile",
    "RollingReturnFamily",
    "get_family",
]
