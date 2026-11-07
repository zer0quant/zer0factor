from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

from tests.eval_fixtures import make_clean_factor_data
from zer0factor.eval.metrics import (
    build_summary,
    calculate_daily_ic,
    calculate_quantile_returns,
)

STANDARD_METADATA = {
    "start_date": "20160101",
    "end_date": None,
    "periods": [1],
    "quantiles": 5,
    "return_type": "open_t1",
    "max_loss": 0.35,
    "universe": "univ_trade_base",
    "rolling_ic_window": 63,
    "transaction_cost_bps": 10.0,
}


def factor_seed(name: str) -> int:
    return sum(ord(c) for c in name)


@lru_cache(maxsize=None)
def _factor_frames(name: str, periods: tuple[str, ...]):
    cfd = make_clean_factor_data(periods=periods, seed=factor_seed(name))
    daily_ic = calculate_daily_ic(cfd)
    qret = calculate_quantile_returns(cfd)
    dates = cfd.index.get_level_values("date")
    summary = build_summary(
        factor_name=name,
        return_type="open_t1",
        clean_factor_data_sample_count=len(cfd),
        clean_factor_data_start=dates.min(),
        clean_factor_data_end=dates.max(),
        quantiles=5,
        daily_ic=daily_ic,
        quantile_returns=qret,
        clean_factor_data=cfd,
        transaction_cost_bps=10.0,
    )
    return cfd, daily_ic, qret, summary


@pytest.fixture
def evaluations_dir(tmp_path) -> Path:
    path = tmp_path / "evaluations"
    path.mkdir()
    return path


@pytest.fixture
def make_run(evaluations_dir):
    def _make_run(
        run_id: str,
        factors: list[str],
        *,
        metadata: dict | None = None,
        periods: tuple[str, ...] = ("1D",),
        write_summary: bool = True,
        write_metadata: bool = True,
        write_clean: bool = True,
    ) -> Path:
        run_dir = evaluations_dir / run_id
        run_dir.mkdir()
        summaries = []
        for name in factors:
            cfd, daily_ic, qret, summary = _factor_frames(name, periods)
            fdir = run_dir / "factors" / name
            fdir.mkdir(parents=True)
            if write_clean:
                cfd.to_parquet(fdir / "clean_factor_data.parquet")
            daily_ic.to_parquet(fdir / "daily_ic.parquet")
            qret.to_parquet(fdir / "quantile_returns.parquet")
            summaries.append(summary)
        if write_summary and summaries:
            pd.concat(summaries, ignore_index=True).to_parquet(
                run_dir / "summary.parquet", index=False
            )
        if write_metadata:
            meta = {
                **STANDARD_METADATA,
                "periods": [int(p.rstrip("D")) for p in periods],
                **(metadata or {}),
                "run_id": run_id,
                "factor_names": factors,
            }
            (run_dir / "metadata.json").write_text(json.dumps(meta))
        return run_dir

    return _make_run


@pytest.fixture
def make_factor_store(tmp_path):
    """Write factor value partitions: factor_dir/<name>/date=YYYYMMDD/data.parquet."""

    def _make(name: str, values: pd.DataFrame) -> Path:
        factor_dir = tmp_path / "factors"
        for date, day in values.groupby("trade_date"):
            part = factor_dir / name / f"date={date}"
            part.mkdir(parents=True, exist_ok=True)
            day[["ts_code", "value"]].to_parquet(part / "data.parquet", index=False)
        (factor_dir / name).mkdir(parents=True, exist_ok=True)
        return factor_dir

    return _make


@pytest.fixture
def make_config(tmp_path, evaluations_dir):
    from zer0factor.config import Config, StandardSetting, WebConfig

    def _make(registry_text: str | None = None, **web_overrides):
        registry = tmp_path / "factors.toml"
        if registry_text is not None:
            registry.write_text(registry_text)
        (tmp_path / "factors").mkdir(exist_ok=True)
        web = WebConfig(
            cache_dir=tmp_path / "web_cache",
            evaluations_dir=evaluations_dir,
            registry_path=registry,
            standard=StandardSetting(quantiles=5),
            **{"state_dir": tmp_path / "workbench", **web_overrides},
        )
        return Config(
            zer0share_data_dir=tmp_path / "zer0share",
            factor_dir=tmp_path / "factors",
            db_path=tmp_path / "factor.duckdb",
            log_path=tmp_path / "factor.log",
            universe="all",
            process_universe="univ_trade_base",
            start_date="20160101",
            end_date="",
            web=web,
        )

    return _make
