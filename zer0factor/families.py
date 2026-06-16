from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from zer0factor.preprocess_profile import PROFILES, PreprocessProfile


@dataclass(frozen=True)
class FactorVariant:
    raw_name: str
    profile: PreprocessProfile

    @property
    def name(self) -> str:
        return self.profile.output_name(self.raw_name)

    @property
    def preprocess(self) -> str:
        return self.profile.key

    @property
    def is_raw(self) -> bool:
        return self.profile.is_raw


class FactorFamily(ABC):
    name: str
    base_factors: tuple[str, ...]
    windows: tuple[int, ...]
    profiles: tuple[PreprocessProfile, ...] = PROFILES

    @abstractmethod
    def raw_name(self, base_factor: str, window: int) -> str: ...

    @abstractmethod
    def derive(self, panel: pd.DataFrame, window: int) -> pd.DataFrame: ...

    def raw_names(self) -> tuple[str, ...]:
        return tuple(
            self.raw_name(base_factor, window)
            for base_factor in self.base_factors
            for window in self.windows
        )

    def variants(self) -> tuple[FactorVariant, ...]:
        return tuple(
            FactorVariant(raw, profile)
            for raw in self.raw_names()
            for profile in self.profiles
        )

    def parse_name(self, factor_name: str) -> FactorVariant:
        index = {v.name: v for v in self.variants()}
        if factor_name not in index:
            raise ValueError(f"unknown factor name: {factor_name!r}")
        return index[factor_name]

    def preprocess_output_names(self) -> list[str]:
        return [v.name for v in self.variants() if not v.is_raw]

    def all_factor_names(self) -> list[str]:
        return [v.name for v in self.variants()]


__all__ = [
    "PROFILES",
    "FactorFamily",
    "FactorVariant",
    "PreprocessProfile",
]
