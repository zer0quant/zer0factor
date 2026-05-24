from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluateMeta:
    default: bool
    quantiles: int
    periods: tuple[int, ...]
    return_type: str


@dataclass(frozen=True)
class FactorMeta:
    name: str
    category: str
    source_type: str
    enabled: bool
    source_factor: str | None = None
    tags: tuple[str, ...] = ()
    description: str = ""
    evaluate: EvaluateMeta | None = None


@dataclass(frozen=True)
class RegistryValidation:
    registered_missing: tuple[str, ...]
    orphan_stored: tuple[str, ...]


class FactorRegistry:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._factors: dict[str, FactorMeta] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"factor registry not found: {self._path}")
        with open(self._path, "rb") as f:
            raw = tomllib.load(f)
        for entry in raw.get("factors", []):
            meta = _parse_factor_meta(entry)
            self._factors[meta.name] = meta

    def all(self) -> list[FactorMeta]:
        return list(self._factors.values())

    def get(self, name: str) -> FactorMeta:
        if name not in self._factors:
            raise KeyError(f"factor not registered: {name}")
        return self._factors[name]

    def filter(
        self,
        *,
        enabled: bool | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        evaluate_default: bool | None = None,
    ) -> list[FactorMeta]:
        results = list(self._factors.values())
        if enabled is not None:
            results = [f for f in results if f.enabled == enabled]
        if category is not None:
            results = [f for f in results if f.category == category]
        if tags is not None:
            results = [f for f in results if all(t in f.tags for t in tags)]
        if evaluate_default is not None:
            results = [
                f for f in results
                if f.evaluate is not None and f.evaluate.default == evaluate_default
            ]
        return results

    def validate(self, storage) -> RegistryValidation:
        stored = set(storage.list_factors())
        registered = set(self._factors)
        return RegistryValidation(
            registered_missing=tuple(sorted(registered - stored)),
            orphan_stored=tuple(sorted(stored - registered)),
        )


def _parse_factor_meta(entry: dict) -> FactorMeta:
    required = {"name", "category", "source_type", "enabled"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"factor entry missing required fields: {missing}")

    evaluate: EvaluateMeta | None = None
    if "evaluate" in entry:
        ev = entry["evaluate"]
        evaluate = EvaluateMeta(
            default=bool(ev.get("default", True)),
            quantiles=int(ev.get("quantiles", 5)),
            periods=tuple(ev.get("periods", [1, 5, 10])),
            return_type=str(ev.get("return_type", "open_t1")),
        )

    return FactorMeta(
        name=str(entry["name"]),
        category=str(entry["category"]),
        source_type=str(entry["source_type"]),
        enabled=bool(entry["enabled"]),
        source_factor=entry.get("source_factor"),
        tags=tuple(entry.get("tags", [])),
        description=str(entry.get("description", "")),
        evaluate=evaluate,
    )
