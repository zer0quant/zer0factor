from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class Ret240_20_RemoveUpLimit(Factor):
    spec = FactorSpec(
        name="ret240_20_remove_up_limit",
        inputs=["close"],
        min_window=260,
        recommended_window=300,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        daily_return = data.close.pct_change()
        log_return = np.log1p(daily_return)
        log_return = log_return.where(daily_return < 0.095, 0.0)
        formation_log_return = log_return.shift(20)
        value = np.exp(
            formation_log_return.rolling(240, min_periods=240).sum()
        ) - 1
        return to_factor_output(value, self.spec.name)
