from pathlib import Path

import pytest

from zer0factor.config import Config, ExternalFamilySpec, load_config


def test_load_config_returns_config(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""
""")
    cfg = load_config(toml)
    assert isinstance(cfg, Config)
    assert cfg.zer0share_data_dir == Path("../zer0share/data")
    assert cfg.factor_dir == Path("data/factors")
    assert cfg.universe == "all"
    assert cfg.process_universe == "univ_trade_base"
    assert cfg.start_date == "20160101"
    assert cfg.end_date == ""


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("nonexistent.toml"))


def test_load_config_missing_key(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("[zer0share]\n")
    with pytest.raises(KeyError):
        load_config(toml)


def test_load_config_reads_notify_webhook_url(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""

[notify]
webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"
""")
    cfg = load_config(toml)
    assert cfg.notify_webhook_url == "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"


def test_load_config_notify_webhook_url_defaults_to_empty(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""
""")
    cfg = load_config(toml)
    assert cfg.notify_webhook_url == ""


def test_load_config_reads_external_families(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""

[external_families]
ma_bias = "zer0alpha.factors:MA_BIAS_FAMILY"
""")
    cfg = load_config(toml)
    assert cfg.external_families == (
        ExternalFamilySpec(
            name="ma_bias",
            module="zer0alpha.factors",
            attribute="MA_BIAS_FAMILY",
        ),
    )
    assert cfg.external_family_targets() == {
        "ma_bias": "zer0alpha.factors:MA_BIAS_FAMILY",
    }


def test_load_config_rejects_invalid_external_family_target(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20160101"
end_date = ""

[external_families]
ma_bias = "zer0alpha.factors.MA_BIAS_FAMILY"
""")

    with pytest.raises(ValueError, match="invalid external family target"):
        load_config(toml)
