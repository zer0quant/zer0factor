from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreprocessProfile:
    zscore: bool = False
    size_neutral: bool = False
    industry_neutral: bool = False

    @property
    def key(self) -> str:
        if not self.zscore:
            return "raw"
        parts = ["z"]
        if self.size_neutral and self.industry_neutral:
            parts.append("size_industry_neu")
        elif self.size_neutral:
            parts.append("size_neu")
        elif self.industry_neutral:
            parts.append("industry_neu")
        return "_".join(parts)

    @property
    def is_raw(self) -> bool:
        return not self.zscore

    @property
    def neutralize_method(self) -> str | None:
        if self.size_neutral and self.industry_neutral:
            return "size_industry"
        if self.size_neutral:
            return "size"
        if self.industry_neutral:
            return "industry"
        return None

    def output_name(self, raw_name: str) -> str:
        return f"{self.key}_{raw_name}" if self.zscore else raw_name


RAW                 = PreprocessProfile()
Z                   = PreprocessProfile(zscore=True)
Z_SIZE_NEU          = PreprocessProfile(zscore=True, size_neutral=True)
Z_INDUSTRY_NEU      = PreprocessProfile(zscore=True, industry_neutral=True)
Z_SIZE_INDUSTRY_NEU = PreprocessProfile(zscore=True, size_neutral=True, industry_neutral=True)

PROFILES = (RAW, Z, Z_SIZE_NEU, Z_INDUSTRY_NEU, Z_SIZE_INDUSTRY_NEU)

__all__ = [
    "PROFILES",
    "RAW",
    "Z",
    "Z_INDUSTRY_NEU",
    "Z_SIZE_INDUSTRY_NEU",
    "Z_SIZE_NEU",
    "PreprocessProfile",
]
