"""Standardize and neutralize stored factors."""

from __future__ import annotations

import pandas as pd

from zer0factor.core.protocols import IndustrySource
from zer0factor.exposures import build_sw_l1_industry_panel
from zer0factor.naming import FactorName
from zer0factor.panel import (
    filter_long_by_universe,
    filter_panel_by_universe,
    long_to_wide,
    wide_to_long,
)
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.storage import FactorStorage

NEUTRALIZATION_SIZE_FACTOR = "z_log_circulating_market_cap"

_NEUTRALIZE_ONLY = PreprocessConfig(
    winsorize_method="none",
    impute_method="none",
    standardize_method="none",
    neutralize_method="size_industry",
)
_ZSCORE_ONLY = PreprocessConfig(
    winsorize_method="none",
    impute_method="none",
    standardize_method="zscore",
    neutralize_method=None,
)


class FactorPreprocessService:
    def __init__(
        self,
        storage: FactorStorage,
        industry_source: IndustrySource | None = None,
    ) -> None:
        self._storage = storage
        self._industry_source = industry_source

    def standardize(
        self,
        factor_name: str,
        *,
        output_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        config: PreprocessConfig | None = None,
        universe: pd.DataFrame | None = None,
    ) -> int:
        resolved_output = output_name or FactorName.parse(factor_name).standardized
        source = self._storage.read(factor_name, start_date=start_date, end_date=end_date)
        source = filter_long_by_universe(source, universe)
        pipeline = FactorPreprocessPipeline(config or PreprocessConfig())
        output = pipeline.transform(source)
        self._storage.write(resolved_output, output)
        return len(output)

    def neutralize(
        self,
        factor_name: str,
        *,
        output_name: str | None = None,
        size_factor_name: str = NEUTRALIZATION_SIZE_FACTOR,
        start_date: str | None = None,
        end_date: str | None = None,
        universe: pd.DataFrame | None = None,
    ) -> int:
        if self._industry_source is None:
            raise ValueError("neutralize requires an industry_source")

        name = FactorName.parse(factor_name)
        resolved_output = output_name or name.neutralized
        source = self._storage.read(
            name.standardized, start_date=start_date, end_date=end_date
        )
        size = self._storage.read(
            size_factor_name, start_date=start_date, end_date=end_date
        )
        source_panel = long_to_wide(source)
        size_panel = long_to_wide(size)
        dates = source_panel.index.intersection(size_panel.index)
        ts_codes = source_panel.columns.intersection(size_panel.columns)
        source_panel = source_panel.reindex(index=dates, columns=ts_codes)
        size_panel = size_panel.reindex(index=dates, columns=ts_codes)
        source_panel = filter_panel_by_universe(source_panel, universe)
        size_panel = size_panel.reindex(
            index=source_panel.index, columns=source_panel.columns
        )
        industry_panel = build_sw_l1_industry_panel(
            self._industry_source, dates=dates, ts_codes=ts_codes
        )
        industry_panel = industry_panel.reindex(
            index=source_panel.index, columns=source_panel.columns
        )

        residual = FactorPreprocessPipeline(_NEUTRALIZE_ONLY).transform(
            source_panel,
            exposures={"size": size_panel, "industry": industry_panel},
        )
        standardized = FactorPreprocessPipeline(_ZSCORE_ONLY).transform(residual)
        output = wide_to_long(standardized)
        self._storage.write(resolved_output, output)
        return len(output)
