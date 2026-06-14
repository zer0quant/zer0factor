from __future__ import annotations

import pandas as pd

WINDOWS = (5, 10, 20, 30, 60, 90, 120, 180)
BASE_RETURN_FACTORS = (
    "daily_return",
    "open_return",
    "intraday_return",
    "overnight_return",
)
PROFILE_PREFIXES = (
    ("z_size_industry_neu_", "z_size_industry_neu"),
    ("z_industry_neu_", "z_industry_neu"),
    ("z_size_neu_", "z_size_neu"),
    ("z_", "z"),
)


def raw_factor_name(base_factor: str, window: int) -> str:
    return f"{base_factor}_ma{window}"


def raw_factor_names() -> tuple[str, ...]:
    return tuple(
        raw_factor_name(base_factor, window)
        for base_factor in BASE_RETURN_FACTORS
        for window in WINDOWS
    )


def parse_rolling_return_name(factor_name: str) -> dict[str, int | str]:
    preprocess = "raw"
    raw_name = factor_name
    for prefix, profile in PROFILE_PREFIXES:
        if factor_name.startswith(prefix):
            preprocess = profile
            raw_name = factor_name.removeprefix(prefix)
            break

    base_factor = next(
        (
            name
            for name in BASE_RETURN_FACTORS
            if raw_name.startswith(f"{name}_")
        ),
        None,
    )
    if base_factor is None:
        raise ValueError(f"unknown rolling return factor name: {factor_name}")

    suffix = raw_name.removeprefix(f"{base_factor}_ma")
    if suffix == raw_name or not suffix.isdigit():
        raise ValueError(f"factor name does not end with _ma<window>: {factor_name}")
    window = int(suffix)
    if window not in WINDOWS:
        raise ValueError(f"unsupported rolling return window: {factor_name}")

    return {
        "base_factor": base_factor,
        "preprocess": preprocess,
        "window": window,
    }


def derive_rolling_mean_panel(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return panel.rolling(window=window, min_periods=window // 2).mean()


__all__ = [
    "BASE_RETURN_FACTORS",
    "PROFILE_PREFIXES",
    "WINDOWS",
    "derive_rolling_mean_panel",
    "parse_rolling_return_name",
    "raw_factor_name",
    "raw_factor_names",
]
