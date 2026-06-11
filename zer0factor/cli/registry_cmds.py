"""Registry inspection commands: factor-list, factor-info."""

from pathlib import Path

import click
import pandas as pd

from zer0factor.cli.root import cli
from zer0factor.config import load_config
from zer0factor.context import AppContext
from zer0factor.registry import FactorRegistry


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
                f"\nregistered but missing in storage "
                f"({len(validation.registered_missing)}): {names}"
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
