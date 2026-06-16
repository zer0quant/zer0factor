from __future__ import annotations

WINDOWS = (5, 10, 20, 30, 60, 90, 120, 180)
BASE_RETURN_FACTORS = (
    "daily_return",
    "open_return",
    "intraday_return",
    "overnight_return",
)

__all__ = [
    "BASE_RETURN_FACTORS",
    "WINDOWS",
]
