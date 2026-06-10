"""Long/wide factor panel transformations shared across services and CLI."""

from __future__ import annotations

import pandas as pd

from zer0factor.core import to_factor_output

LONG_COLUMNS = ("trade_date", "ts_code", "value")


def parse_trade_dates(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d")
    return pd.to_datetime(values)


def long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.loc[:, list(LONG_COLUMNS)].copy()
    frame["trade_date"] = parse_trade_dates(frame["trade_date"])
    if frame.duplicated(["trade_date", "ts_code"]).any():
        raise ValueError("factor data contains duplicate trade_date/ts_code")
    return (
        frame.pivot(index="trade_date", columns="ts_code", values="value")
        .sort_index()
        .sort_index(axis=1)
    )


def wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    return to_factor_output(df)


def filter_panel_by_universe(
    panel: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return panel
    aligned = universe.reindex(index=panel.index, columns=panel.columns, fill_value=False)
    aligned = aligned.astype(bool)
    return panel.where(aligned).dropna(axis=1, how="all")


def filter_long_by_universe(
    factor: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return factor
    return wide_to_long(filter_panel_by_universe(long_to_wide(factor), universe))


def read_universe_panel(
    pro,
    *,
    universe_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    rows = pro.universe(
        universe=universe_name,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,universe,ts_code",
    )
    if rows.empty:
        return pd.DataFrame(dtype=bool)

    frame = rows.loc[:, ["trade_date", "ts_code"]].copy()
    frame["trade_date"] = parse_trade_dates(frame["trade_date"])
    frame["in_universe"] = True
    return (
        frame.drop_duplicates(["trade_date", "ts_code"])
        .pivot(index="trade_date", columns="ts_code", values="in_universe")
        .pipe(lambda df: df.where(df.notna(), False))
        .astype(bool)
        .sort_index()
        .sort_index(axis=1)
    )
