from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.eval.domain import ReturnType


def _require_columns(data: pd.DataFrame, columns: set[str]) -> None:
    missing = columns.difference(data.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(f"missing required columns: {missing_columns}")


def _parse_trade_date(values: pd.Series) -> pd.Series:
    if pd.api.types.is_integer_dtype(values) and not values.isna().any():
        # Fast path for hive-partitioned factor reads (int64 YYYYMMDD).
        normalized = values.astype("int64").astype(str)
    else:
        normalized = values.map(_normalize_trade_date)
    return pd.to_datetime(normalized, format="%Y%m%d", errors="raise")


def _normalize_trade_date(value: object) -> object:
    if pd.isna(value):
        return value
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return str(value)


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
    if normalized.duplicated(subset=["date", "asset"]).any():
        raise ValueError("duplicate date/asset rows in price data")

    matrix = normalized.pivot(index="date", columns="asset", values="price")
    matrix = matrix.sort_index().sort_index(axis=1)
    if shift_periods:
        matrix = matrix.shift(shift_periods)
    return matrix


def filter_factor_by_universe(
    factor: pd.Series, universe: pd.DataFrame | None
) -> pd.Series:
    """Keep (date, asset) rows whose universe cell is non-null and truthy.

    Rows whose date or asset is absent from the universe panel are dropped.
    """
    if universe is None:
        return factor
    if factor.empty or universe.empty:
        return factor.iloc[0:0]

    rows = universe.index.get_indexer(factor.index.get_level_values(0))
    cols = universe.columns.get_indexer(factor.index.get_level_values(1))
    found = (rows >= 0) & (cols >= 0)
    cells = universe.to_numpy()[rows[found], cols[found]]
    if cells.dtype != bool:
        present = pd.notna(cells)
        truthy = np.zeros(len(cells), dtype=bool)
        truthy[present] = cells[present].astype(bool)
        cells = truthy
    membership = np.zeros(len(factor), dtype=bool)
    membership[found] = cells
    return factor[membership]
