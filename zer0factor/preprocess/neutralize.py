from typing import Literal

import pandas as pd


def neutralize(
    factor: pd.DataFrame,
    *,
    method: Literal["size_industry", "none"] | None = None,
    exposures: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if method is None or method == "none":
        return factor.copy()
    if method == "size_industry":
        raise ValueError("neutralization requires implemented exposure regression support")
    raise ValueError(f"unknown neutralization method: {method}")
