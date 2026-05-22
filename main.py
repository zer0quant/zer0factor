import sys
from collections.abc import Callable
from pathlib import Path

import click
import pandas as pd
from loguru import logger

from zer0factor.config import load_config
from zer0factor.core import Factor, Zer0ShareDataProvider, run_factor
from zer0factor.exposures import build_sw_l1_industry_panel
from zer0factor.factors import (
    DailyReturn,
    IntradayReturn,
    LogCirculatingMarketCap,
    LogTotalMarketCap,
    OpenReturn,
    OvernightReturn,
)
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.storage import FactorStorage

RETURN_FACTORS = (
    DailyReturn(),
    OpenReturn(),
    IntradayReturn(),
    OvernightReturn(),
)
MARKET_CAP_FACTORS = (
    LogTotalMarketCap(),
    LogCirculatingMarketCap(),
)
MARKET_CAP_PREPROCESS_CONFIG = PreprocessConfig(
    winsorize_method="mad",
    winsorize_n=5.0,
    impute_method="cross_section_median",
    standardize_method="zscore",
    neutralize_method=None,
)
STANDARD_PREPROCESS_CONFIG = MARKET_CAP_PREPROCESS_CONFIG
NEUTRALIZATION_SIZE_FACTOR = "z_log_circulating_market_cap"
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}"


@click.group()
@click.option("--config", default="config/settings.toml", show_default=True)
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config)


@cli.command()
@click.pass_context
def status(ctx):
    """Show factor library status."""
    cfg = load_config(ctx.obj["config_path"])
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    factors = storage.list_factors()
    if not factors:
        click.echo("No factors computed yet.")
    else:
        click.echo(f"Factors ({len(factors)}):")
        for name in factors:
            click.echo(f"  {name}")


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO", format=LOG_FORMAT)
    logger.add(
        log_path,
        level="INFO",
        format=LOG_FORMAT,
        rotation="100 MB",
        retention=10,
        enqueue=True,
    )


def compute_and_store_factors(
    factors: tuple[Factor, ...],
    provider: Zer0ShareDataProvider,
    storage: FactorStorage,
    start_date: str,
    end_date: str | None,
    universe: str,
    progress: Callable[[int, int, str], None] | None = None,
    log_info: Callable[[str], None] | None = None,
) -> dict[str, int]:
    fields = sorted({field for factor in factors for field in factor.spec.inputs})
    adjust_values = {factor.spec.adjust for factor in factors}
    if len(adjust_values) != 1:
        raise ValueError("factors with mixed adjust settings cannot share one data load")

    if log_info is not None:
        log_info(f"market_data_load_started fields={','.join(fields)}")
    data = provider.history(
        fields=fields,
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        adjust=adjust_values.pop(),
        progress=progress,
    )
    if log_info is not None:
        log_info("market_data_load_finished")
    if log_info is not None:
        log_info("factor_write_stage_started")
    row_counts = {}
    for factor in factors:
        if log_info is not None:
            log_info(f"factor_write_started factor={factor.spec.name}")
        result = run_factor(factor, data, storage=storage)
        row_counts[factor.spec.name] = len(result)
        if log_info is not None:
            log_info(f"factor_write_finished factor={factor.spec.name} rows={len(result)}")
    return row_counts


def compute_and_store_market_cap_factors(
    factors: tuple[Factor, ...],
    provider: Zer0ShareDataProvider,
    storage: FactorStorage,
    start_date: str,
    end_date: str | None,
    universe: str,
    progress: Callable[[int, int, str], None] | None = None,
    log_info: Callable[[str], None] | None = None,
) -> dict[str, int]:
    fields = sorted({field for factor in factors for field in factor.spec.inputs})

    if log_info is not None:
        log_info(f"market_cap_data_load_started fields={','.join(fields)}")
    data = provider.history(
        fields=fields,
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        adjust=None,
        progress=progress,
    )
    if log_info is not None:
        log_info("market_cap_data_load_finished")

    pipeline = FactorPreprocessPipeline(MARKET_CAP_PREPROCESS_CONFIG)
    row_counts = {}
    for factor in factors:
        if log_info is not None:
            log_info(f"market_cap_factor_write_started factor={factor.spec.name}")
        raw = run_factor(factor, data, storage=storage)
        row_counts[factor.spec.name] = len(raw)

        z_name = f"z_{factor.spec.name}"
        z_scored = pipeline.transform(raw)
        storage.write(z_name, z_scored)
        row_counts[z_name] = len(z_scored)
        if log_info is not None:
            log_info(
                "market_cap_factor_write_finished "
                f"factor={factor.spec.name} rows={len(raw)} "
                f"z_factor={z_name} z_rows={len(z_scored)}"
            )
    return row_counts


def neutralize_stored_factor(
    *,
    factor_name: str,
    output_name: str,
    storage: FactorStorage,
    pro,
    start_date: str | None = None,
    end_date: str | None = None,
    size_factor_name: str = NEUTRALIZATION_SIZE_FACTOR,
) -> int:
    source = storage.read(factor_name, start_date=start_date, end_date=end_date)
    size = storage.read(size_factor_name, start_date=start_date, end_date=end_date)
    source_panel = _factor_long_to_wide(source)
    size_panel = _factor_long_to_wide(size)
    dates = source_panel.index.intersection(size_panel.index)
    ts_codes = source_panel.columns.intersection(size_panel.columns)
    source_panel = source_panel.reindex(index=dates, columns=ts_codes)
    size_panel = size_panel.reindex(index=dates, columns=ts_codes)
    industry_panel = build_sw_l1_industry_panel(pro, dates=dates, ts_codes=ts_codes)

    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="none",
            neutralize_method="size_industry",
        )
    )
    result = pipeline.transform(
        source_panel,
        exposures={"size": size_panel, "industry": industry_panel},
    )
    output = _factor_wide_to_long(result)
    storage.write(output_name, output)
    return len(output)


