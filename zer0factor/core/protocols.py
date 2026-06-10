"""Structural interfaces for external data sources (dependency inversion)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import pandas as pd

if TYPE_CHECKING:
    from zer0factor.core import FactorFrame


@runtime_checkable
class DataProvider(Protocol):
    """Loads standardized field panels for factor computation."""

    def history(
        self,
        fields: Iterable[str],
        start_date: str,
        end_date: str | None,
        universe: str | Iterable[str] = "all",
        adjust: str | None = "hfq",
        progress: Callable[[int, int, str], None] | None = None,
    ) -> "FactorFrame": ...


@runtime_checkable
class UniverseSource(Protocol):
    """Yields universe membership rows (trade_date, universe, ts_code)."""

    def universe(
        self,
        *,
        universe: str,
        start_date: str | None,
        end_date: str | None,
        fields: str,
    ) -> pd.DataFrame: ...


@runtime_checkable
class IndustrySource(Protocol):
    """Yields industry membership rows for exposure construction."""

    def index_member_all(self, fields: str) -> pd.DataFrame: ...
