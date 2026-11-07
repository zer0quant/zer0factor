"""Web workbench commands: serve and web-warm."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click

from zer0factor.cli.root import cli
from zer0factor.config import load_config

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8600, show_default=True, type=int)
@click.pass_context
def serve(ctx, host, port):
    """Serve the factor workbench (API + web UI + background task scheduler)."""
    import uvicorn

    from zer0factor.web.app import create_app

    cfg = load_config(ctx.obj["config_path"])
    if not (STATIC_DIR / "index.html").exists():
        click.echo("前端未构建：cd web && npm install && npm run build（API 照常启动）")
    click.echo(f"zer0factor workbench: http://{host}:{port}")
    config_path = Path(ctx.obj["config_path"]).resolve()
    uvicorn.run(
        create_app(cfg, static_dir=STATIC_DIR, config_path=config_path), host=host, port=port
    )


def _warm_one(config_path: str, run_id: str, factor: str) -> str:
    from zer0factor.web.charts import get_decay, get_series, latest_values
    from zer0factor.web.runs import SummaryCache, scan_runs

    cfg = load_config(Path(config_path))
    run = next(r for r in scan_runs(cfg.web.evaluations_dir) if r.run_id == run_id)
    summary = SummaryCache().get(run)
    if summary is None:
        raise RuntimeError("run has no summary.parquet")
    if get_series(run, factor, cfg.web.cache_dir, summary) is None:
        raise RuntimeError("clean_factor_data.parquet missing")
    get_decay(run, factor, cfg.web.cache_dir, summary)
    latest_values(run, factor, {}, 1, 1, cfg.web.cache_dir)
    return factor


@cli.command("web-warm")
@click.option("--run", "run_id", required=True, help="Evaluation run id to precompute")
@click.option("--workers", default=8, show_default=True, type=int)
@click.pass_context
def web_warm(ctx, run_id, workers):
    """Precompute web chart caches for every factor of one evaluation run."""
    from zer0factor.web.runs import scan_runs

    config_path = str(ctx.obj["config_path"])
    cfg = load_config(Path(config_path))
    run = next((r for r in scan_runs(cfg.web.evaluations_dir) if r.run_id == run_id), None)
    if run is None:
        raise click.ClickException(f"evaluation run not found: {run_id}")
    ok, failed = 0, 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_warm_one, config_path, run_id, f): f for f in run.factor_names}
        for future in as_completed(futures):
            factor = futures[future]
            try:
                future.result()
                ok += 1
                click.echo(f"ok   {factor}")
            except Exception as exc:
                failed += 1
                click.echo(f"fail {factor}: {exc}")
    click.echo(f"done: {ok} ok, {failed} failed")
