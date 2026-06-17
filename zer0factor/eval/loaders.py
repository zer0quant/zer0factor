from __future__ import annotations

import pandas as pd

from zer0factor.eval.data import EvaluationDataLoader


def load_stored_factor(storage, factor_name: str, *, start_date: str, end_date: str | None):
    return EvaluationDataLoader(storage, None).load_factor(
        factor_name,
        start_date=start_date,
        end_date=end_date,
    )


def load_price_data(
    pro, *, start_date: str, end_date: str | None, periods: tuple[int, ...]
) -> pd.DataFrame:
    return EvaluationDataLoader(None, pro).load_prices(
        start_date=start_date,
        end_date=end_date,
        periods=periods,
    )


def load_universe_panel(
    pro, *, universe_name: str | None, start_date: str, end_date: str | None
) -> pd.DataFrame | None:
    return EvaluationDataLoader(None, pro).load_universe(
        universe_name=universe_name,
        start_date=start_date,
        end_date=end_date,
    )


def load_index_daily(
    pro,
    *,
    ts_code: str,
    start_date: str,
    end_date: str | None,
) -> pd.Series:
    """
    Returns daily index return Series.
    index: DatetimeIndex (ascending)
    values: pct_chg / 100 (decimal form)
    """
    return EvaluationDataLoader(None, pro).load_benchmark_returns(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
    )
