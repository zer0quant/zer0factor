import pandas as pd


def standardize(
    factor: pd.DataFrame,
    *,
    method: str = "zscore",
) -> pd.DataFrame:
    if method == "none":
        return factor.copy()
    if method == "zscore":
        return factor.apply(_zscore_row, axis=1)
    if method == "rank_pct":
        return factor.rank(axis=1, pct=True)
    raise ValueError(f"unknown standardization method: {method}")


def _zscore_row(row: pd.Series) -> pd.Series:
    valid = row.dropna()
    if len(valid) < 2:
        return pd.Series(float("nan"), index=row.index, dtype="float64")

    std = valid.std()
    if pd.isna(std) or std == 0:
        return pd.Series(float("nan"), index=row.index, dtype="float64")

    return (row - valid.mean()) / std
