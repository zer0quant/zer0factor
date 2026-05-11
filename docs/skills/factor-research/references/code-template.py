import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class VolumeAdjustedMomentum20D(Factor):
    spec = FactorSpec(
        name="volume_adjusted_momentum_20d",
        inputs=["close", "volume"],
        min_window=20,
        recommended_window=60,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        ret20 = data.close / data.close.shift(20) - 1
        volume_ratio = data.volume.rolling(5).mean() / (
            data.volume.rolling(20).mean() + 1e-8
        )
        value = ret20 * volume_ratio.rank(axis=1, pct=True)
        return to_factor_output(value, self.spec.name)

