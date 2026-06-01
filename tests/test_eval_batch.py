from pathlib import Path

import pytest

from zer0factor.eval.batch import load_batch_evaluation_config


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "batch.toml"
    p.write_text(content)
    return p


def test_load_batch_explicit_mode_unchanged(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factors = ["z_neu_daily_return", "z_neu_open_return"]
periods = [1, 5, 10]
return_type = "open_t1"
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.factor_names == ("z_neu_daily_return", "z_neu_open_return")
    assert cfg.transaction_cost_bps == 10.0


def test_load_batch_reads_transaction_cost_bps(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factors = ["z_neu_daily_return"]
transaction_cost_bps = 8.5
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.transaction_cost_bps == pytest.approx(8.5)


def test_load_batch_registry_mode_resolves_factors(tmp_path):
    registry = tmp_path / "factors.toml"
    registry.write_text("""
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
enabled = false
description = ""
""")
    p = _write_toml(tmp_path, f"""
[evaluation]
factor_source = "registry"
registry_path = "{registry}"
enabled_only = true
periods = [1, 5, 10]
return_type = "open_t1"
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.factor_names == ("z_neu_daily_return",)


def test_load_batch_registry_mode_category_filter(tmp_path):
    registry = tmp_path / "factors.toml"
    registry.write_text("""
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
    p = _write_toml(tmp_path, f"""
[evaluation]
factor_source = "registry"
registry_path = "{registry}"
categories = ["price"]
enabled_only = false
periods = [1, 5]
return_type = "open_t1"
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.factor_names == ("z_price_factor",)


def test_load_batch_registry_mode_no_matches_raises(tmp_path):
    registry = tmp_path / "factors.toml"
    registry.write_text("""
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = false
description = ""
""")
    p = _write_toml(tmp_path, f"""
[evaluation]
factor_source = "registry"
registry_path = "{registry}"
enabled_only = true
periods = [1, 5, 10]
return_type = "open_t1"
""")
    with pytest.raises(ValueError, match="no factors matched"):
        load_batch_evaluation_config(p)


def test_load_batch_invalid_factor_source_raises(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factor_source = "unknown"
factors = ["z_neu_daily_return"]
""")
    with pytest.raises(ValueError, match="unknown factor_source"):
        load_batch_evaluation_config(p)
