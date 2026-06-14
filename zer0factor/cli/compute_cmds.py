"""Factor computation commands: compute-returns, compute-market-cap, build-factors."""

from pathlib import Path

import click
from loguru import logger

from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.context import AppContext
from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS
from zer0factor.notify import load_notifier
from zer0factor.pipeline import run_build_stage, update_factor_registry
from zer0factor.services.compute import FactorComputeService, ZScorePostProcess


@cli.command("compute-returns")
@click.pass_context
def compute_returns(ctx):
    """Compute built-in return factors and store them locally."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    end_date = cfg.end_date or None
    app.configure_logging()
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

    service = FactorComputeService(app.provider, app.storage, log_info=logger.info)
    row_counts = service.compute_and_store(
        RETURN_FACTORS,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
    )
    for factor_name, row_count in row_counts.items():
        logger.info("return_factor_rows factor={} rows={}", factor_name, row_count)
    logger.info("return_factor_job_finished factors={}", len(row_counts))


@cli.command("compute-market-cap")
@click.pass_context
def compute_market_cap(ctx):
    """Compute built-in market cap factors and store raw plus z-scored values."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
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

    service = FactorComputeService(app.provider, app.storage, log_info=logger.info)
    row_counts = service.compute_and_store(
        MARKET_CAP_FACTORS,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        postprocess=ZScorePostProcess(app.storage),
    )
    for factor_name, row_count in row_counts.items():
        logger.info("market_cap_factor_rows factor={} rows={}", factor_name, row_count)
    logger.info("market_cap_factor_job_finished factors={}", len(row_counts))


@cli.command("build-factors")
@click.option("--family", "family_name", required=True, help="Factor family to build")
@click.option(
    "--stage",
    type=click.Choice(["raw", "preprocess", "all"]),
    default="all",
    show_default=True,
)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--registry", "registry_path", default="config/factors.toml", show_default=True)
@click.option("--update-registry", is_flag=True, default=False)
@click.option(
    "--workers",
    type=int,
    default=1,
    show_default=True,
    help="Parallel worker processes (1 = serial)",
)
@click.pass_context
def build_factors_command(
    ctx,
    family_name,
    stage,
    start_date,
    end_date,
    registry_path,
    update_registry,
    workers,
):
    """Build a registered factor family."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    notifier = load_notifier(cfg)
    pro = app.pro if stage in {"preprocess", "all"} else None

    rows = run_build_stage(
        family_name=family_name,
        stage=stage,
        storage=app.storage,
        pro=pro,
        start_date=resolved_start,
        end_date=resolved_end,
        process_universe=cfg.process_universe,
        workers=workers,
        notifier=notifier,
    )
    for factor_name, row_count in rows.items():
        click.echo(f"{factor_name}: {row_count}")

    if update_registry:
        added = update_factor_registry(Path(registry_path), family_name=family_name)
        click.echo(f"registry entries added: {len(added)}")
