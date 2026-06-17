from pathlib import Path

import pytest

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.selection import FactorSelector


def _write_registry(path: Path) -> None:
    path.write_text(
        """
[[factors]]
name = "factor_a"
category = "price"
source_type = "neutralized"
enabled = true
tags = ["momentum"]
description = ""

[[factors]]
name = "factor_b"
category = "volume"
source_type = "neutralized"
enabled = false
tags = ["turnover"]
description = ""

[[factors]]
name = "factor_c"
category = "price"
source_type = "neutralized"
enabled = true
tags = ["momentum", "short"]
description = ""
""",
        encoding="utf-8",
    )


def test_selector_returns_explicit_names_in_order():
    selector = FactorSelector()
    request = EvaluationRequest(factor_names=("factor_b", "factor_a"))

    assert selector.resolve(request) == ("factor_b", "factor_a")


def test_selector_rejects_empty_explicit_names():
    selector = FactorSelector()

    with pytest.raises(ValueError, match="factor_names must not be empty"):
        selector.resolve(EvaluationRequest(factor_names=()))


def test_selector_loads_enabled_registry_factors(tmp_path):
    registry_path = tmp_path / "factors.toml"
    _write_registry(registry_path)

    selector = FactorSelector()
    request = EvaluationRequest(
        factor_source="registry",
        registry_path=registry_path,
        enabled_only=True,
    )

    assert selector.resolve(request) == ("factor_a", "factor_c")


def test_selector_filters_registry_categories(tmp_path):
    registry_path = tmp_path / "factors.toml"
    _write_registry(registry_path)

    selector = FactorSelector()
    request = EvaluationRequest(
        factor_source="registry",
        registry_path=registry_path,
        enabled_only=False,
        categories=("volume",),
    )

    assert selector.resolve(request) == ("factor_b",)


def test_selector_rejects_empty_registry_match(tmp_path):
    registry_path = tmp_path / "factors.toml"
    _write_registry(registry_path)

    selector = FactorSelector()
    request = EvaluationRequest(
        factor_source="registry",
        registry_path=registry_path,
        enabled_only=True,
        categories=("missing",),
    )

    with pytest.raises(ValueError, match="no factors matched"):
        selector.resolve(request)
