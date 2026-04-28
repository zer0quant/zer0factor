from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    zer0share_data_dir: Path
    factor_dir: Path
    db_path: Path
    log_path: Path
    universe: str
    start_date: str
    end_date: str


def load_config(path: Path = Path("config/settings.toml")) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"配置文件格式错误: {e}") from e
    try:
        return Config(
            zer0share_data_dir=Path(raw["zer0share"]["data_dir"]),
            factor_dir=Path(raw["paths"]["factor_dir"]),
            db_path=Path(raw["paths"]["db_path"]),
            log_path=Path(raw["paths"]["log_path"]),
            universe=raw["factor"]["universe"],
            start_date=raw["factor"]["start_date"],
            end_date=raw["factor"]["end_date"],
        )
    except KeyError as e:
        raise KeyError(f"配置文件缺少必要字段: {e}") from e
