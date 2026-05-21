from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.core import Factor, FactorFrame, FactorSpec, to_factor_output


class LogTotalMarketCap(Factor):
    spec = FactorSpec(
        name="log_total_market_cap",
        inputs=["total_mv"],
        min_window=1,
        frequency="1d",
        adjust=None,
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.total_mv.where(data.total_mv > 0)
        return to_factor_output(np.log(value), self.spec.name)


class LogCirculatingMarketCap(Factor):
    spec = FactorSpec(
        name="log_circulating_market_cap",
        inputs=["circ_mv"],
        min_window=1,
        frequency="1d",
        adjust=None,
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.circ_mv.where(data.circ_mv > 0)
        return to_factor_output(np.log(value), self.spec.name)
