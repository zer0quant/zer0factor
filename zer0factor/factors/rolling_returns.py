from __future__ import annotations

import pandas as pd

from zer0factor.families import FactorFamily

WINDOWS = (5, 10, 20, 30, 60, 90, 120, 180)
BASE_RETURN_FACTORS = (
    "daily_return",
    "open_return",
    "intraday_return",
    "overnight_return",
)


class RollingReturnFamily(FactorFamily):
    name = "rolling_return"
    base_factors = BASE_RETURN_FACTORS
    windows = WINDOWS

    def raw_name(self, base_factor: str, window: int) -> str:
        return f"{base_factor}_ma{window}"

    def derive(self, panel: pd.DataFrame, window: int) -> pd.DataFrame:
        return panel.rolling(window=window, min_periods=window // 2).mean()

    def parse_raw_name(self, raw_name: str) -> dict[str, object]:
        for base in self.base_factors:
            if raw_name.startswith(base):
                window = int(raw_name.removeprefix(f"{base}_ma"))
                return {"base_factor": base, "window": window}
        raise ValueError(f"cannot parse raw factor name: {raw_name!r}")


__all__ = [
    "BASE_RETURN_FACTORS",
    "RollingReturnFamily",
    "WINDOWS",
]
