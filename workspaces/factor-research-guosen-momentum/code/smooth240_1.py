from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class Smooth240_1(Factor):
    spec = FactorSpec(
        name="smooth240_1",
        inputs=["close"],
        min_window=241,
        recommended_window=280,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        daily_return = data.close.pct_change()
        cumulative_return = data.close.shift(1) / data.close.shift(241) - 1
        path_length = daily_return.abs().shift(1).rolling(240, min_periods=240).sum()
        value = cumulative_return / path_length.replace(0, np.nan)
        return to_factor_output(value, self.spec.name)
