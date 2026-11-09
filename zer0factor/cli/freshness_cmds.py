"""check-freshness: cut-off date consistency before any incremental update."""

import click
from loguru import logger

from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.factor_registry import family_registry
from zer0factor.freshness import (
    BASE_FACTORS,
    BASE_GROUP,
    check_freshness,
    format_report,
    latest_standard_evaluation,
)
from zer0factor.notify import load_notifier


def _factor_groups(cfg) -> tuple[dict[str, list[str]], list[str]]:
    groups: dict[str, list[str]] = {BASE_GROUP: list(BASE_FACTORS)}
    errors: list[str] = []
    registry = family_registry(cfg)
    for name in registry.known_names():
        try:
            groups[name] = list(registry.get(name).all_factor_names())
        except Exception as exc:  # a broken family must not hide the others
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return groups, errors


@cli.command("check-freshness")
@click.option("--json", "as_json", is_flag=True, default=False, help="以 JSON 输出")
@click.option("--notify", is_flag=True, default=False, help="有问题时发飞书提醒")
@click.pass_context
def check_freshness_command(ctx, as_json, notify):
    """检查行情、股票池、因子、评估四方的截止日是否一致；不一致时退出码为 1。"""
    cfg = load_config(ctx.obj["config_path"])
    groups, family_errors = _factor_groups(cfg)
    report = check_freshness(
        zer0share_data_dir=cfg.zer0share_data_dir,
        factor_dir=cfg.factor_dir,
        universes=[cfg.process_universe, cfg.web.standard.universe],
        factor_groups=groups,
        evaluation=latest_standard_evaluation(cfg.web.evaluations_dir, cfg.web.standard),
    )
    click.echo(report.to_json() if as_json else format_report(report))
    for err in family_errors:
        logger.warning("freshness_family_skipped {}", err)
        if not as_json:
            click.echo(f"（因子族加载失败，已跳过：{err}）", err=True)
    if not report.ok:
        if notify:
            load_notifier(cfg).notify_warning("check-freshness", list(report.issues))
        ctx.exit(1)
