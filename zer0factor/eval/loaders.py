from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def load_stored_factor(storage, factor_name: str, *, start_date: str, end_date: str | None):
    return storage.read(factor_name, start_date=start_date, end_date=end_date)


def load_price_data(
    pro, *, start_date: str, end_date: str | None, periods: tuple[int, ...]
) -> pd.DataFrame:
    extended_end = _extend_end_date(end_date or start_date, max(periods) * 3 + 10)
    return pro.pro_bar(
        ts_code=None,
        start_date=start_date,
        end_date=extended_end,
        adj=None,
    )


def load_universe_panel(
    pro, *, universe_name: str | None, start_date: str, end_date: str | None
) -> pd.DataFrame | None:
    if universe_name is None:
        return None

    universe = pro.universe(
        universe=universe_name,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,universe,ts_code",
    )
    if universe.empty:
        return pd.DataFrame(dtype=bool)
    missing_columns = {"trade_date", "ts_code"}.difference(universe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"universe data must contain columns: {missing}")

    universe = universe.dropna(subset=["trade_date", "ts_code"])
    if universe.empty:
        return pd.DataFrame(dtype=bool)

    normalized = pd.DataFrame(
        {
            "date": pd.to_datetime(universe["trade_date"], format="%Y%m%d"),
            "ts_code": universe["ts_code"],
            "member": True,
        }
    )
    panel = normalized.pivot_table(
        index="date",
        columns="ts_code",
        values="member",
        aggfunc="any",
        fill_value=False,
    )
    return panel.astype(bool).sort_index().sort_index(axis=1)


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
    df = pro.index_daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,pct_chg",
    )
    if df.empty:
        return pd.Series(dtype=float, name=ts_code)

    result = (
        df[["trade_date", "pct_chg"]]
        .dropna(subset=["pct_chg"])
        .drop_duplicates(subset=["trade_date"], keep="last")
        .assign(date=lambda d: pd.to_datetime(d["trade_date"], format="%Y%m%d"))
        .set_index("date")["pct_chg"]
        / 100
    )
    result.name = ts_code
    return result.sort_index()


def _extend_end_date(base_date: str, days: int) -> str:
    parsed = datetime.strptime(base_date, "%Y%m%d")
    return (parsed + timedelta(days=days)).strftime("%Y%m%d")
