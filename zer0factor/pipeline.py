from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from zer0factor.factors.rolling_returns import raw_factor_names


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


__all__ = [
    "FAMILIES",
    "PROFILES",
    "FactorFamily",
    "PreprocessProfile",
    "get_family",
]
