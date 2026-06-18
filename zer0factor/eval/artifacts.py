from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from zer0factor.eval.domain import EvaluationRunConfig


class EvaluationArtifactStore:
    def create_run(self, run) -> None:
        run.run_dir.mkdir(parents=True, exist_ok=False)

    def write_factor_artifacts(self, result) -> dict[str, Path]:
        if result.clean_factor_data is None:
            raise ValueError("clean_factor_data is required to write factor artifacts")
        if result.daily_ic is None:
            raise ValueError("daily_ic is required to write factor artifacts")
        if result.quantile_returns is None:
            raise ValueError("quantile_returns is required to write factor artifacts")
        return write_factor_artifacts(
            factor_dir=result.output_dir,
            clean_factor_data=result.clean_factor_data,
            daily_ic=result.daily_ic,
            quantile_returns=result.quantile_returns,
        )

    def write_run_summary(self, run, summary: pd.DataFrame) -> dict[str, Path]:
        return write_run_summary(
            run_dir=run.run_dir,
            summary=summary,
            config=run.config,
            run_id=run.run_id,
        )


def create_run_directory(
    config: EvaluationRunConfig, run_id: str | None = None
) -> tuple[str, Path]:
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    run_dir = config.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def write_factor_artifacts(
    *,
    factor_dir: str | Path,
    clean_factor_data: pd.DataFrame,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
) -> dict[str, Path]:
    factor_dir = Path(factor_dir)
    factor_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "clean_factor_data": factor_dir / "clean_factor_data.parquet",
        "daily_ic": factor_dir / "daily_ic.parquet",
        "quantile_returns": factor_dir / "quantile_returns.parquet",
    }
    clean_factor_data.to_parquet(paths["clean_factor_data"])
    daily_ic.to_parquet(paths["daily_ic"])
    quantile_returns.to_parquet(paths["quantile_returns"])
    return paths


def write_run_summary(
    *,
    run_dir: str | Path,
    summary: pd.DataFrame,
    config: EvaluationRunConfig,
    run_id: str,
) -> dict[str, Path]:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "summary_csv": run_dir / "summary.csv",
        "summary_parquet": run_dir / "summary.parquet",
        "metadata": run_dir / "metadata.json",
    }
    summary.to_csv(paths["summary_csv"], index=False)
    summary.to_parquet(paths["summary_parquet"], index=False)
    paths["metadata"].write_text(
        json.dumps(_build_metadata(config=config, run_id=run_id), indent=2) + "\n"
    )
    return paths


def _build_metadata(*, config: EvaluationRunConfig, run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "factor_names": list(config.factor_names),
        "start_date": config.start_date,
        "end_date": config.end_date,
        "periods": list(config.periods),
        "quantiles": config.quantiles,
        "return_type": config.return_type,
        "max_loss": config.max_loss,
        "universe": config.universe,
        "rolling_ic_window": config.rolling_ic_window,
        "transaction_cost_bps": config.transaction_cost_bps,
    }
