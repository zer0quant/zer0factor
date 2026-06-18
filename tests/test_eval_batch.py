from pathlib import Path

import pytest

from zer0factor.eval.batch import BatchEvaluationConfig, load_batch_evaluation_config
from zer0factor.eval.report import ReportThresholds


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


def test_load_batch_reads_workers(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factors = ["z_neu_daily_return"]
workers = 16
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.workers == 16


def test_load_batch_reads_report_thresholds(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factors = ["z_neu_daily_return"]

[report]
min_ic = 0.01
min_monotonicity = 0.4
""")
    cfg = load_batch_evaluation_config(p)
    assert hasattr(cfg, "report_thresholds")
    assert cfg.report_thresholds.min_ic == pytest.approx(0.01)
    assert cfg.report_thresholds.min_monotonicity == pytest.approx(0.4)


def test_batch_config_to_request_carries_evaluation_fields(tmp_path):
    thresholds = ReportThresholds(min_ic=0.02)
    cfg = BatchEvaluationConfig(
        factor_names=("factor_a", "factor_b"),
        start_date="20240101",
        end_date="20240201",
        periods=(1, 5),
        quantiles=7,
        return_type="close_t0",
        universe="custom_universe",
        max_loss=0.25,
        workers=4,
        output_dir=tmp_path / "evaluations",
        transaction_cost_bps=6.5,
        report_thresholds=thresholds,
    )

    request = cfg.to_request()

    assert request.factor_names == ("factor_a", "factor_b")
    assert request.start_date == "20240101"
    assert request.end_date == "20240201"
    assert request.periods == (1, 5)
    assert request.quantiles == 7
    assert request.return_type == "close_t0"
    assert request.universe == "custom_universe"
    assert request.max_loss == pytest.approx(0.25)
    assert request.workers == 4
    assert request.transaction_cost_bps == pytest.approx(6.5)
    assert request.report_thresholds == thresholds
    assert request.generate_report is True


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
