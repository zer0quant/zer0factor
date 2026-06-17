from __future__ import annotations

import io
import warnings
from collections.abc import Sequence
from contextlib import contextmanager, redirect_stdout

import pandas as pd
from alphalens.utils import get_clean_factor_and_forward_returns

from zer0factor.eval.metrics import (
    build_summary,
    calculate_daily_ic,
    calculate_quantile_returns,
)


class MetricsCalculator:
    def clean_factor_and_forward_returns(
        self,
        factor: pd.Series,
        prices: pd.DataFrame,
        *,
        quantiles: int,
        periods: Sequence[int],
        max_loss: float,
    ) -> pd.DataFrame:
        with suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return get_clean_factor_and_forward_returns(
                factor,
                prices,
                quantiles=quantiles,
                periods=tuple(periods),
                max_loss=max_loss,
            )

    def calculate_daily_ic(self, clean_factor_data: pd.DataFrame) -> pd.DataFrame:
        with suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return calculate_daily_ic(clean_factor_data)

    def calculate_quantile_returns(self, clean_factor_data: pd.DataFrame) -> pd.DataFrame:
        with suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return calculate_quantile_returns(clean_factor_data)

    def build_factor_summary(self, **kwargs) -> pd.DataFrame:
        with suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return build_summary(**kwargs)

    def calculate_period_sample_counts(
        self,
        factor: pd.Series,
        prices: pd.DataFrame,
        *,
        quantiles: int,
        periods: Sequence[int],
        max_loss: float,
    ) -> dict[str, int]:
        counts = {}
        for period in periods:
            period_label = f"{period}D"
            clean = self.clean_factor_and_forward_returns(
                factor,
                prices,
                quantiles=quantiles,
                periods=(period,),
                max_loss=max_loss,
            )
            counts[period_label] = int(clean[period_label].count()) if period_label in clean else 0
        return counts


@contextmanager
def suppress_known_evaluation_warnings():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=(
                "The default fill_method='pad' in DataFrame.pct_change "
                "is deprecated.*"
            ),
            category=FutureWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Series.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="DataFrame.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Downcasting object dtype arrays on \\.fillna.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Non-vectorized DateOffset being applied.*",
            category=pd.errors.PerformanceWarning,
            module=r"alphalens\.utils",
        )
        yield
