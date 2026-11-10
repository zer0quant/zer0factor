"""Factor computation commands: compute-returns, compute-market-cap, build-factors."""

import time
from pathlib import Path

import click
from loguru import logger

from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.context import AppContext
from zer0factor.factor_registry import FAMILIES, family_registry
from zer0factor.factors.builtin import (
    MARKET_CAP_FACTORS,
    MARKET_CAP_FACTORS_LOOKBACK,
    RETURN_FACTORS,
    RETURN_FACTORS_LOOKBACK,
)
from zer0factor.naming import FactorName
from zer0factor.notify import load_notifier
from zer0factor.pipeline import (
    preprocess_all_factors,
    run_build_family,
    run_build_stage,
    update_factor_registry,
)
from zer0factor.services.compute import (
    FactorComputeService,
    ZScorePostProcess,
    incremental_write_start,
    resolve_load_start,
    trading_days_before,
)


def _date_range_options(func):
    func = click.option("--end-date", default=None)(func)
    func = click.option("--start-date", default=None)(func)
    return func


def _incremental_options(func):
    func = click.option(
        "--rebuild-tail",
        type=click.IntRange(min=0),
        default=1,
        show_default=True,
        help="增量时额外重算已有的最后 N 个日期",
    )(func)
    func = click.option(
        "--incremental",
        is_flag=True,
        default=False,
        help="从已有因子的最后日期续算，只写新日期（输出从未构建过时退回全量）",
    )(func)
    return func


def _resolve_write_start(
    *,
    storage,
    names,
    start_date: str | None,
    incremental: bool,
    rebuild_tail: int,
    default_start: str,
) -> str:
    if incremental and start_date:
        raise click.UsageError("--incremental cannot be used with --start-date")
    if not incremental:
        return start_date or default_start
    names = list(names)
    write_start = incremental_write_start(storage, names, rebuild_tail=rebuild_tail)
    if write_start is None:
        logger.info("incremental_fallback_full_build outputs={}", len(names))
        return default_start
    logger.info(
        "incremental_build write_start={} rebuild_tail={} outputs={}",
        write_start,
        rebuild_tail,
        len(names),
    )
    return max(write_start, default_start)


def _load_start(app, lookback, *, write_start: str, history_start: str) -> str:
    return resolve_load_start(
        lookback,
        write_start=write_start,
        history_start=history_start,
        trading_days_before=lambda date, n: trading_days_before(app.pro, date, n),
    )


