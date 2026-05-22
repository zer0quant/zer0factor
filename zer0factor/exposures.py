from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

SW_L1_INDUSTRY_FIELDS = "l1_code,l1_name,ts_code,in_date,out_date,is_new"


def build_sw_l1_industry_panel(
    pro,
    *,
    dates: Iterable[pd.Timestamp | str],
    ts_codes: Iterable[str],
) -> pd.DataFrame:
    date_index = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    columns = [str(code) for code in ts_codes]
    members = pro.index_member_all(fields=SW_L1_INDUSTRY_FIELDS)
    panel = pd.DataFrame(index=date_index, columns=columns, dtype="object")
    if members.empty or len(date_index) == 0 or len(columns) == 0:
        return panel

    members = members.loc[:, ["l1_code", "ts_code", "in_date", "out_date"]].copy()
    members["ts_code"] = members["ts_code"].astype(str)
    members = members[members["ts_code"].isin(columns)]
    if members.empty:
        return panel

    members["in_date"] = pd.to_datetime(members["in_date"])
    members["out_date"] = pd.to_datetime(members["out_date"])
    members = members.dropna(subset=["l1_code", "ts_code", "in_date"])
    members = members.sort_values(["ts_code", "in_date"])

    for date in date_index:
        active = members[
            (members["in_date"] <= date)
            & (members["out_date"].isna() | (date <= members["out_date"]))
        ]
        if active.empty:
            continue
        latest = active.sort_values("in_date").drop_duplicates("ts_code", keep="last")
        panel.loc[date, latest["ts_code"].to_numpy()] = latest["l1_code"].to_numpy()
    return panel
