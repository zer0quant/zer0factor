from __future__ import annotations

from zer0factor.factors.rolling_returns import RollingReturnFamily
from zer0factor.families import FactorFamily

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
    "get_family",
]
