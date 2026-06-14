"""Factor evaluation commands: evaluate-*, show-summary."""

from pathlib import Path

import click
import pandas as pd
from loguru import logger

from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.context import AppContext
from zer0factor.eval import (
    EvaluationConfig,
    ReportThresholds,
    find_latest_run_dir,
    generate_evaluation_report,
    load_batch_evaluation_config,
)
from zer0factor.eval.analysis import ANALYSIS_CONFIGS, run_analysis
from zer0factor.notify import load_notifier
from zer0factor.services.evaluate import EvaluationService


def _parse_periods(value: str) -> tuple[int, ...]:
    try:
        periods = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise click.BadParameter("must be comma-separated positive integers") from exc

    if not periods or any(period <= 0 for period in periods):
        raise click.BadParameter("must be comma-separated positive integers")
    return periods


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
    notifier = load_notifier(cfg)
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

    service = EvaluationService(app.storage, app.pro, log_info=log_progress, notifier=notifier)
    result = service.run(config)
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
@click.option(
    "--benchmark-index",
    default=None,
    help="指数代码，如 000300.SH，用于计算多头指数超额收益",
)
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
@click.option(
    "--benchmark-index",
    default=None,
    help="指数代码，如 000300.SH，用于计算多头指数超额收益",
)
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
@click.option(
    "--benchmark-index",
    default=None,
    help="指数代码，如 000300.SH，用于计算多头指数超额收益",
)
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


@cli.command("analyze-evaluation")
@click.option(
    "--family",
    required=True,
    type=click.Choice(sorted(ANALYSIS_CONFIGS)),
    help="Factor family analysis parser to use",
)
@click.option("--run-dir", default=None, help="Evaluation run directory (defaults to latest)")
@click.option("--summary", default=None, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--output-dir", default=None, type=click.Path(file_okay=False, path_type=Path))
@click.option("--evaluations-dir", default="data/evaluations", show_default=True)
def analyze_evaluation_command(family, run_dir, summary, output_dir, evaluations_dir):
    """Analyze an evaluation summary and write grouped diagnostics."""
    resolved_run_dir = Path(run_dir) if run_dir else None
    summary_path = summary
    if summary_path is None:
        resolved_run_dir = resolved_run_dir or find_latest_run_dir(Path(evaluations_dir))
        summary_path = resolved_run_dir / "summary.csv"
    elif resolved_run_dir is None:
        resolved_run_dir = Path(summary_path).parent
    if not Path(summary_path).exists():
        raise click.ClickException(f"summary.csv not found: {summary_path}")

    resolved_output_dir = output_dir or resolved_run_dir / "analysis"
    result = run_analysis(
        summary_path=Path(summary_path),
        output_dir=Path(resolved_output_dir),
        config=ANALYSIS_CONFIGS[family],
    )
    click.echo(f"Analysis report written to {result.report_path}")
    click.echo(f"Factors analyzed: {result.analyzed_count}")
    click.echo(f"Skipped factors: {result.skipped_count}")


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
