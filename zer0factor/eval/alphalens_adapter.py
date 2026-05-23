from __future__ import annotations

import pandas as pd

from zer0factor.eval.config import ReturnType


def _require_columns(data: pd.DataFrame, columns: set[str]) -> None:
    missing = columns.difference(data.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(f"missing required columns: {missing_columns}")


def _parse_trade_date(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.astype(str), format="%Y%m%d", errors="raise")


def factor_long_to_alphalens_series(factor: pd.DataFrame) -> pd.Series:
    _require_columns(factor, {"trade_date", "ts_code", "value"})

    normalized = pd.DataFrame(
        {
            "date": _parse_trade_date(factor["trade_date"]),
            "asset": factor["ts_code"],
            "factor": factor["value"],
        }
    )
    if normalized.duplicated(subset=["date", "asset"]).any():
        raise ValueError("duplicate date/asset rows in factor data")

    result = normalized.set_index(["date", "asset"])["factor"].sort_index()
    result.name = "factor"
    return result


def build_price_matrix(price_data: pd.DataFrame, return_type: ReturnType) -> pd.DataFrame:
    if return_type == "open_t1":
        value_column = "open"
        shift_periods = -1
    elif return_type == "close_t0":
        value_column = "close"
        shift_periods = 0
    else:
        raise ValueError(f"unknown return_type: {return_type}")

    _require_columns(price_data, {"trade_date", "ts_code", value_column})
    normalized = pd.DataFrame(
        {
            "date": _parse_trade_date(price_data["trade_date"]),
            "asset": price_data["ts_code"],
            "price": price_data[value_column],
        }
    )
    matrix = normalized.pivot(index="date", columns="asset", values="price")
    matrix = matrix.sort_index().sort_index(axis=1)
    if shift_periods:
        matrix = matrix.shift(shift_periods)
    return matrix


def filter_factor_by_universe(
    factor: pd.Series, universe: pd.DataFrame | None
) -> pd.Series:
    if universe is None:
        return factor

    membership = pd.Series(
        (bool(universe.at[date, asset]) if date in universe.index and asset in universe.columns else False)
        for date, asset in factor.index
    )
    return factor[membership.to_numpy()]
