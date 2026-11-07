"""Discover factor families: built-ins, every ``FAMILY`` in configured packages, explicit specs.

A module counts as a family module when it exports a module-level ``FAMILY`` that is a
``FactorFamily``. Modules whose name starts with ``_`` and modules without ``FAMILY`` are
skipped silently; import errors, wrong types and duplicate names are reported as entries
with an ``error`` so a broken family shows up instead of disappearing.
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from zer0factor.config import ExternalFamilySpec
from zer0factor.families import FactorFamily

Origin = Literal["builtin", "package", "explicit"]


@dataclass(frozen=True)
class DiscoveredFamily:
    name: str
    module: str
    origin: Origin
    family: FactorFamily | None = None
    error: str | None = None


def _error_text(exc: BaseException) -> str:
    lines = traceback.format_exception_only(type(exc), exc)
    return lines[-1].strip() if lines else repr(exc)


def _package_modules(package: str) -> tuple[list[str], str | None]:
    try:
        pkg = importlib.import_module(package)
    except Exception as exc:
        return [], f"cannot import package {package}: {_error_text(exc)}"
    paths = getattr(pkg, "__path__", None)
    if paths is None:
        return [], f"{package} is not a package"
    names = sorted(
        f"{package}.{info.name}"
        for info in pkgutil.iter_modules(paths)
        if not info.name.startswith("_")
    )
    return names, None


def discover_families(
    builtins: Mapping[str, FactorFamily],
    packages: Iterable[str],
    explicit: Iterable[ExternalFamilySpec],
) -> list[DiscoveredFamily]:
    found: list[DiscoveredFamily] = []
    owner: dict[str, str] = {}  # family name -> module that claimed it first

    def add(name: str, module: str, origin: Origin, family) -> None:
        if not isinstance(family, FactorFamily):
            found.append(DiscoveredFamily(
                name, module, origin,
                error=f"FAMILY must be a FactorFamily, got {type(family).__name__}",
            ))
            return
        if family.name in owner:
            found.append(DiscoveredFamily(
                family.name, module, origin,
                error=f"duplicate family name {family.name!r} (also in {owner[family.name]})",
            ))
            return
        owner[family.name] = module
        found.append(DiscoveredFamily(family.name, module, origin, family=family))

    for name, family in builtins.items():
        add(name, type(family).__module__, "builtin", family)

    for package in packages:
        modules, error = _package_modules(package)
        if error:
            found.append(DiscoveredFamily(package, package, "package", error=error))
            continue
        for module_name in modules:
            short = module_name.rsplit(".", 1)[-1]
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                found.append(DiscoveredFamily(short, module_name, "package", error=_error_text(exc)))
                continue
            if not hasattr(module, "FAMILY"):
                continue
            add(short, module_name, "package", module.FAMILY)

    for spec in explicit:
        if spec.name in owner:
            # Already found by package scan (the usual case for old [external_families] entries).
            continue
        try:
            module = importlib.import_module(spec.module)
            family = getattr(module, spec.attribute)
        except Exception as exc:
            found.append(DiscoveredFamily(spec.name, spec.module, "explicit", error=_error_text(exc)))
            continue
        if isinstance(family, FactorFamily) and family.name != spec.name:
            found.append(DiscoveredFamily(
                spec.name, spec.module, "explicit",
                error=f"{spec.target} has name {family.name!r}, expected {spec.name!r}",
            ))
            continue
        add(spec.name, spec.module, "explicit", family)
    return found


def describe(entry: DiscoveredFamily) -> dict:
    out: dict = {
        "name": entry.name,
        "module": entry.module,
        "origin": entry.origin,
        "error": entry.error,
        "base_factors": [],
        "windows": [],
        "profiles": [],
        "raw_names": [],
        "outputs": [],
        "uses_data_provider": False,
        "source": None,
    }
    family = entry.family
    if family is None:
        return out
    try:
        out.update(
            base_factors=[str(b) for b in family.base_factors],
            windows=[int(w) for w in family.windows],
            profiles=[p.key for p in family.profiles],
            raw_names=list(family.raw_names()),
            outputs=family.all_factor_names(),
            uses_data_provider=bool(family.uses_data_provider),
        )
        module = importlib.import_module(entry.module)
        source = getattr(module, "SOURCE", None)
        out["source"] = source if isinstance(source, dict) else None
    except Exception as exc:
        out["error"] = f"cannot describe family: {_error_text(exc)}"
    return out
