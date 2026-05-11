from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class RankMom120_20(Factor):
    spec = FactorSpec(
        name="rank_mom120_20",
        inputs=["close"],
        min_window=140,
        recommended_window=180,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        daily_return = data.close.pct_change()
        ranks = daily_return.rank(axis=1, method="average")
        counts = daily_return.notna().sum(axis=1)
        center = (counts + 1) / 2
        scale = pd.Series(np.nan, index=counts.index)
        valid_counts = counts > 1
        scale.loc[valid_counts] = np.sqrt(
            ((counts.loc[valid_counts] - 1) * (counts.loc[valid_counts] + 1)) / 12
        )
        standardized_rank = ranks.sub(center, axis=0).div(scale.replace(0, np.nan), axis=0)
        value = standardized_rank.shift(20).rolling(120, min_periods=120).mean()
        return to_factor_output(value, self.spec.name)
