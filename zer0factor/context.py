"""Composition root: builds and caches application dependencies from config."""

from __future__ import annotations

import sys
from functools import cached_property
from pathlib import Path

from loguru import logger

from zer0factor.config import Config, load_config
from zer0factor.storage import FactorStorage

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}"


class AppContext:
    def __init__(self, config: Config) -> None:
        self.config = config

    @classmethod
    def from_config_path(cls, path: Path) -> AppContext:
        return cls(load_config(Path(path)))

    @cached_property
    def storage(self) -> FactorStorage:
        return FactorStorage(self.config.factor_dir, self.config.db_path)

    @cached_property
    def pro(self):
        from zer0share.api import LocalPro

        return LocalPro(self.config.zer0share_data_dir)

    @cached_property
    def provider(self):
        from zer0factor.core import Zer0ShareDataProvider

        return Zer0ShareDataProvider(self.pro)

    def configure_logging(self) -> None:
        log_path = self.config.log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.remove()
        logger.add(sys.stderr, level="INFO", format=LOG_FORMAT)
        logger.add(
            log_path,
            level="INFO",
            format=LOG_FORMAT,
            rotation="100 MB",
            retention=10,
            enqueue=True,
        )
