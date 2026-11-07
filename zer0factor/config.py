import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalFamilySpec:
    name: str
    module: str
    attribute: str

    @classmethod
    def from_target(cls, name: str, target: str) -> "ExternalFamilySpec":
        module, sep, attribute = target.partition(":")
        if not sep or not module or not attribute:
            raise ValueError(
                f"invalid external family target for {name!r}: {target!r}; "
                "expected 'module:attribute'"
            )
        return cls(name=name, module=module, attribute=attribute)

    @property
    def target(self) -> str:
        return f"{self.module}:{self.attribute}"


@dataclass(frozen=True)
class StandardSetting:
    start_date: str = "20160101"
    quantiles: int = 10
    period: str = "1D"
    return_type: str = "open_t1"
    universe: str = "univ_trade_base"


@dataclass(frozen=True)
class WebConfig:
    cache_dir: Path = Path("data/web_cache")
    evaluations_dir: Path = Path("data/evaluations")
    registry_path: Path = Path("config/factors.toml")
    standard: StandardSetting = StandardSetting()
    state_dir: Path = Path("data/workbench")
    heavy_slots: int = 1
    light_slots: int = 2


def _parse_web(raw: dict) -> WebConfig:
    web = raw.get("web", {})
    standard = web.get("standard", {})
    defaults = StandardSetting()
    paths = {
        key: Path(web[key])
        for key in ("cache_dir", "evaluations_dir", "registry_path", "state_dir")
        if key in web
    }
    tasks = web.get("tasks", {})
    return WebConfig(
        **paths,
        heavy_slots=int(tasks.get("heavy_slots", 1)),
        light_slots=int(tasks.get("light_slots", 2)),
        standard=StandardSetting(
            start_date=str(standard.get("start_date", defaults.start_date)),
            quantiles=int(standard.get("quantiles", defaults.quantiles)),
            period=str(standard.get("period", defaults.period)),
            return_type=str(standard.get("return_type", defaults.return_type)),
            universe=str(standard.get("universe", defaults.universe)),
        ),
    )


@dataclass(frozen=True)
class Config:
    zer0share_data_dir: Path
    factor_dir: Path
    db_path: Path
    log_path: Path
    universe: str
    process_universe: str
    start_date: str
    end_date: str
    notify_webhook_url: str = ""
    external_families: tuple[ExternalFamilySpec, ...] = ()
    web: WebConfig = WebConfig()
    family_packages: tuple[str, ...] = ()

    def external_family_targets(self) -> dict[str, str]:
        return {spec.name: spec.target for spec in self.external_families}


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
            process_universe=raw["factor"].get("process_universe", "univ_trade_base"),
            start_date=raw["factor"]["start_date"],
            end_date=raw["factor"]["end_date"],
            notify_webhook_url=raw.get("notify", {}).get("webhook_url", ""),
            external_families=tuple(
                ExternalFamilySpec.from_target(str(name), str(target))
                for name, target in raw.get("external_families", {}).items()
            ),
            web=_parse_web(raw),
            family_packages=tuple(
                str(p) for p in raw.get("families", {}).get("packages", ())
            ),
        )
    except KeyError as e:
        raise KeyError(f"配置文件缺少必要字段: {e}") from e