@cli.command("compute-returns")
@_date_range_options
@_incremental_options
@click.pass_context
def compute_returns(ctx, start_date, end_date, incremental, rebuild_tail):
    """Compute built-in return factors and store them locally."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    end_date = end_date if end_date is not None else (cfg.end_date or None)
    app.configure_logging()
    write_start = _resolve_write_start(
        storage=app.storage,
        names=[factor.spec.name for factor in RETURN_FACTORS],
        start_date=start_date,
        incremental=incremental,
        rebuild_tail=rebuild_tail,
        default_start=cfg.start_date,
    )
    load_start = _load_start(
        app, RETURN_FACTORS_LOOKBACK, write_start=write_start, history_start=cfg.start_date
    )
    logger.info(
        "return_factor_job_started universe={} start_date={} end_date={} fields={}",
        cfg.universe,
        write_start,
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
        start_date=write_start,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        load_start_date=load_start,
    )
    for factor_name, row_count in row_counts.items():
        logger.info("return_factor_rows factor={} rows={}", factor_name, row_count)
    logger.info("return_factor_job_finished factors={}", len(row_counts))


@cli.command("compute-market-cap")
@_date_range_options
@_incremental_options
@click.pass_context
def compute_market_cap(ctx, start_date, end_date, incremental, rebuild_tail):
    """Compute built-in market cap factors and store raw plus z-scored values."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
    end_date = end_date if end_date is not None else (cfg.end_date or None)
    raw_names = [factor.spec.name for factor in MARKET_CAP_FACTORS]
    write_start = _resolve_write_start(
        storage=app.storage,
        names=[*raw_names, *(FactorName.parse(n).standardized for n in raw_names)],
        start_date=start_date,
        incremental=incremental,
        rebuild_tail=rebuild_tail,
        default_start=cfg.start_date,
    )
    load_start = _load_start(
        app, MARKET_CAP_FACTORS_LOOKBACK, write_start=write_start, history_start=cfg.start_date
    )
    logger.info(
        "market_cap_factor_job_started universe={} start_date={} end_date={} fields={}",
        cfg.universe,
        write_start,
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
        start_date=write_start,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        postprocess=ZScorePostProcess(app.storage),
        load_start_date=load_start,
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
@_incremental_options
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
    incremental,
    rebuild_tail,
    registry_path,
    update_registry,
    workers,
):
    """Build a registered factor family."""
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
    family = family_registry(cfg).get(family_name)
    resolved_start = _resolve_write_start(
        storage=app.storage,
        names=_stage_output_names(family, stage),
        start_date=start_date,
        incremental=incremental,
        rebuild_tail=rebuild_tail,
        default_start=cfg.start_date,
    )
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    notifier = load_notifier(cfg)
    pro = app.pro if stage in {"preprocess", "all"} else None

    if family.uses_data_provider:
        rows = _run_data_provider_family(
            family=family,
            stage=stage,
            app=app,
            start_date=resolved_start,
            end_date=resolved_end,
            universe=cfg.universe,
            process_universe=cfg.process_universe,
            workers=workers,
            notifier=notifier,
            history_start=cfg.start_date,
            incremental=incremental,
        )
    elif family_name in FAMILIES:
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
    else:
        rows = run_build_family(
            family,
            stage,
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
        if family_name in FAMILIES:
            added = update_factor_registry(Path(registry_path), family_name=family_name)
        else:
            added = update_factor_registry(
                Path(registry_path),
                family_name=family_name,
                family=family,
            )
        click.echo(f"registry entries added: {len(added)}")


def _stage_output_names(family, stage) -> list[str]:
    names: list[str] = []
    if stage in {"raw", "all"}:
        names.extend(family.raw_names())
    if stage in {"preprocess", "all"}:
        names.extend(family.preprocess_output_names())
    return names


def _run_data_provider_family(
    *,
    family,
    stage,
    app,
    start_date,
    end_date,
    universe,
    process_universe,
    workers,
    notifier,
    history_start,
    incremental=False,
):
    if stage not in {"raw", "preprocess", "all"}:
        raise ValueError(f"unknown build stage: {stage}")
    rows: dict[str, int] = {}
    if stage in {"raw", "all"}:
        factors = family.factors()
        if incremental and any(
            getattr(getattr(f, "spec", None), "adjust", None) == "qfq" for f in factors
        ):
            raise click.UsageError(
                f"family {family.name} uses qfq prices, whose history changes with every "
                "ex-dividend; --incremental is not supported, rebuild it in full"
            )
        load_start = _load_start(
            app,
            getattr(family, "lookback", None),
            write_start=start_date,
            history_start=history_start,
        )
        logger.info(
            "data_provider_family_load_range family={} load_start={} write_start={}",
            family.name,
            load_start,
            start_date,
        )
        notifier.notify_start("raw", details={"family": family.name})
        t0 = time.monotonic()
        try:
            service = FactorComputeService(app.provider, app.storage, log_info=logger.info)
            rows.update(
                service.compute_and_store(
                    factors,
                    start_date=start_date,
                    end_date=end_date,
                    universe=universe,
                    load_start_date=load_start,
                )
            )
        except Exception as exc:
            notifier.notify_error("raw", exc)
            raise
        notifier.notify_done("raw", rows, time.monotonic() - t0)
    if stage in {"preprocess", "all"}:
        notifier.notify_start("preprocess", details={"family": family.name})
        t0 = time.monotonic()
        pre_rows: dict[str, int] = {}
        try:
            pre_rows.update(
                preprocess_all_factors(
                    list(family.raw_names()),
                    storage=app.storage,
                    pro=app.pro,
                    start_date=start_date,
                    end_date=end_date,
                    process_universe=process_universe,
                    profiles=family.profiles,
                    workers=workers,
                )
            )
        except Exception as exc:
            notifier.notify_error("preprocess", exc)
            raise
        notifier.notify_done("preprocess", pre_rows, time.monotonic() - t0)
        rows.update(pre_rows)
    return rows
