"""update-daily: freshness check -> incremental builds -> incremental evaluation."""

from pathlib import Path

import click
from loguru import logger

from zer0factor.cli.compute_cmds import build_factors_command, compute_market_cap, compute_returns
from zer0factor.cli.evaluate_cmds import _run_evaluation_job
from zer0factor.cli.freshness_cmds import collect_report
from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.daily import Step, run_steps
from zer0factor.freshness import format_report, latest_standard_evaluation
from zer0factor.notify import load_notifier

DEFAULT_FAMILIES = ("rolling_return",)


def _period_days(period: str) -> int:
    return int(str(period).rstrip("Dd"))


def _plan(
    ctx, cfg, *, target_end, families, workers, rebuild_tail, skip_eval, full_eval=False
) -> list[Step]:
    steps = [
        Step(
            "compute-returns",
            lambda: ctx.invoke(
                compute_returns, start_date=None, end_date=target_end,
                incremental=True, rebuild_tail=rebuild_tail,
            ),
        ),
        Step(
            "compute-market-cap",
            lambda: ctx.invoke(
                compute_market_cap, start_date=None, end_date=target_end,
                incremental=True, rebuild_tail=rebuild_tail,
            ),
        ),
    ]
    for family in families:
        steps.append(
            Step(
                f"build-factors {family}",
                lambda family=family: ctx.invoke(
                    build_factors_command, family_name=family, stage="all",
                    start_date=None, end_date=target_end, incremental=True,
                    rebuild_tail=rebuild_tail, registry_path="config/factors.toml",
                    update_registry=False, workers=workers,
                ),
            )
        )
    if skip_eval:
        return steps
    std = cfg.web.standard
    base = latest_standard_evaluation(cfg.web.evaluations_dir, std)
    if base is None:
        logger.warning("daily_eval_skipped reason=no standard run; run a full evaluation first")
        return steps
    run_id, _, factor_names, _ = base
    label = "全量" if full_eval else f"--incremental，基准 {run_id}"
    steps.append(
        Step(
            f"evaluate-factors（{len(factor_names)} 个因子，{label}）",
            lambda: _run_evaluation_job(
                ctx,
                factor_names=tuple(factor_names),
                start_date=std.start_date,
                end_date=None,
                periods=(_period_days(std.period),),
                quantiles=std.quantiles,
                return_type=std.return_type,
                universe=std.universe,
                max_loss=0.35,
                output_dir=Path(cfg.web.evaluations_dir),
                transaction_cost_bps=10.0,
                workers=workers,
                incremental=not full_eval,
            ),
        )
    )
    return steps


@cli.command("update-daily")
@click.option(
    "--family", "families", multiple=True,
    help=f"要增量构建的因子族，可重复（默认 {', '.join(DEFAULT_FAMILIES)}）",
)
@click.option("--workers", default=8, show_default=True, type=int, help="构建和评估的并行进程数")
@click.option("--rebuild-tail", default=1, show_default=True, type=click.IntRange(min=0))
@click.option("--skip-eval", is_flag=True, default=False, help="只构建因子，不评估")
@click.option("--full-eval", is_flag=True, default=False, help="评估改为全量（每月对账用）")
@click.option("--notify", is_flag=True, default=False, help="把结果发到飞书")
@click.option("--dry-run", is_flag=True, default=False, help="只检查截止日并列出步骤，不执行")
@click.pass_context
def update_daily_command(
    ctx, families, workers, rebuild_tail, skip_eval, full_eval, notify, dry_run
):
    """日更：检查截止日 → 增量构建收益率、市值、因子族 → 增量评估。

    目标截止日取行情和股票池中较早的一个；股票池落后时照常更新到股票池的截止日并报警。
    任一步失败即停止，退出码为 1。
    """
    cfg = load_config(ctx.obj["config_path"])
    notifier = load_notifier(cfg) if notify else None
    report, _ = collect_report(cfg)
    click.echo(format_report(report))
    if report.target_end is None:
        click.echo("行情或股票池没有数据，无法确定目标截止日，停止。", err=True)
        if notifier:
            notifier.notify_warning("update-daily", list(report.issues))
        ctx.exit(1)
    upstream_issues = [i for i in report.issues if i.startswith(("股票池", "行情"))]

    steps = _plan(
        ctx, cfg, target_end=report.target_end, families=families or DEFAULT_FAMILIES,
        workers=workers, rebuild_tail=rebuild_tail, skip_eval=skip_eval, full_eval=full_eval,
    )
    click.echo(f"\n目标截止日 {report.target_end}，计划执行：")
    for i, step in enumerate(steps, 1):
        click.echo(f"  {i}. {step.name}")
    if dry_run:
        return

    outcomes = run_steps(steps, log=logger.info)
    final, _ = collect_report(cfg)
    lines = [o.describe() for o in outcomes]
    click.echo("\n结果：")
    for line in lines:
        click.echo(f"  - {line}")
    click.echo("\n" + format_report(final))

    failed = any(o.status == "failed" for o in outcomes)
    alerts = [*lines] if failed else []
    alerts += [*dict.fromkeys([*upstream_issues, *final.issues])]
    if notifier:
        if failed or alerts:
            notifier.notify_warning("update-daily", alerts or lines)
        else:
            notifier.notify_success("update-daily", lines)
    if failed:
        ctx.exit(1)
