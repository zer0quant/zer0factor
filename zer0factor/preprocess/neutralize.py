from typing import Literal

import numpy as np
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
        if exposures is None or "size" not in exposures or "industry" not in exposures:
            raise ValueError(
                "size_industry neutralization requires size and industry exposures"
            )
        return _neutralize_size_industry(
            factor,
            size=exposures["size"],
            industry=exposures["industry"],
        )
    raise ValueError(f"unknown neutralization method: {method}")


def _neutralize_size_industry(
    factor: pd.DataFrame,
    *,
    size: pd.DataFrame,
    industry: pd.DataFrame,
) -> pd.DataFrame:
    _validate_unique_axes(factor, "factor")
    _validate_unique_axes(size, "size")
    _validate_unique_axes(industry, "industry")

    aligned_size = size.reindex(index=factor.index, columns=factor.columns)
    aligned_industry = industry.reindex(index=factor.index, columns=factor.columns)
    result = pd.DataFrame(np.nan, index=factor.index, columns=factor.columns, dtype="float64")

    for date in factor.index:
        y = pd.to_numeric(factor.loc[date], errors="coerce").replace(
            [np.inf, -np.inf],
            np.nan,
        )
        size_row = pd.to_numeric(aligned_size.loc[date], errors="coerce").replace(
            [np.inf, -np.inf],
            np.nan,
        )
        industry_row = aligned_industry.loc[date]
        valid = y.notna() & size_row.notna() & industry_row.map(_is_finite_or_label)

        if not valid.any():
            continue

        valid_index = valid.index[valid]
        design = pd.DataFrame(
            {
                "intercept": 1.0,
                "size": size_row.loc[valid_index].astype(float),
            },
            index=valid_index,
        )
        industry_dummies = pd.get_dummies(
            industry_row.loc[valid_index],
            drop_first=True,
            dtype=float,
        )
        design = pd.concat([design, industry_dummies], axis=1)

        if len(valid_index) <= design.shape[1]:
            continue

        x_values = design.to_numpy(dtype=float)
        y_values = y.loc[valid_index].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(x_values, y_values, rcond=None)
        result.loc[date, valid_index] = y_values - x_values @ beta

    return result


def _validate_unique_axes(frame: pd.DataFrame, name: str) -> None:
    if frame.index.has_duplicates:
        raise ValueError(f"{name} exposure has duplicate index labels")
    if frame.columns.has_duplicates:
        raise ValueError(f"{name} exposure has duplicate column labels")


def _is_finite_or_label(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (int, float, np.number)):
        return bool(np.isfinite(value))
    return True
