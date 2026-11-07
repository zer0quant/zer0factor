from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import import_module

from zer0factor.config import ExternalFamilySpec
from zer0factor.factors.rolling_returns import RollingReturnFamily
from zer0factor.families import FactorFamily

FAMILIES: dict[str, FactorFamily] = {
    "rolling_return": RollingReturnFamily(),
}


def get_family(
    name: str,
    external_families: Iterable[ExternalFamilySpec] | Mapping[str, str] | None = None,
) -> FactorFamily:
    return FactorFamilyRegistry(FAMILIES, external_families or ()).get(name)


class FactorFamilyRegistry:
    def __init__(
        self,
        builtins: Mapping[str, FactorFamily],
        external_specs: Iterable[ExternalFamilySpec] | Mapping[str, str] = (),
    ) -> None:
        self._builtins = dict(builtins)
        self._external_specs = self._normalize_external_specs(external_specs)

    def get(self, name: str) -> FactorFamily:
        if name in self._builtins:
            return self._builtins[name]
        if name in self._external_specs:
            return self._load_external(self._external_specs[name])
        known = ", ".join(self.known_names())
        raise ValueError(f"unknown factor family: {name}; known families: {known}")

    def known_names(self) -> tuple[str, ...]:
        return tuple(sorted({*self._builtins, *self._external_specs}))

    def _load_external(self, spec: ExternalFamilySpec) -> FactorFamily:
        family = getattr(import_module(spec.module), spec.attribute)
        if not isinstance(family, FactorFamily):
            raise TypeError(
                f"external family {spec.name!r} must be a FactorFamily, "
                f"got {type(family).__name__}"
            )
        if family.name != spec.name:
            raise ValueError(
                f"external family {spec.target!r} has name {family.name!r}, "
                f"expected {spec.name!r}"
            )
        return family

    @staticmethod
    def _normalize_external_specs(
        external_specs: Iterable[ExternalFamilySpec] | Mapping[str, str],
    ) -> dict[str, ExternalFamilySpec]:
        if isinstance(external_specs, Mapping):
            return {
                str(name): ExternalFamilySpec.from_target(str(name), str(target))
                for name, target in external_specs.items()
            }
        return {spec.name: spec for spec in external_specs}


def family_registry(cfg) -> FactorFamilyRegistry:
    """Built-ins + families auto-discovered in ``[families] packages`` + explicit specs."""
    from zer0factor.discovery import discover_families

    explicit = tuple(getattr(cfg, "external_families", ()) or ())
    packages = tuple(getattr(cfg, "family_packages", ()) or ())
    discovered = {
        d.name: d.family
        for d in discover_families(FAMILIES, packages, ())
        if d.family is not None
    }
    # Explicit specs stay lazily imported (and validated) by the registry itself.
    remaining = [s for s in explicit if s.name not in discovered]
    return FactorFamilyRegistry(discovered, remaining)


__all__ = [
    "FAMILIES",
    "family_registry",
    "FactorFamilyRegistry",
    "get_family",
]
