from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from zer0factor.eval.analysis import EvaluationAnalysisConfig

import pandas as pd

from zer0factor.preprocess_profile import PROFILES, PreprocessProfile


@dataclass(frozen=True)
class FactorOutputSpec:
    family: str
    name: str
    raw_name: str
    profile: PreprocessProfile
    params: Mapping[str, object]

    @property
    def preprocess(self) -> str:
        return self.profile.key

    @property
    def is_raw(self) -> bool:
        return self.profile.is_raw

    def analysis_dimensions(self) -> dict[str, object]:
        return {"preprocess": self.preprocess, **self.params}


class FactorFamily(ABC):
    name: str
    base_factors: tuple[str, ...]
    windows: tuple[int, ...]
    profiles: tuple[PreprocessProfile, ...] = PROFILES
    uses_data_provider: bool = False

    @abstractmethod
    def raw_name(self, base_factor: str, window: int) -> str: ...

    @abstractmethod
    def derive(self, panel: pd.DataFrame, window: int) -> pd.DataFrame: ...

    def parse_raw_name(self, raw_name: str) -> Mapping[str, object]:
        return {}

    def raw_names(self) -> tuple[str, ...]:
        return tuple(
            self.raw_name(base_factor, window)
            for base_factor in self.base_factors
            for window in self.windows
        )

    def output_specs(self) -> tuple[FactorOutputSpec, ...]:
        return tuple(
            FactorOutputSpec(
                family=self.name,
                name=profile.output_name(raw),
                raw_name=raw,
                profile=profile,
                params=self.parse_raw_name(raw),
            )
            for raw in self.raw_names()
            for profile in self.profiles
        )

    def parse_output_name(self, factor_name: str) -> FactorOutputSpec:
        index = {spec.name: spec for spec in self.output_specs()}
        if factor_name not in index:
            raise ValueError(f"unknown factor name: {factor_name!r}")
        return index[factor_name]

    def preprocess_output_names(self) -> list[str]:
        return [spec.name for spec in self.output_specs() if not spec.is_raw]

    def all_factor_names(self) -> list[str]:
        return [spec.name for spec in self.output_specs()]

    def analysis_dimensions(self, factor_name: str) -> dict[str, object]:
        return self.parse_output_name(factor_name).analysis_dimensions()

    @property
    def analysis_config(self) -> EvaluationAnalysisConfig | None:
        return None


__all__ = [
    "PROFILES",
    "FactorFamily",
    "FactorOutputSpec",
    "PreprocessProfile",
]
