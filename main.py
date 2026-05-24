import sys
from collections.abc import Callable
from pathlib import Path

import click
import pandas as pd
from loguru import logger

from zer0factor.config import load_config
from zer0factor.core import Factor, Zer0ShareDataProvider, run_factor
from zer0factor.eval import (
    EvaluationConfig,
    ReportThresholds,
    evaluate_factors,
    find_latest_run_dir,
    generate_evaluation_report,
    load_batch_evaluation_config,
)
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
from zer0factor.registry import FactorRegistry
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


@cli.command("factor-list")
@click.option("--registry", "registry_path", default="config/factors.toml", show_default=True)
@click.option("--category", default=None, help="Filter by category")
@click.option("--enabled", is_flag=True, default=False, help="Show only enabled factors")
@click.option("--registered", is_flag=True, default=False, help="Show only registry factors")
@click.option("--orphan", is_flag=True, default=False, help="Show only unregistered stored factors")
@click.pass_context
def factor_list_command(ctx, registry_path, category, enabled, registered, orphan):
    """List factors from registry and storage with status comparison."""
    if registered and orphan:
        raise click.UsageError("--registered and --orphan are mutually exclusive")

    cfg = load_config(ctx.obj["config_path"])
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    registry = FactorRegistry(Path(registry_path))
    validation = registry.validate(storage)

    rows = []

    if not orphan:
        factors = registry.filter(
            enabled=True if enabled else None,
            category=category,
        )
        for meta in factors:
            stats = storage.factor_stats(meta.name)
            rows.append({
                "NAME": meta.name,
                "CATEGORY": meta.category,
                "TYPE": meta.source_type,
                "ENABLED": "Y" if meta.enabled else "N",
                "IN_STORAGE": "Y" if stats else "N",
                "ROWS": f"{stats.rows:,}" if stats else "-",
                "START": stats.start_date if stats else "-",
                "END": stats.end_date if stats else "-",
                "SOURCE": "registry",
            })

    if not registered:
        for name in validation.orphan_stored:
            stats = storage.factor_stats(name)
            rows.append({
                "NAME": name,
                "CATEGORY": "-",
                "TYPE": "-",
                "ENABLED": "-",
                "IN_STORAGE": "Y",
                "ROWS": f"{stats.rows:,}" if stats else "-",
                "START": stats.start_date if stats else "-",
                "END": stats.end_date if stats else "-",
                "SOURCE": "storage",
            })

    if rows:
        click.echo(pd.DataFrame(rows).to_string(index=False))
    else:
        click.echo("No factors found.")

    if not orphan:
        if validation.registered_missing:
            names = ", ".join(validation.registered_missing)
            click.echo(
                f"\nregistered but missing in storage ({len(validation.registered_missing)}): {names}"
            )
        if not registered and validation.orphan_stored:
            names = ", ".join(validation.orphan_stored)
            click.echo(
                f"stored but unregistered ({len(validation.orphan_stored)}): {names}"
            )


@cli.command("factor-info")
@click.argument("name")
@click.option("--registry", "registry_path", default="config/factors.toml", show_default=True)
@click.pass_context
def factor_info_command(ctx, name, registry_path):
    """Show registry metadata and storage status for a single factor."""
    cfg = load_config(ctx.obj["config_path"])
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    registry = FactorRegistry(Path(registry_path))

    try:
        meta = registry.get(name)
    except KeyError:
        click.echo(f"Error: '{name}' is not registered in {registry_path}", err=True)
        raise SystemExit(1)

    tags = ", ".join(meta.tags) if meta.tags else "-"
    click.echo("── Registry ──────────────────────────────────")
    click.echo(f"name:          {meta.name}")
    click.echo(f"category:      {meta.category}")
    click.echo(f"source_type:   {meta.source_type}")
    click.echo(f"source_factor: {meta.source_factor or '-'}")
    click.echo(f"enabled:       {'true' if meta.enabled else 'false'}")
    click.echo(f"tags:          {tags}")
    click.echo(f"description:   {meta.description or '-'}")
    if meta.evaluate:
        ev = meta.evaluate
        click.echo(
            f"evaluate:      quantiles={ev.quantiles}"
            f"  periods={list(ev.periods)}"
            f"  return_type={ev.return_type}"
        )
    else:
        click.echo("evaluate:      (uses global defaults)")

    stats = storage.factor_stats(name)
    click.echo("\n── Storage ───────────────────────────────────")
    if stats:
        click.echo("status:        found")
        click.echo(f"rows:          {stats.rows:,}")
        click.echo(f"start_date:    {stats.start_date}")
        click.echo(f"end_date:      {stats.end_date}")
    else:
        click.echo("status:        not found in storage")


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


