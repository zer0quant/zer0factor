import numpy as np
import pandas as pd


def impute_missing(
    factor: pd.DataFrame,
    *,
    method: str = "cross_section_median",
    industry: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cleaned = factor.replace([np.inf, -np.inf], np.nan)

    if method == "none":
        return cleaned.copy()

    if method == "cross_section_median":
        row_medians = cleaned.median(axis=1)
        return cleaned.T.fillna(row_medians).T

    if method == "industry_median":
        if industry is None:
            raise ValueError("industry_median imputation requires industry data")
        raise ValueError("industry_median imputation is not implemented")

    raise ValueError(f"unknown imputation method: {method}")
