"""FastAPI app serving the read-only factor workbench."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from loguru import logger

from zer0factor.config import Config
from zer0factor.web.bases import base_versions, summarize_bases
from zer0factor.web.catalog import Catalog, build_catalog
from zer0factor.web.charts import (
    cached_series,
    detail_cached,
    detail_payload,
    latest_values,
    load_stock_names,
    ls_sparkline,
    version_curve,
)
from zer0factor.web.correlation import _cached as _correlation_cache
from zer0factor.web.correlation import factor_correlation
from zer0factor.web.families import DiscoveryError, FamilyCatalog
from zer0factor.web.jsonsafe import to_jsonable
from zer0factor.jobs.scheduler import Scheduler
from zer0factor.jobs.store import TaskStore
from zer0factor.web.runs import RunInfo, summary_row
from zer0factor.web.tasks_api import TaskContext, active_run_ids, register_task_routes

MIN_COMPARE, MAX_COMPARE = 2, 8
_EMPTY_SUMMARY = pd.DataFrame(columns=["factor_name", "period"])


def _json(data: object) -> JSONResponse:
    return JSONResponse(to_jsonable(data))


def _run_summary(run: RunInfo, catalog: Catalog) -> dict:
    return {
        "run_id": run.run_id,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "universe": run.universe,
        "quantiles": run.quantiles,
        "periods": list(run.periods),
        "return_type": run.return_type,
        "transaction_cost_bps": run.transaction_cost_bps,
        "n_factors": len(run.factor_names),
        "has_summary": run.has_summary,
        "standard": catalog.is_standard(run),
    }


REFRESH_KINDS = {"evaluate", "warm"}


class FamilyPatch(BaseModel):
    status: Literal["enabled", "archived"] | None = None
    note: str | None = Field(None, max_length=2000)


def create_app(
    cfg: Config,
    static_dir: Path | None = None,
    *,
    config_path: Path | None = None,
    scheduler: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if scheduler:
            app.state.scheduler.start()
        try:
            yield
        finally:
            if scheduler:
                app.state.scheduler.stop()

    app = FastAPI(title="zer0factor workbench", lifespan=lifespan)
    store = TaskStore(Path(cfg.web.state_dir) / "workbench.db")
    state = {"catalog": build_catalog(cfg, exclude_runs=active_run_ids(store)), "names": None}
    # (run_id, factor, period, points) -> downsampled long-short curve. Cached series files are
    # written once and never change, so a curve found on disk can be memoised for good.
    sparklines: dict[tuple[str, str, str, int], list] = {}
    names_lock = threading.Lock()

    def refresh_catalog() -> None:
        state["catalog"] = build_catalog(cfg, exclude_runs=active_run_ids(store))
        _correlation_cache.cache_clear()
        sparklines.clear()

    def on_task_finished(task: dict) -> None:
        if task["kind"] in REFRESH_KINDS:
            refresh_catalog()

    sched = Scheduler(
        store,
        slots={"heavy": cfg.web.heavy_slots, "light": cfg.web.light_slots},
        on_finished=on_task_finished,
    )
    app.state.store = store
    app.state.scheduler = sched
    app.state.refresh_catalog = refresh_catalog

    def catalog() -> Catalog:
        return state["catalog"]

    def stock_names() -> dict[str, str]:
        with names_lock:
            if state["names"] is None:
                state["names"] = load_stock_names(cfg.zer0share_data_dir)
            return state["names"]

    def require_factor(name: str) -> None:
        if not catalog().has_factor(name):
            raise HTTPException(404, f"unknown factor: {name}")

    def require_run(name: str, run_id: str) -> RunInfo:
        require_factor(name)
        run = catalog().get_run(run_id)
        if run is None or name not in run.factor_names:
            raise HTTPException(404, f"run {run_id} has no factor {name}")
        return run

    def summary_of(run: RunInfo) -> pd.DataFrame:
        summary = catalog().summary_cache.get(run)
        return _EMPTY_SUMMARY if summary is None else summary

    def meta_payload() -> dict:
        c = catalog()
        return {
            "standard": asdict(c.standard),
            "scanned_at": c.scanned_at.isoformat(timespec="seconds"),
            "n_factors": len(c.factor_names),
            "runs": [_run_summary(r, c) for r in reversed(c.runs)],
        }

    def chosen_run(name: str) -> tuple[RunInfo | None, str | None, bool]:
        """(run, period, is_standard) used to represent a factor in comparisons."""
        c = catalog()
        hit = c.standard_rows().get(name)
        if hit:
            return hit[0], c.standard.period, True
        runs = [r for r in c.runs_for(name) if r.has_summary]
        if not runs:
            return None, None, False
        run = runs[0]
        period = c.standard.period if c.standard.period in run.periods else run.periods[0]
        return run, period, False

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception(f"web request failed: {request.url.path}")
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    @app.get("/api/meta")
    def meta():
        return _json(meta_payload())

    @app.post("/api/refresh")
    def refresh():
        refresh_catalog()
        return _json(meta_payload())

    register_task_routes(
        app,
        TaskContext(
            cfg=cfg,
            config_path=Path(config_path or "config/settings.toml"),
            store=store,
            scheduler=sched,
            known_factors=lambda: set(catalog().factor_names),
            known_runs=lambda: {r.run_id: len(r.factor_names) for r in catalog().runs},
            known_families=lambda: app.state.known_families(),
        ),
    )
    families = FamilyCatalog(cfg, Path(config_path or "config/settings.toml"), store)
    app.state.families = families
    app.state.known_families = families.valid_names

    @app.get("/api/families")
    def list_families(refresh: bool = False):
        try:
            rows = families.list(refresh=refresh)
        except DiscoveryError as exc:
            raise HTTPException(502, str(exc)) from exc
        scanned = families.scanned_at
        return _json({"families": rows, "scanned_at": scanned.isoformat(timespec="seconds")})

    @app.patch("/api/families/{name}")
    def patch_family(name: str, body: FamilyPatch):
        if name not in families.valid_names():
            raise HTTPException(404, f"unknown factor family: {name}")
        store.set_family(name, status=body.status, note=body.note)
        row = next(f for f in families.list() if f["name"] == name and not f["error"])
        return _json(row)

    @app.get("/api/factors")
    def factors():
        return _json({"rows": catalog().board_rows()})

    @app.get("/api/bases")
    def bases():
        return _json({"rows": summarize_bases(catalog().board_rows(), cfg.web.board)})

    @app.get("/api/bases/{base}")
    def base(base: str):
        body = base_versions(catalog().board_rows(), base, cfg.web.board)
        if body is None:
            raise HTTPException(404, f"unknown base factor: {base}")
        return _json(body)

    @app.get("/api/bases/{base}/curves")
    def base_curves(
        base: str, prep: str | None = None, win: str | None = None, kind: str = "long_excess"
    ):
        """Overlay curves: one prep across its windows, or one window across preps."""
        if (prep is None) == (win is None):
            raise HTTPException(400, "give exactly one of prep / win")
        if kind not in ("long_excess", "long", "ls"):
            raise HTTPException(400, f"unknown curve kind: {kind}")
        window: int | None = None
        if win is not None and win != "none":
            try:
                window = int(win)
            except ValueError:
                raise HTTPException(400, f"bad window: {win}") from None
        c = catalog()
        body = base_versions(c.board_rows(), base, cfg.web.board)
        if body is None:
            raise HTTPException(404, f"unknown base factor: {base}")
        chosen = [
            v["name"]
            for v in body["versions"]
            if (v["prep"] == prep if prep is not None else v["window"] == window)
        ]
        hits = c.standard_rows()
        curves: dict[str, pd.Series] = {}
        missing = []
        for name in chosen:
            hit = hits.get(name)
            curve = (
                version_curve(hit[0], name, c.standard.period, cfg.web.cache_dir, kind)
                if hit
                else None
            )
            if curve is None or curve.empty:
                missing.append(name)
            else:
                curves[name] = curve
        index = sorted(set().union(*(s.index for s in curves.values()))) if curves else []
        return _json(
            {
                "kind": kind,
                "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in index],
                "series": {n: s.reindex(index).ffill().tolist() for n, s in curves.items()},
                "missing": missing,
            }
        )

    @app.get("/api/board/curves")
    def board_curves(points: int = Query(60, ge=10, le=250)):
        """Per standard-evaluated factor: is the detail page cached, and its LS sparkline.

        Reads caches only (never derives), so it stays fast even for uncached factors.
        """
        c = catalog()
        period = c.standard.period
        items = {}
        for name, (run, _row) in c.standard_rows().items():
            key = (run.run_id, name, period, points)
            curve = sparklines.get(key)
            if curve is None:
                curve = ls_sparkline(run, name, period, cfg.web.cache_dir, points)
                if curve is not None:
                    sparklines[key] = curve
            items[name] = {
                "cached": detail_cached(run, name, cfg.web.cache_dir),
                "ls": curve,
            }
        return _json({"points": points, "items": items})

    @app.get("/api/factors/{name}")
    def factor(name: str):
        require_factor(name)
        c = catalog()
        runs = c.runs_for(name)
        hit = c.standard_rows().get(name)
        default = hit[0].run_id if hit else (runs[0].run_id if runs else None)
        return _json(
            {
                "name": name,
                "meta": c.meta(name),
                "runs": [_run_summary(r, c) for r in runs],
                "default_run": default,
            }
        )

    @app.get("/api/factors/{name}/runs/{run_id}")
    def detail(name: str, run_id: str, period: str = "1D"):
        run = require_run(name, run_id)
        if period not in run.periods:
            raise HTTPException(404, f"run {run_id} has no period {period}")
        payload = detail_payload(run, name, period, cfg.web.cache_dir, summary_of(run))
        return _json(payload)

    @app.get("/api/factors/{name}/runs/{run_id}/latest")
    def latest(
        name: str,
        run_id: str,
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=200),
        ascending: bool = False,
    ):
        run = require_run(name, run_id)
        return _json(
            latest_values(run, name, stock_names(), page, size, cfg.web.cache_dir, ascending=ascending)
        )

    def parse_factors(f: str) -> list[str]:
        names = [x for x in (s.strip() for s in f.split(",")) if x]
        if not MIN_COMPARE <= len(names) <= MAX_COMPARE:
            raise HTTPException(422, f"compare needs {MIN_COMPARE}-{MAX_COMPARE} factors")
        for n in names:
            require_factor(n)
        return names

    @app.get("/api/compare")
    def compare(f: str):
        names = parse_factors(f)
        c = catalog()
        rows, inconsistent, unevaluated, missing_curve = [], [], [], []
        curves: dict[str, pd.Series] = {}
        for n in names:
            run, period, standard = chosen_run(n)
            if run is None:
                unevaluated.append(n)
                rows.append(c.board_row(n, None))
                continue
            if not standard:
                inconsistent.append(n)
            row = summary_row(run, n, period, c.summary_cache)
            rows.append(c.board_row(n, (run, row) if row else None))
            # Read caches only: deriving here would take ~1 min per factor and one bad
            # clean_factor_data would fail the whole comparison.
            series = cached_series(run, n, cfg.web.cache_dir)
            column = f"{period}:ls"
            if series is not None and column in series["portfolio_daily_returns"]:
                ls = series["portfolio_daily_returns"][column]
                curves[n] = (1 + ls.fillna(0)).cumprod() - 1
            else:
                missing_curve.append(n)
        index = sorted(set().union(*(s.index for s in curves.values()))) if curves else []
        return _json(
            {
                "factors": names,
                "rows": rows,
                "inconsistent": inconsistent,
                "unevaluated": unevaluated,
                "missing_curve": missing_curve,
                "curves": {
                    "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in index],
                    "series": {n: s.reindex(index).ffill().tolist() for n, s in curves.items()},
                },
            }
        )

    @app.get("/api/compare/correlation")
    def correlation(f: str):
        names = parse_factors(f)
        ranges = {}
        for n in names:
            run, period, _ = chosen_run(n)
            row = summary_row(run, n, period, catalog().summary_cache) if run else None
            start = str(row["start_date"]) if row else cfg.web.standard.start_date
            end = str(row["end_date"]) if row else "99991231"
            ranges[n] = (start, end)
        universe_dir = (
            Path(cfg.zer0share_data_dir)
            / "stock"
            / "universe"
            / f"name={cfg.web.standard.universe}"
        )
        return _json(factor_correlation(names, cfg.factor_dir, universe_dir, ranges))

    @app.api_route("/api/{rest:path}", methods=["GET", "POST"])
    def api_not_found(rest: str):
        raise HTTPException(404, f"no such endpoint: /api/{rest}")

    if static_dir is not None and Path(static_dir).is_dir():
        root = Path(static_dir).resolve()

        @app.get("/{path:path}")
        def spa(path: str):
            candidate = (root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app
