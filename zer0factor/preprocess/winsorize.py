import pandas as pd


def winsorize(
    factor: pd.DataFrame,
    *,
    method: str = "mad",
    n: float = 5.0,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
) -> pd.DataFrame:
    if method == "none":
        return factor.copy()
    if method == "mad":
        if n <= 0:
            raise ValueError("n must be positive")
        return factor.apply(lambda row: _winsorize_mad_row(row, n), axis=1)
    if method == "quantile":
        if not 0 <= lower_quantile < upper_quantile <= 1:
            raise ValueError("quantiles must satisfy 0 <= lower < upper <= 1")
        return factor.apply(
            lambda row: _winsorize_quantile_row(row, lower_quantile, upper_quantile),
            axis=1,
        )
    raise ValueError(f"unknown winsorization method: {method}")


def _winsorize_mad_row(row: pd.Series, n: float) -> pd.Series:
    median = row.median(skipna=True)
    mad = (row - median).abs().median(skipna=True)
    if pd.isna(median) or pd.isna(mad) or mad == 0:
        return row
    return row.clip(lower=median - n * mad, upper=median + n * mad)


def _winsorize_quantile_row(
    row: pd.Series,
    lower_quantile: float,
    upper_quantile: float,
) -> pd.Series:
    lower = row.quantile(lower_quantile)
    upper = row.quantile(upper_quantile)
    if pd.isna(lower) or pd.isna(upper):
        return row
    return row.clip(lower=lower, upper=upper)
