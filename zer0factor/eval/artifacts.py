from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from zer0factor.eval.domain import EvaluationRunConfig


class EvaluationArtifactStore:
    def create_run(self, run) -> None:
        run.run_dir.mkdir(parents=True, exist_ok=False)

    def write_factor_artifacts(
        self,
        result,
        *,
        link_from: Path | None = None,
        link_before_year: int | None = None,
    ) -> dict[str, Path]:
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
            link_from=link_from,
            link_before_year=link_before_year,
        )

    def write_run_summary(self, run, summary: pd.DataFrame) -> dict[str, Path]:
        return write_run_summary(
            run_dir=run.run_dir,
            summary=summary,
            config=run.config,
            run_id=run.run_id,
            extra=_run_metadata_extra(run),
        )


def _run_metadata_extra(run) -> dict[str, object]:
    base = getattr(run, "base_run_dir", None)
    if base is None:
        return {}
    return {
        "mode": "incremental",
        "base_run_id": Path(base).name,
        "data_start_date": getattr(run, "load_start_date", None),
    }


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
    link_from: Path | None = None,
    link_before_year: int | None = None,
) -> dict[str, Path]:
    factor_dir = Path(factor_dir)
    factor_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "clean_factor_data": factor_dir / "clean_factor_data.parquet",
        "daily_ic": factor_dir / "daily_ic.parquet",
        "quantile_returns": factor_dir / "quantile_returns.parquet",
    }
    write_clean_factor_data(
        paths["clean_factor_data"],
        clean_factor_data,
        link_from=link_from,
        link_before_year=link_before_year,
    )
    daily_ic.to_parquet(paths["daily_ic"])
    quantile_returns.to_parquet(paths["quantile_returns"])
    return paths


def write_run_summary(
    *,
    run_dir: str | Path,
    summary: pd.DataFrame,
    config: EvaluationRunConfig,
    run_id: str,
    extra: dict[str, object] | None = None,
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
        json.dumps({**_build_metadata(config=config, run_id=run_id), **(extra or {})}, indent=2)
        + "\n"
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


def write_clean_factor_data(
    path: Path,
    clean_factor_data: pd.DataFrame,
    *,
    link_from: Path | None = None,
    link_before_year: int | None = None,
) -> None:
    """Write clean factor data as a directory of ``<year>.parquet`` files.

    ``pd.read_parquet(path)`` reads the directory back to the identical frame,
    so readers of the former single file keep working. Years before
    ``link_before_year`` whose file exists under ``link_from`` (a base run's
    directory of the same layout) are hard-linked instead of rewritten: an
    incremental run then costs one year of disk, not the whole history.
    """
    path = Path(path)
    if "date" not in (clean_factor_data.index.names or ()):
        # No date level to split on: keep the single-file layout.
        if path.is_dir():
            shutil.rmtree(path)
        clean_factor_data.to_parquet(path)
        return
    if path.is_file():
        path.unlink()
    path.mkdir(parents=True, exist_ok=True)
    years = clean_factor_data.index.get_level_values("date").year
    for year in sorted(set(years)):
        target = path / f"{year}.parquet"
        source = Path(link_from) / f"{year}.parquet" if link_from is not None else None
        if (
            source is not None
            and link_before_year is not None
            and year < link_before_year
            and source.is_file()
        ):
            target.unlink(missing_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
            continue
        # Never write through an existing file: it may be a hard link into a base run.
        target.unlink(missing_ok=True)
        clean_factor_data[years == year].to_parquet(target)
