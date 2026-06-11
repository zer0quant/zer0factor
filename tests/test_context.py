from pathlib import Path

from zer0factor.context import AppContext
from zer0factor.storage import FactorStorage


def _write_settings(tmp_path: Path) -> Path:
    settings = tmp_path / "settings.toml"
    settings.write_text(
        f"""
[zer0share]
data_dir = "{(tmp_path / 'data').as_posix()}"

[paths]
factor_dir = "{(tmp_path / 'factors').as_posix()}"
db_path = "{(tmp_path / 'factor.duckdb').as_posix()}"
log_path = "{(tmp_path / 'logs' / 'app.log').as_posix()}"

[factor]
universe = "all"
start_date = "20240101"
end_date = ""
""",
        encoding="utf-8",
    )
    return settings


def test_from_config_path_loads_config(tmp_path):
    app = AppContext.from_config_path(_write_settings(tmp_path))
    assert app.config.universe == "all"
    assert app.config.start_date == "20240101"


def test_storage_is_built_lazily_and_cached(tmp_path):
    app = AppContext.from_config_path(_write_settings(tmp_path))
    storage = app.storage
    assert isinstance(storage, FactorStorage)
    assert app.storage is storage


def test_configure_logging_creates_log_dir(tmp_path):
    app = AppContext.from_config_path(_write_settings(tmp_path))
    app.configure_logging()
    assert (tmp_path / "logs").is_dir()
