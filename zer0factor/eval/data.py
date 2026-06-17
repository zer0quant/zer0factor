from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd


class EvaluationDataLoader:
    def __init__(self, storage, pro):
        self.storage = storage
        self.pro = pro

    def load_factor(
        self, factor_name: str, *, start_date: str, end_date: str | None
    ) -> pd.DataFrame:
        return self.storage.read(factor_name, start_date=start_date, end_date=end_date)

    def load_prices(
        self, *, start_date: str, end_date: str | None, periods: tuple[int, ...]
    ) -> pd.DataFrame:
        extended_end = _extend_end_date(end_date or start_date, max(periods) * 3 + 10)
        return self.pro.pro_bar(
            ts_code=None,
            start_date=start_date,
            end_date=extended_end,
            adj=None,
        )

    def load_universe(
        self, *, universe_name: str | None, start_date: str, end_date: str | None
    ) -> pd.DataFrame | None:
        if universe_name is None:
            return None

        universe = self.pro.universe(
            universe=universe_name,
            start_date=start_date,
            end_date=end_date,
            fields="trade_date,universe,ts_code",
        )
        return _universe_to_panel(universe)

    def load_benchmark_returns(
        self, *, ts_code: str | None, start_date: str, end_date: str | None
    ) -> pd.Series | None:
        if ts_code is None:
            return None

        df = self.pro.index_daily(
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

    def max_factor_trade_date(
        self, factor_names: Iterable[str], *, start_date: str
    ) -> str:
        max_dates = []
        for factor_name in factor_names:
            factor_data = self.load_factor(
                factor_name,
                start_date=start_date,
                end_date=None,
            )
            if not factor_data.empty:
                max_dates.append(max_factor_trade_date(factor_data))
        if not max_dates:
            return start_date
        return max(max_dates)


def _universe_to_panel(universe: pd.DataFrame) -> pd.DataFrame:
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


def max_factor_trade_date(factor_data: pd.DataFrame) -> str:
    raw_dates = factor_data["trade_date"]
    if pd.api.types.is_numeric_dtype(raw_dates):
        normalized = raw_dates.astype("Int64").astype(str)
    else:
        numeric_dates = pd.to_numeric(raw_dates, errors="coerce")
        if numeric_dates.notna().all():
            normalized = numeric_dates.astype("Int64").astype(str)
        else:
            normalized = raw_dates.astype(str)
    dates = pd.to_datetime(normalized, format="%Y%m%d")
    return dates.max().strftime("%Y%m%d")


def _extend_end_date(base_date: str, days: int) -> str:
    parsed = datetime.strptime(base_date, "%Y%m%d")
    return (parsed + timedelta(days=days)).strftime("%Y%m%d")
