from pathlib import Path

import pandas as pd
import pytest

from zer0factor.registry import EvaluateMeta, FactorMeta, FactorRegistry, RegistryValidation
from zer0factor.storage import FactorStorage


def _write_registry(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "factors.toml"
    p.write_text(content)
    return p


def test_registry_loads_minimal_factor(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = "test"
""")
    reg = FactorRegistry(p)
    assert len(reg.all()) == 1
    meta = reg.all()[0]
    assert meta.name == "z_neu_daily_return"
    assert meta.category == "price"
    assert meta.source_type == "neutralized"
    assert meta.enabled is True
    assert meta.source_factor is None
    assert meta.tags == ()
    assert meta.evaluate is None


def test_registry_loads_factor_with_evaluate_block(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
""")
    reg = FactorRegistry(p)
    meta = reg.all()[0]
    assert isinstance(meta.evaluate, EvaluateMeta)
    assert meta.evaluate.default is True
    assert meta.evaluate.quantiles == 5
    assert meta.evaluate.periods == (1, 5, 10)
    assert meta.evaluate.return_type == "open_t1"


def test_registry_missing_required_field_raises(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "bad_factor"
category = "price"
""")
    with pytest.raises(ValueError, match="missing required fields"):
        FactorRegistry(p)


def test_registry_get_existing_factor(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    meta = reg.get("z_neu_daily_return")
    assert meta.name == "z_neu_daily_return"


def test_registry_get_missing_factor_raises(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    with pytest.raises(KeyError):
        reg.get("does_not_exist")


def test_registry_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FactorRegistry(tmp_path / "nonexistent.toml")


def test_registry_filter_by_enabled(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_a"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_b"
category = "price"
source_type = "neutralized"
enabled = false
description = ""
""")
    reg = FactorRegistry(p)
    enabled = reg.filter(enabled=True)
    assert [f.name for f in enabled] == ["z_a"]
    disabled = reg.filter(enabled=False)
    assert [f.name for f in disabled] == ["z_b"]


def test_registry_filter_by_category(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_price_factor"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_vol_factor"
category = "volume"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    price = reg.filter(category="price")
    assert [f.name for f in price] == ["z_price_factor"]


def test_registry_filter_by_evaluate_default(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_eval_default"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"

[[factors]]
name = "z_no_evaluate"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    defaults = reg.filter(evaluate_default=True)
    assert [f.name for f in defaults] == ["z_eval_default"]


def _make_storage_with_factors(tmp_path: Path, names: list[str]) -> FactorStorage:
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame({
        "trade_date": ["20240102"],
        "ts_code": ["000001.SZ"],
        "value": [0.1],
    })
    for name in names:
        storage.write(name, df)
    return storage


def test_validate_registered_missing(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_registered_only"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    storage = _make_storage_with_factors(tmp_path, [])
    reg = FactorRegistry(p)
    result = reg.validate(storage)
    assert isinstance(result, RegistryValidation)
    assert "z_registered_only" in result.registered_missing
    assert result.orphan_stored == ()


def test_validate_orphan_stored(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_registered"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    storage = _make_storage_with_factors(tmp_path, ["z_registered", "z_orphan"])
    reg = FactorRegistry(p)
    result = reg.validate(storage)
    assert result.registered_missing == ()
    assert "z_orphan" in result.orphan_stored


def test_validate_all_clean(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_factor_a"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    storage = _make_storage_with_factors(tmp_path, ["z_factor_a"])
    reg = FactorRegistry(p)
    result = reg.validate(storage)
    assert result.registered_missing == ()
    assert result.orphan_stored == ()
