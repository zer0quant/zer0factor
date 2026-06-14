"""Factor preprocessing commands: standardize-factor, neutralize-factor."""

import click
from loguru import logger

from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.context import AppContext
from zer0factor.naming import FactorName
from zer0factor.panel import read_universe_panel
from zer0factor.services.preprocess import (
    NEUTRALIZATION_SIZE_FACTOR,
    FactorPreprocessService,
)


@cli.command("standardize-factor")
@click.argument("factor_name")
@click.option("--output-name", default=None)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.pass_context
def standardize_factor(ctx, factor_name, output_name, start_date, end_date):
    """Standardize a stored factor with winsorization, imputation, and z-score."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    resolved_output = output_name or FactorName.parse(factor_name).standardized
    logger.info(
        "standardize_factor_job_started factor={} output={} start_date={} end_date={}",
        factor_name,
        resolved_output,
        resolved_start,
        resolved_end or "latest",
    )
    universe = read_universe_panel(
        app.pro,
        universe_name=cfg.process_universe,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    service = FactorPreprocessService(app.storage)
    rows = service.standardize(
        factor_name,
        output_name=resolved_output,
        start_date=resolved_start,
        end_date=resolved_end,
        universe=universe,
    )
    logger.info(
        "standardize_factor_job_finished factor={} output={} rows={}",
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
    """Neutralize a standardized factor and standardize the residual."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    resolved_output = output_name or FactorName.parse(factor_name).neutralized
    logger.info(
        "neutralize_factor_job_started "
        "factor={} source={} output={} size_factor={} start_date={} end_date={}",
        factor_name,
        FactorName.parse(factor_name).standardized,
        resolved_output,
        size_factor_name,
        resolved_start,
        resolved_end or "latest",
    )
    universe = read_universe_panel(
        app.pro,
        universe_name=cfg.process_universe,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    service = FactorPreprocessService(app.storage, industry_source=app.pro)
    rows = service.neutralize(
        factor_name,
        output_name=resolved_output,
        size_factor_name=size_factor_name,
        start_date=resolved_start,
        end_date=resolved_end,
        universe=universe,
    )
    logger.info(
        "neutralize_factor_job_finished factor={} output={} rows={}",
        factor_name,
        resolved_output,
        rows,
    )
