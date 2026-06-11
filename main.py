from pathlib import Path

import click
import pandas as pd
from loguru import logger

from zer0factor.config import load_config
from zer0factor.context import AppContext
from zer0factor.eval import (
    EvaluationConfig,
    ReportThresholds,
    evaluate_factors,
    find_latest_run_dir,
    generate_evaluation_report,
    load_batch_evaluation_config,
)
from zer0factor.exposures import build_sw_l1_industry_panel
from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS
from zer0factor.panel import (
    filter_long_by_universe,
    filter_panel_by_universe,
    long_to_wide,
    parse_trade_dates,  # noqa: F401  (re-exported for CLI/test consumers)
    read_universe_panel,
    wide_to_long,
)
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.registry import FactorRegistry
from zer0factor.services.compute import FactorComputeService, ZScorePostProcess
from zer0factor.storage import FactorStorage

STANDARD_PREPROCESS_CONFIG = PreprocessConfig()
NEUTRALIZATION_SIZE_FACTOR = "z_log_circulating_market_cap"


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
    app = AppContext(load_config(ctx.obj["config_path"]))
    storage = app.storage
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

    app = AppContext(load_config(ctx.obj["config_path"]))
    storage = app.storage
    try:
        registry = FactorRegistry(Path(registry_path))
    except FileNotFoundError:
        click.echo(f"Error: registry file not found: {registry_path}", err=True)
        raise SystemExit(1)
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

    if not registered and category is None:
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
    app = AppContext(load_config(ctx.obj["config_path"]))
    storage = app.storage
    try:
        registry = FactorRegistry(Path(registry_path))
    except FileNotFoundError:
        click.echo(f"Error: registry file not found: {registry_path}", err=True)
        raise SystemExit(1)

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


def _parse_periods(value: str) -> tuple[int, ...]:
    try:
        periods = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise click.BadParameter("must be comma-separated positive integers") from exc

    if not periods or any(period <= 0 for period in periods):
        raise click.BadParameter("must be comma-separated positive integers")
    return periods


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
    source_panel = long_to_wide(source)
    size_panel = long_to_wide(size)
    dates = source_panel.index.intersection(size_panel.index)
    ts_codes = source_panel.columns.intersection(size_panel.columns)
    source_panel = source_panel.reindex(index=dates, columns=ts_codes)
    size_panel = size_panel.reindex(index=dates, columns=ts_codes)
    source_panel = filter_panel_by_universe(source_panel, universe)
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
    output = wide_to_long(standardized)
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
    source = filter_long_by_universe(source, universe)
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
    resolved_output = output_name or f"z_{factor_name}"
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
    rows = standardize_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=app.storage,
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
    universe = read_universe_panel(
        app.pro,
        universe_name=cfg.process_universe,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    rows = neutralize_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=app.storage,
        pro=app.pro,
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
    transaction_cost_bps: float,
    benchmark_index: str | None = None,
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
        transaction_cost_bps=transaction_cost_bps,
        benchmark_index=benchmark_index,
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
    transaction_cost_bps: float,
    benchmark_index: str | None = None,
):
    cfg = load_config(ctx.obj["config_path"])
    app = AppContext(cfg)
    app.configure_logging()
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
        benchmark_index=benchmark_index,
        transaction_cost_bps=transaction_cost_bps,
    )
    def log_progress(message: str) -> None:
        logger.info(message)

    result = evaluate_factors(
        factor_names=factor_names,
        storage=app.storage,
        pro=app.pro,
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
@click.option(
    "--transaction-cost-bps",
    default=10.0,
    show_default=True,
    type=float,
    help="单边交易成本，单位 bps；按估算换手从收益中扣除",
)
@click.option("--benchmark-index", default=None, help="指数代码，如 000300.SH，用于计算多头指数超额收益")
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
    transaction_cost_bps,
    benchmark_index,
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
        transaction_cost_bps=transaction_cost_bps,
        benchmark_index=benchmark_index,
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
@click.option(
    "--transaction-cost-bps",
    default=10.0,
    show_default=True,
    type=float,
    help="单边交易成本，单位 bps；按估算换手从收益中扣除",
)
@click.option("--benchmark-index", default=None, help="指数代码，如 000300.SH，用于计算多头指数超额收益")
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
    transaction_cost_bps,
    benchmark_index,
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
        transaction_cost_bps=transaction_cost_bps,
        benchmark_index=benchmark_index,
    )


@cli.command("evaluate-batch")
@click.option(
    "--file",
    "batch_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--benchmark-index", default=None, help="指数代码，如 000300.SH，用于计算多头指数超额收益")
@click.pass_context
def evaluate_batch_command(ctx, batch_file, benchmark_index):
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
        transaction_cost_bps=batch.transaction_cost_bps,
        benchmark_index=benchmark_index,
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


@cli.command("show-summary")
@click.option("--run-dir", default=None, help="Evaluation run directory (defaults to latest)")
@click.option("--evaluations-dir", default="data/evaluations", show_default=True)
@click.option("--period", default=None, help="Filter to a specific period, e.g. 1D")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Show all raw diagnostic columns",
)
def show_summary_command(run_dir, evaluations_dir, period, show_all):
    """Show all metrics for an evaluation run, transposed (metrics as rows)."""
    resolved_run_dir = Path(run_dir) if run_dir else find_latest_run_dir(Path(evaluations_dir))
    summary_path = resolved_run_dir / "summary.csv"
    if not summary_path.exists():
        raise click.ClickException(f"summary.csv not found in {resolved_run_dir}")

    df = pd.read_csv(summary_path)
    if period:
        df = df[df["period"] == period]
        if df.empty:
            raise click.ClickException(f"No rows found for period={period}")
    if not show_all:
        df = df.drop(
            columns=[
                "IC>0 %",
                "IC>0 %(W)",
                "IC>0 %(M)",
            ],
            errors="ignore",
        )

    df = df.reset_index(drop=True)
    col_labels = (df["factor_name"] + "_" + df["period"]).tolist()
    transposed = df.T.copy()
    transposed.columns = col_labels

    pd.set_option("display.max_rows", 500)
    pd.set_option("display.max_colwidth", 40)
    pd.set_option("display.width", 0)

    click.echo(f"Run: {resolved_run_dir}")
    click.echo(transposed.to_string())


if __name__ == "__main__":
    cli()
