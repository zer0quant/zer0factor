"""Compute factors from a data provider and persist them."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from zer0factor.core import Factor, run_factor
from zer0factor.core.protocols import DataProvider
from zer0factor.naming import FactorName
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.storage import FactorStorage

ProgressFn = Callable[[int, int, str], None]
LogFn = Callable[[str], None]
PostProcessFn = Callable[[str, pd.DataFrame], dict[str, int]]


class ZScorePostProcess:
    """Post-compute strategy: store a z-scored variant alongside the raw factor."""

    def __init__(
        self,
        storage: FactorStorage,
        config: PreprocessConfig | None = None,
    ) -> None:
        self._storage = storage
        self._pipeline = FactorPreprocessPipeline(config or PreprocessConfig())

    def __call__(self, factor_name: str, raw: pd.DataFrame) -> dict[str, int]:
        z_name = FactorName.parse(factor_name).standardized
        z_scored = self._pipeline.transform(raw)
        self._storage.write(z_name, z_scored)
        return {z_name: len(z_scored)}


class FactorComputeService:
    def __init__(
        self,
        provider: DataProvider,
        storage: FactorStorage,
        *,
        log_info: LogFn | None = None,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._log: LogFn = log_info or (lambda message: None)

    def compute_and_store(
        self,
        factors: tuple[Factor, ...],
        *,
        start_date: str,
        end_date: str | None,
        universe: str,
        progress: ProgressFn | None = None,
        postprocess: PostProcessFn | None = None,
    ) -> dict[str, int]:
        fields = sorted({field for factor in factors for field in factor.spec.inputs})
        adjust_values = {factor.spec.adjust for factor in factors}
        if len(adjust_values) != 1:
            raise ValueError("factors with mixed adjust settings cannot share one data load")

        self._log(f"market_data_load_started fields={','.join(fields)}")
        data = self._provider.history(
            fields=fields,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            adjust=adjust_values.pop(),
            progress=progress,
        )
        self._log("market_data_load_finished")
        self._log("factor_write_stage_started")

        row_counts: dict[str, int] = {}
        for factor in factors:
            name = factor.spec.name
            self._log(f"factor_write_started factor={name}")
            result = run_factor(factor, data, storage=self._storage)
            row_counts[name] = len(result)
            self._log(f"factor_write_finished factor={name} rows={len(result)}")
            if postprocess is not None:
                row_counts.update(postprocess(name, result))
        return row_counts
