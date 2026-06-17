import sys
import types

import pandas as pd
import pytest

from zer0factor.config import ExternalFamilySpec
from zer0factor.factor_registry import FAMILIES, FactorFamilyRegistry, get_family
from zer0factor.families import FactorFamily


class FakeFamily(FactorFamily):
    name = "fake"
    base_factors = ()
    windows = ()

    def raw_name(self, base_factor: str, window: int) -> str:
        return "fake"

    def derive(self, panel: pd.DataFrame, window: int) -> pd.DataFrame:
        return panel


def test_registry_returns_builtin_family() -> None:
    registry = FactorFamilyRegistry(FAMILIES)

    assert registry.get("rolling_return") is FAMILIES["rolling_return"]


def test_registry_loads_external_family_from_spec(monkeypatch) -> None:
    module = types.ModuleType("fake_registry_factors")
    module.FAKE_FAMILY = FakeFamily()
    monkeypatch.setitem(sys.modules, "fake_registry_factors", module)
    registry = FactorFamilyRegistry(
        FAMILIES,
        (
            ExternalFamilySpec(
                name="fake",
                module="fake_registry_factors",
                attribute="FAKE_FAMILY",
            ),
        ),
    )

    assert registry.get("fake") is module.FAKE_FAMILY


def test_get_family_accepts_external_specs(monkeypatch) -> None:
    module = types.ModuleType("fake_registry_factors")
    module.FAKE_FAMILY = FakeFamily()
    monkeypatch.setitem(sys.modules, "fake_registry_factors", module)

    family = get_family(
        "fake",
        (
            ExternalFamilySpec(
                name="fake",
                module="fake_registry_factors",
                attribute="FAKE_FAMILY",
            ),
        ),
    )

    assert family is module.FAKE_FAMILY


def test_registry_rejects_unknown_family_with_known_names() -> None:
    registry = FactorFamilyRegistry(
        FAMILIES,
        (ExternalFamilySpec(name="fake", module="fake_registry_factors", attribute="FAKE"),),
    )

    with pytest.raises(ValueError, match="known families: fake, rolling_return"):
        registry.get("missing")
