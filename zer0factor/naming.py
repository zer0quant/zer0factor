"""Naming policy for derived factors (z-scored, neutralized variants)."""

from __future__ import annotations

from dataclasses import dataclass

STANDARDIZED_PREFIX = "z_"
NEUTRALIZED_PREFIX = "z_neu_"


@dataclass(frozen=True)
class FactorName:
    raw: str

    @classmethod
    def parse(cls, name: str) -> FactorName:
        if name.startswith(NEUTRALIZED_PREFIX):
            return cls(name[len(NEUTRALIZED_PREFIX):])
        if name.startswith(STANDARDIZED_PREFIX):
            return cls(name[len(STANDARDIZED_PREFIX):])
        return cls(name)

    @property
    def standardized(self) -> str:
        return f"{STANDARDIZED_PREFIX}{self.raw}"

    @property
    def neutralized(self) -> str:
        return f"{NEUTRALIZED_PREFIX}{self.raw}"
