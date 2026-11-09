"""Compute factors from a data provider and persist them."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from zer0factor.core import Factor, run_factor
from zer0factor.core.protocols import DataProvider
from zer0factor.naming import FactorName
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.storage import FactorStorage

ProgressFn = Callable[[int, int, str], None]
LogFn = Callable[[str], None]
PostProcessFn = Callable[[str, pd.DataFrame], dict[str, int]]


class ZScorePostProcess:
    """Post-compute strategy: store a z-scored variant alongside the raw factor."""

    def __init__(
        self,
        storage: FactorStorage,
        config: PreprocessConfig | None = None,
    ) -> None:
        self._storage = storage
        self._pipeline = FactorPreprocessPipeline(config or PreprocessConfig())

    def __call__(self, factor_name: str, raw: pd.DataFrame) -> dict[str, int]:
        z_name = FactorName.parse(factor_name).standardized
        z_scored = self._pipeline.transform(raw)
        self._storage.write(z_name, z_scored)
        return {z_name: len(z_scored)}


class FactorComputeService:
    def __init__(
        self,
        provider: DataProvider,
        storage: FactorStorage,
        *,
        log_info: LogFn | None = None,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._log: LogFn = log_info or (lambda message: None)

    def compute_and_store(
        self,
        factors: tuple[Factor, ...],
        *,
        start_date: str,
        end_date: str | None,
        universe: str,
        progress: ProgressFn | None = None,
        postprocess: PostProcessFn | None = None,
        load_start_date: str | None = None,
    ) -> dict[str, int]:
        """Compute ``factors`` and write dates ``>= start_date``.

        ``load_start_date`` (default: ``start_date``) is where market data loading
        begins; rolling factors need it earlier than ``start_date`` so the first
        written dates see a full window. Only dates ``>= start_date`` are written,
        so partitions before it are left untouched.
        """
        load_start = load_start_date or start_date
        fields = sorted({field for factor in factors for field in factor.spec.inputs})
        adjust_values = {factor.spec.adjust for factor in factors}
        if len(adjust_values) != 1:
            raise ValueError("factors with mixed adjust settings cannot share one data load")

        self._log(
            f"market_data_load_started fields={','.join(fields)} "
            f"load_start={load_start} write_start={start_date}"
        )
        data = self._provider.history(
            fields=fields,
            start_date=load_start,
            end_date=end_date,
            universe=universe,
            adjust=adjust_values.pop(),
            progress=progress,
        )
        self._log("market_data_load_finished")
        self._log("factor_write_stage_started")

        row_counts: dict[str, int] = {}
        for factor in factors:
            name = factor.spec.name
            self._log(f"factor_write_started factor={name}")
            result = run_factor(factor, data)
            if load_start < start_date:
                result = result[result["trade_date"] >= start_date].reset_index(drop=True)
            self._storage.write(name, result)
            row_counts[name] = len(result)
            self._log(f"factor_write_finished factor={name} rows={len(result)}")
            if postprocess is not None:
                row_counts.update(postprocess(name, result))
        return row_counts


def resolve_load_start(
    lookback: int | None,
    *,
    write_start: str,
    history_start: str,
    trading_days_before: Callable[[str, int], str],
) -> str:
    """Where to start loading data so values from ``write_start`` on are exact.

    ``lookback`` is the number of trading days before ``write_start`` a factor
    family needs; ``None`` means unknown or unbounded (recursive indicators), so
    the whole history from ``history_start`` is loaded.
    """
    if write_start <= history_start:
        return write_start
    if lookback is None:
        return history_start
    if lookback <= 0:
        return write_start
    return max(trading_days_before(write_start, lookback), history_start)


def trading_days_before(pro, date: str, n: int, *, exchange: str = "SSE") -> str:
    """The open trading day ``n`` trading days before ``date`` (``date`` excluded)."""
    if n <= 0:
        return date
    # 2x calendar days + a month covers any holiday cluster on the A-share calendar.
    span_days = n * 2 + 30
    start = (pd.Timestamp(date) - pd.Timedelta(days=span_days)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange=exchange, start_date=start, end_date=date, is_open=1)
    days = sorted(d for d in cal["cal_date"].astype(str) if d < date)
    if not days:
        return start
    return days[-n] if len(days) >= n else days[0]