def _parse_periods(value: str) -> tuple[int, ...]:
    try:
        periods = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise click.BadParameter("must be comma-separated positive integers") from exc

    if not periods or any(period <= 0 for period in periods):
        raise click.BadParameter("must be comma-separated positive integers")
    return periods


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
    universe: pd.DataFrame | None = None,
) -> int:
    source_name = _standardized_factor_name(factor_name)
    source = storage.read(source_name, start_date=start_date, end_date=end_date)
    size = storage.read(size_factor_name, start_date=start_date, end_date=end_date)
    source_panel = _factor_long_to_wide(source)
    size_panel = _factor_long_to_wide(size)
    dates = source_panel.index.intersection(size_panel.index)
    ts_codes = source_panel.columns.intersection(size_panel.columns)
    source_panel = source_panel.reindex(index=dates, columns=ts_codes)
    size_panel = size_panel.reindex(index=dates, columns=ts_codes)
    source_panel = _filter_panel_by_universe(source_panel, universe)
    size_panel = size_panel.reindex(index=source_panel.index, columns=source_panel.columns)
    industry_panel = build_sw_l1_industry_panel(pro, dates=dates, ts_codes=ts_codes)
    industry_panel = industry_panel.reindex(index=source_panel.index, columns=source_panel.columns)

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
    standardized = standardize_stored_panel(result)
    output = _factor_wide_to_long(standardized)
    storage.write(output_name, output)
    return len(output)


def standardize_stored_factor(
    *,
    factor_name: str,
    output_name: str,
    storage: FactorStorage,
    start_date: str | None = None,
    end_date: str | None = None,
    config: PreprocessConfig = STANDARD_PREPROCESS_CONFIG,
    universe: pd.DataFrame | None = None,
) -> int:
    source = storage.read(factor_name, start_date=start_date, end_date=end_date)
    source = _filter_long_by_universe(source, universe)
    pipeline = FactorPreprocessPipeline(config)
    output = pipeline.transform(source)
    storage.write(output_name, output)
    return len(output)


def preprocess_stored_factor(**kwargs) -> int:
    return standardize_stored_factor(**kwargs)


def standardize_stored_panel(panel: pd.DataFrame) -> pd.DataFrame:
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="zscore",
            neutralize_method=None,
        )
    )
    return pipeline.transform(panel)


def _standardized_factor_name(factor_name: str) -> str:
    if factor_name.startswith("z_"):
        return factor_name
    return f"z_{factor_name}"


