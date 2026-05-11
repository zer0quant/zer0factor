from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class OverNightMom20(Factor):
    spec = FactorSpec(
        name="overnight_mom20",
        inputs=["open", "close"],
        min_window=20,
        recommended_window=60,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        overnight_return = np.log(data.open / data.close.shift(1))
        value = overnight_return.rolling(20, min_periods=20).sum()
        return to_factor_output(value, self.spec.name)
