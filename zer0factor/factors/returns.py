from __future__ import annotations

import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class DailyReturn(Factor):
    spec = FactorSpec(
        name="daily_return",
        inputs=["close"],
        min_window=1,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.close / data.close.shift(1) - 1
        return to_factor_output(value, self.spec.name)


class OpenReturn(Factor):
    spec = FactorSpec(
        name="open_return",
        inputs=["open"],
        min_window=1,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.open / data.open.shift(1) - 1
        return to_factor_output(value, self.spec.name)


class IntradayReturn(Factor):
    spec = FactorSpec(
        name="intraday_return",
        inputs=["open", "close"],
        min_window=1,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.close / data.open - 1
        return to_factor_output(value, self.spec.name)


class OvernightReturn(Factor):
    spec = FactorSpec(
        name="overnight_return",
        inputs=["open", "close"],
        min_window=1,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.open / data.close.shift(1) - 1
        return to_factor_output(value, self.spec.name)
