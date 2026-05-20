import sys
from collections.abc import Callable
from pathlib import Path

import click
from loguru import logger

from zer0factor.config import load_config
from zer0factor.core import Factor, Zer0ShareDataProvider, run_factor
from zer0factor.factors import DailyReturn, IntradayReturn, OpenReturn, OvernightReturn
from zer0factor.storage import FactorStorage

RETURN_FACTORS = (
    DailyReturn(),
    OpenReturn(),
    IntradayReturn(),
    OvernightReturn(),
)
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


if __name__ == "__main__":
    cli()
