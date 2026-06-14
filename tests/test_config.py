from pathlib import Path

import pytest

from zer0factor.config import Config, load_config


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
