from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

from zer0factor.storage import FactorStorage

STANDARD_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "return_",
        "total_mv",
        "circ_mv",
        "turnover_rate",
    }
)
OUTPUT_SCHEMA = ("trade_date", "ts_code", "value")


@dataclass(frozen=True)
class FactorSpec:
    """Machine-checkable contract for AI-generated factor implementations."""

    name: str
    inputs: Iterable[str]
    min_window: int
    frequency: str = "1d"
    adjust: str | None = "hfq"
    output_schema: tuple[str, str, str] = field(default=OUTPUT_SCHEMA, init=False)

    def __post_init__(self) -> None:
        inputs = tuple(self.inputs)
        if not self.name:
            raise ValueError("factor name is required")
        if not inputs:
            raise ValueError("inputs are required")

        unknown = sorted(set(inputs) - STANDARD_FIELDS)
        if unknown:
            raise ValueError(f"unknown input field(s): {unknown}")

        if self.min_window < 1:
            raise ValueError("min_window must be >= 1")

        if self.adjust not in {"hfq", "qfq", "none", None}:
            raise ValueError("adjust must be one of: hfq, qfq, none")

        object.__setattr__(self, "inputs", inputs)


class FactorFrame:
    """A standardized wide-panel view: each field is date x ts_code."""

    def __init__(self, fields: dict[str, pd.DataFrame]):
        if not fields:
            raise ValueError("FactorFrame requires at least one field")

        unknown = sorted(set(fields) - STANDARD_FIELDS)
        if unknown:
            raise ValueError(f"unknown input field(s): {unknown}")

        normalized: dict[str, pd.DataFrame] = {}
        for name, frame in fields.items():
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"{name} must be a pandas DataFrame")
            normalized[name] = frame.sort_index().sort_index(axis=1)

        self._fields = normalized

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(self._fields)

    def require(self, inputs: Iterable[str]) -> None:
        missing = sorted(set(inputs) - set(self._fields))
        if missing:
            raise ValueError(f"missing input field(s): {missing}")

    def __getattr__(self, name: str) -> pd.DataFrame:
        try:
            return self._fields[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class Factor:
    spec: FactorSpec

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        raise NotImplementedError


class ParametricFactor(Factor):
    """Factor whose spec is determined at instantiation time by constructor parameters."""

    def __init__(self, spec: FactorSpec) -> None:
        self.spec = spec


def to_factor_output(
    value: pd.DataFrame | pd.Series,
    factor_name: str | None = None,
) -> pd.DataFrame:
    if isinstance(value, pd.Series):
        if not isinstance(value.index, pd.MultiIndex) or value.index.nlevels != 2:
            raise ValueError("Series factor output must use a two-level index")
        result = value.dropna().rename("value").reset_index()
    elif isinstance(value, pd.DataFrame):
        wide = value.copy()
        wide.index = pd.to_datetime(wide.index)
        result = wide.stack(future_stack=True).dropna().rename("value").reset_index()
    else:
        raise TypeError("factor output must be a pandas DataFrame or Series")

    result.columns = ["trade_date", "ts_code", "value"]
    result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.strftime("%Y%m%d")
    result = result.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    return result.loc[:, list(OUTPUT_SCHEMA)]


def run_factor(
    factor: Factor,
    data: FactorFrame,
    storage: FactorStorage | None = None,
) -> pd.DataFrame:
    spec = factor.spec
    data.require(spec.inputs)

    result = factor.compute(data)
    if tuple(result.columns) != OUTPUT_SCHEMA:
        raise ValueError(f"factor output columns must be {OUTPUT_SCHEMA}")

    if storage is not None:
        storage.write(spec.name, result)
    return result


class Zer0ShareDataProvider:
    """Adapter from zer0share LocalPro into the decoupled FactorFrame contract."""

    _BAR_SOURCE_COLUMNS = {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "pre_close": "pre_close",
        "volume": "vol",
        "amount": "amount",
        "return_": "pct_chg",
    }
    _DAILY_BASIC_SOURCE_COLUMNS = {
        "total_mv": "total_mv",
        "circ_mv": "circ_mv",
        "turnover_rate": "turnover_rate",
    }
    _DAILY_BASIC_FIELD_ORDER = ("total_mv", "circ_mv", "turnover_rate")

    def __init__(self, pro):
        self._pro = pro

    def history(
        self,
        fields: Iterable[str],
        start_date: str,
        end_date: str | None,
        universe: str | Iterable[str] = "all",
        adjust: str | None = "hfq",
        progress: Callable[[int, int, str], None] | None = None,
    ) -> FactorFrame:
        requested = tuple(fields)
        unknown = sorted(set(requested) - STANDARD_FIELDS)
        if unknown:
            raise ValueError(f"unknown input field(s): {unknown}")

        codes = self._resolve_universe(universe)
        total = len(codes)
        if progress is not None:
            progress(0, total, "")
        if codes:
            ts_code = ",".join(codes)
        else:
            ts_code = ""

        bar_fields = [
            field for field in requested if field in self._BAR_SOURCE_COLUMNS
        ]
        daily_basic_fields = [
            field for field in requested if field in self._DAILY_BASIC_SOURCE_COLUMNS
        ]

        bar_raw = pd.DataFrame(
            columns=["trade_date", "ts_code", *self._BAR_SOURCE_COLUMNS.values()]
        )
        if bar_fields and codes:
            bar_raw = self._pro.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                adj=None if adjust == "none" else adjust,
            )

        daily_basic_raw = pd.DataFrame(
            columns=["trade_date", "ts_code", *self._DAILY_BASIC_SOURCE_COLUMNS.values()]
        )
        if daily_basic_fields and codes:
            daily_basic_source_fields = [
                self._DAILY_BASIC_SOURCE_COLUMNS[field]
                for field in self._DAILY_BASIC_FIELD_ORDER
                if field in daily_basic_fields
            ]
            daily_basic_raw = self._pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=",".join(["ts_code", "trade_date", *daily_basic_source_fields]),
            )
        if progress is not None:
            progress(total, total, codes[-1] if codes else "")

        panels = {}
        for field_name in requested:
            if field_name in self._BAR_SOURCE_COLUMNS:
                panels[field_name] = self._pivot_field(
                    bar_raw, self._BAR_SOURCE_COLUMNS[field_name]
                )
            else:
                panels[field_name] = self._pivot_field(
                    daily_basic_raw, self._DAILY_BASIC_SOURCE_COLUMNS[field_name]
                )
        return FactorFrame(panels)

    def _resolve_universe(self, universe: str | Iterable[str]) -> list[str]:
        if universe == "all":
            basic = self._pro.stock_basic(list_status="L", fields="ts_code")
            return sorted(basic["ts_code"].dropna().astype(str).unique().tolist())
        if isinstance(universe, str):
            return [code.strip() for code in universe.split(",") if code.strip()]
        return sorted(str(code) for code in universe)

    @staticmethod
    def _pivot_field(raw: pd.DataFrame, source_column: str) -> pd.DataFrame:
        if source_column not in raw.columns:
            raise ValueError(f"zer0share result missing source column: {source_column}")

        frame = raw.loc[:, ["trade_date", "ts_code", source_column]].copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d")
        panel = frame.pivot(index="trade_date", columns="ts_code", values=source_column)
        return panel.sort_index().sort_index(axis=1)


__all__ = [
    "Factor",
    "FactorFrame",
    "FactorSpec",
    "ParametricFactor",
    "STANDARD_FIELDS",
    "Zer0ShareDataProvider",
    "run_factor",
    "to_factor_output",
]