def preprocess_stored_factor(
    *,
    factor_name: str,
    output_name: str,
    storage: FactorStorage,
    start_date: str | None = None,
    end_date: str | None = None,
    config: PreprocessConfig = STANDARD_PREPROCESS_CONFIG,
) -> int:
    source = storage.read(factor_name, start_date=start_date, end_date=end_date)
    pipeline = FactorPreprocessPipeline(config)
    output = pipeline.transform(source)
    storage.write(output_name, output)
    return len(output)


def _factor_long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.loc[:, ["trade_date", "ts_code", "value"]].copy()
    frame["trade_date"] = _parse_trade_dates(frame["trade_date"])
    if frame.duplicated(["trade_date", "ts_code"]).any():
        raise ValueError("factor data contains duplicate trade_date/ts_code")
    return (
        frame.pivot(index="trade_date", columns="ts_code", values="value")
        .sort_index()
        .sort_index(axis=1)
    )


def _parse_trade_dates(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d")
    return pd.to_datetime(values)


def _factor_wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.index = pd.to_datetime(result.index)
    long = result.stack(future_stack=True).dropna().rename("value").reset_index()
    long.columns = ["trade_date", "ts_code", "value"]
    long["trade_date"] = pd.to_datetime(long["trade_date"]).dt.strftime("%Y%m%d")
    return long.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)


@cli.command("compute-returns")
@click.pass_context
def compute_returns(ctx):
    """Compute built-in return factors and store them locally."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    end_date = cfg.end_date or None
    configure_logging(cfg.log_path)
    logger.info(
        "return_factor_job_started universe={} start_date={} end_date={} fields={}",
        cfg.universe,
        cfg.start_date,
        end_date or "latest",
        "close,open",
    )

    def show_progress(index: int, total: int, code: str) -> None:
        if index == 0:
            logger.info("universe_resolved stocks={}", total)
        elif index == total or index % 100 == 0:
            logger.info("market_data_load_progress loaded={} total={} code={}", index, total, code)

    provider = Zer0ShareDataProvider(LocalPro(cfg.zer0share_data_dir))
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    row_counts = compute_and_store_factors(
        factors=RETURN_FACTORS,
        provider=provider,
        storage=storage,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        log_info=logger.info,
    )
    for factor_name, row_count in row_counts.items():
        logger.info("return_factor_rows factor={} rows={}", factor_name, row_count)
    logger.info("return_factor_job_finished factors={}", len(row_counts))


@cli.command("compute-market-cap")
@click.pass_context
def compute_market_cap(ctx):
    """Compute built-in market cap factors and store raw plus z-scored values."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    end_date = cfg.end_date or None
    logger.info(
        "market_cap_factor_job_started universe={} start_date={} end_date={} fields={}",
        cfg.universe,
        cfg.start_date,
        end_date or "latest",
        "circ_mv,total_mv",
    )

    def show_progress(index: int, total: int, code: str) -> None:
        if index == 0:
            logger.info("universe_resolved stocks={}", total)
        elif index == total or index % 100 == 0:
            logger.info(
                "market_cap_data_load_progress loaded={} total={} code={}",
                index,
                total,
                code,
            )

    provider = Zer0ShareDataProvider(LocalPro(cfg.zer0share_data_dir))
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    row_counts = compute_and_store_market_cap_factors(
        factors=MARKET_CAP_FACTORS,
        provider=provider,
        storage=storage,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        log_info=logger.info,
    )
    for factor_name, row_count in row_counts.items():
        logger.info("market_cap_factor_rows factor={} rows={}", factor_name, row_count)
    logger.info("market_cap_factor_job_finished factors={}", len(row_counts))


@cli.command("preprocess-factor")
@click.argument("factor_name")
@click.option("--output-name", default=None)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.pass_context
def preprocess_factor(ctx, factor_name, output_name, start_date, end_date):
    """Preprocess a stored factor with winsorization, imputation, and z-score."""
    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    resolved_output = output_name or f"z_{factor_name}"
    logger.info(
        "preprocess_factor_job_started factor={} output={} start_date={} end_date={}",
        factor_name,
        resolved_output,
        resolved_start,
        resolved_end or "latest",
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    rows = preprocess_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=storage,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    logger.info(
        "preprocess_factor_job_finished factor={} output={} rows={}",
        factor_name,
        resolved_output,
        rows,
    )


@cli.command("neutralize-factor")
@click.argument("factor_name")
@click.option("--output-name", default=None)
@click.option(
    "--size-factor-name",
    default=NEUTRALIZATION_SIZE_FACTOR,
    show_default=True,
)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.pass_context
def neutralize_factor(ctx, factor_name, output_name, size_factor_name, start_date, end_date):
    """Neutralize a stored z-scored factor against size and SW L1 industry."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    resolved_output = output_name or f"neu_{factor_name}"
    logger.info(
        "neutralize_factor_job_started "
        "factor={} output={} size_factor={} start_date={} end_date={}",
        factor_name,
        resolved_output,
        size_factor_name,
        resolved_start,
        resolved_end or "latest",
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    rows = neutralize_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=storage,
        pro=LocalPro(cfg.zer0share_data_dir),
        start_date=resolved_start,
        end_date=resolved_end,
        size_factor_name=size_factor_name,
    )
    logger.info(
        "neutralize_factor_job_finished factor={} output={} rows={}",
        factor_name,
        resolved_output,
        rows,
    )


if __name__ == "__main__":
    cli()