def read_universe_panel(
    pro,
    *,
    universe_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    rows = pro.universe(
        universe=universe_name,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,universe,ts_code",
    )
    if rows.empty:
        return pd.DataFrame(dtype=bool)

    frame = rows.loc[:, ["trade_date", "ts_code"]].copy()
    frame["trade_date"] = _parse_trade_dates(frame["trade_date"])
    frame["in_universe"] = True
    return (
        frame.drop_duplicates(["trade_date", "ts_code"])
        .pivot(index="trade_date", columns="ts_code", values="in_universe")
        .pipe(lambda df: df.where(df.notna(), False))
        .astype(bool)
        .sort_index()
        .sort_index(axis=1)
    )


def _filter_long_by_universe(
    factor: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return factor
    panel = _factor_long_to_wide(factor)
    return _factor_wide_to_long(_filter_panel_by_universe(panel, universe))


def _filter_panel_by_universe(
    panel: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return panel
    aligned = universe.reindex(index=panel.index, columns=panel.columns, fill_value=False)
    aligned = aligned.astype(bool)
    return panel.where(aligned).dropna(axis=1, how="all")


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


@cli.command("standardize-factor")
@click.argument("factor_name")
@click.option("--output-name", default=None)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.pass_context
def standardize_factor(ctx, factor_name, output_name, start_date, end_date):
    """Standardize a stored factor with winsorization, imputation, and z-score."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    resolved_output = output_name or f"z_{factor_name}"
    logger.info(
        "standardize_factor_job_started factor={} output={} start_date={} end_date={}",
        factor_name,
        resolved_output,
        resolved_start,
        resolved_end or "latest",
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    pro = LocalPro(cfg.zer0share_data_dir)
    universe = read_universe_panel(
        pro,
        universe_name=cfg.process_universe,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    rows = standardize_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=storage,
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
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    raw_factor_name = factor_name[2:] if factor_name.startswith("z_") else factor_name
    resolved_output = output_name or f"z_neu_{raw_factor_name}"
    logger.info(
        "neutralize_factor_job_started "
        "factor={} source={} output={} size_factor={} start_date={} end_date={}",
        factor_name,
        _standardized_factor_name(factor_name),
        resolved_output,
        size_factor_name,
        resolved_start,
        resolved_end or "latest",
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    pro = LocalPro(cfg.zer0share_data_dir)
    universe = read_universe_panel(
        pro,
        universe_name=cfg.process_universe,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    rows = neutralize_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=storage,
        pro=pro,
        start_date=resolved_start,
        end_date=resolved_end,
        size_factor_name=size_factor_name,
        universe=universe,
    )
    logger.info(
        "neutralize_factor_job_finished factor={} output={} rows={}",
        factor_name,
        resolved_output,
        rows,
    )


def _run_evaluation_command(
    ctx,
    *,
    factor_names: tuple[str, ...],
    start_date: str | None,
    end_date: str | None,
    periods: str,
    quantiles: int,
    return_type: str,
    universe: str | None,
    max_loss: float,
    output_dir: str,
) -> None:
    result = _run_evaluation_job(
        ctx,
        factor_names=factor_names,
        start_date=start_date,
        end_date=end_date,
        periods=_parse_periods(periods),
        quantiles=quantiles,
        return_type=return_type,
        universe=universe,
        max_loss=max_loss,
        output_dir=Path(output_dir),
    )
    click.echo(f"Evaluation run {result.run_id} written to {result.output_dir}")


def _run_evaluation_job(
    ctx,
    *,
    factor_names: tuple[str, ...],
    start_date: str | None,
    end_date: str | None,
    periods: tuple[int, ...],
    quantiles: int,
    return_type: str,
    universe: str | None,
    max_loss: float,
    output_dir: Path,
):
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    config = EvaluationConfig(
        factor_names=factor_names,
        start_date=resolved_start,
        end_date=resolved_end,
        periods=periods,
        quantiles=quantiles,
        return_type=return_type,
        max_loss=max_loss,
        universe=universe,
        output_dir=output_dir,
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)

    def log_progress(message: str) -> None:
        logger.info(message)

    result = evaluate_factors(
        factor_names=factor_names,
        storage=storage,
        pro=LocalPro(cfg.zer0share_data_dir),
        config=config,
        log_info=log_progress,
    )
    logger.info(
        "factor_evaluation_job_finished run_id={} output_dir={} factors={}",
        result.run_id,
        result.output_dir,
        len(result.factor_results),
    )
    return result


@cli.command("evaluate-factor")
@click.argument("factor_name")
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--periods", default="1,5,10", show_default=True)
@click.option("--quantiles", default=10, show_default=True)
@click.option(
    "--return-type",
    type=click.Choice(["open_t1", "close_t0"]),
    default="open_t1",
    show_default=True,
)
@click.option("--universe", default=None)
@click.option("--max-loss", default=0.35, show_default=True)
@click.option("--output-dir", default="data/evaluations", show_default=True)
@click.pass_context
def evaluate_factor_command(
    ctx,
    factor_name,
    start_date,
    end_date,
    periods,
    quantiles,
    return_type,
    universe,
    max_loss,
    output_dir,
):
    """Evaluate one stored factor."""
    _run_evaluation_command(
        ctx,
        factor_names=(factor_name,),
        start_date=start_date,
        end_date=end_date,
        periods=periods,
        quantiles=quantiles,
        return_type=return_type,
        universe=universe,
        max_loss=max_loss,
        output_dir=output_dir,
    )


@cli.command("evaluate-factors")
@click.argument("factor_names", nargs=-1, required=True)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--periods", default="1,5,10", show_default=True)
@click.option("--quantiles", default=10, show_default=True)
@click.option(
    "--return-type",
    type=click.Choice(["open_t1", "close_t0"]),
    default="open_t1",
    show_default=True,
)
@click.option("--universe", default=None)
@click.option("--max-loss", default=0.35, show_default=True)
@click.option("--output-dir", default="data/evaluations", show_default=True)
@click.pass_context
def evaluate_factors_command(
    ctx,
    factor_names,
    start_date,
    end_date,
    periods,
    quantiles,
    return_type,
    universe,
    max_loss,
    output_dir,
):
    """Evaluate one or more stored factors."""
    _run_evaluation_command(
        ctx,
        factor_names=factor_names,
        start_date=start_date,
        end_date=end_date,
        periods=periods,
        quantiles=quantiles,
        return_type=return_type,
        universe=universe,
        max_loss=max_loss,
        output_dir=output_dir,
    )


@cli.command("evaluate-batch")
@click.option(
    "--file",
    "batch_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.pass_context
def evaluate_batch_command(ctx, batch_file):
    """Evaluate factors from a TOML batch file."""
    batch = load_batch_evaluation_config(batch_file)
    result = _run_evaluation_job(
        ctx,
        factor_names=batch.factor_names,
        start_date=batch.start_date,
        end_date=batch.end_date,
        periods=batch.periods,
        quantiles=batch.quantiles,
        return_type=batch.return_type,
        universe=batch.universe,
        max_loss=batch.max_loss,
        output_dir=batch.output_dir,
    )
    click.echo(f"Evaluation run {result.run_id} written to {result.output_dir}")

    report = generate_evaluation_report(
        run_dir=result.output_dir,
        thresholds=batch.report_thresholds,
    )
    click.echo(f"Report written to {report.report_path}")
    click.echo(f"Ranked summary written to {report.ranked_summary_path}")
    preview_columns = [
        "factor_name",
        "period",
        "adjusted_score",
        "score",
        "passed",
        "direction",
        "adjusted_spread_bps",
        "monotonicity",
    ]
    preview_columns = [
        column for column in preview_columns if column in report.ranked_summary.columns
    ]
    click.echo(report.ranked_summary.loc[:, preview_columns].head(10).to_string(index=False))


@cli.command("evaluate-summary")
@click.option("--run-dir", default=None)
@click.option("--evaluations-dir", default="data/evaluations", show_default=True)
@click.option("--min-ic", default=0.02, show_default=True, type=float)
@click.option("--min-icir", default=0.3, show_default=True, type=float)
@click.option("--min-win-rate", default=52.0, show_default=True, type=float)
@click.option("--min-spread-bps", default=0.0, show_default=True, type=float)
@click.option("--min-sample-count", default=1000, show_default=True, type=int)
@click.option("--min-monotonicity", default=0.3, show_default=True, type=float)
def evaluate_summary_command(
    run_dir,
    evaluations_dir,
    min_ic,
    min_icir,
    min_win_rate,
    min_spread_bps,
    min_sample_count,
    min_monotonicity,
):
    """Summarize an evaluation run."""
    resolved_run_dir = Path(run_dir) if run_dir else find_latest_run_dir(Path(evaluations_dir))
    result = generate_evaluation_report(
        run_dir=resolved_run_dir,
        thresholds=ReportThresholds(
            min_ic=min_ic,
            min_icir=min_icir,
            min_win_rate=min_win_rate,
            min_spread_bps=min_spread_bps,
            min_sample_count=min_sample_count,
            min_monotonicity=min_monotonicity,
        ),
    )
    click.echo(f"Report written to {result.report_path}")
    click.echo(f"Ranked summary written to {result.ranked_summary_path}")
    preview_columns = [
        "factor_name",
        "period",
        "adjusted_score",
        "score",
        "passed",
        "direction",
        "adjusted_spread_bps",
        "monotonicity",
    ]
    preview_columns = [
        column for column in preview_columns if column in result.ranked_summary.columns
    ]
    click.echo(result.ranked_summary.loc[:, preview_columns].head(10).to_string(index=False))


if __name__ == "__main__":
    cli()
