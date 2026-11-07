"""Task endpoints: create, list, inspect, stream logs, cancel, retry, evaluation options."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from zer0factor.config import Config
from zer0factor.jobs.scheduler import Scheduler
from zer0factor.jobs.specs import EvaluateParams, SpecError, build_spec
from zer0factor.jobs.store import TaskStore
from zer0factor.web.jsonsafe import to_jsonable

LOG_CHUNK = 262144


class TaskCreate(BaseModel):
    kind: str
    params: dict = {}
    source: str = "web"


@dataclass
class TaskContext:
    cfg: Config
    config_path: Path
    store: TaskStore
    scheduler: Scheduler
    known_factors: Callable[[], set[str]]
    known_runs: Callable[[], dict[str, int]]  # run_id -> number of factors
    known_families: Callable[[], set[str]]


def active_run_ids(store: TaskStore) -> set[str]:
    return {
        t["run_id"]
        for t in store.list(status=["queued", "running"], kind="evaluate", limit=100000)
        if t.get("run_id")
    }


def list_universes(cfg: Config) -> list[str]:
    root = Path(cfg.zer0share_data_dir) / "stock" / "universe"
    if not root.is_dir():
        return []
    return sorted(p.name.removeprefix("name=") for p in root.iterdir() if p.name.startswith("name="))


def create_task(ctx: TaskContext, kind: str, params: dict, source: str = "web") -> dict:
    runs = ctx.known_runs()
    try:
        spec = build_spec(
            kind,
            params,
            cfg=ctx.cfg,
            config_path=ctx.config_path,
            known_factors=ctx.known_factors() if kind == "evaluate" else set(),
            known_families=ctx.known_families() if kind == "build" else set(),
            known_runs=set(runs) | active_run_ids(ctx.store),
            run_factor_counts=runs,
        )
    except SpecError as exc:
        raise HTTPException(422, str(exc)) from exc
    source = source if source in {"web", "agent", "cli"} else "web"
    return ctx.store.create(
        kind=spec.kind,
        queue=spec.queue,
        title=spec.title,
        params=spec.params,
        command=spec.command,
        cwd=str(Path.cwd()),
        run_id=spec.run_id,
        source=source,
        progress_total=spec.progress_total,
    )


def register_task_routes(app: FastAPI, ctx: TaskContext) -> None:
    store = ctx.store

    def require(task_id: str) -> dict:
        task = store.get(task_id)
        if task is None:
            raise HTTPException(404, f"unknown task: {task_id}")
        return task

    @app.get("/api/tasks")
    def tasks(
        status: str = "",
        kind: str = "",
        limit: int = Query(200, ge=1, le=1000),
    ):
        statuses = [s for s in status.split(",") if s] or None
        active = store.list(status=["queued", "running"], limit=100000)
        return JSONResponse(
            to_jsonable(
                {
                    "tasks": store.list(status=statuses, kind=kind or None, limit=limit),
                    "running": sum(t["status"] == "running" for t in active),
                    "queued": sum(t["status"] == "queued" for t in active),
                }
            )
        )

    @app.post("/api/tasks", status_code=201)
    def post_task(body: TaskCreate):
        return create_task(ctx, body.kind, body.params, body.source)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str):
        return require(task_id)

    @app.get("/api/tasks/{task_id}/log")
    def task_log(task_id: str, offset: int = Query(0, ge=0)):
        t = require(task_id)
        path = store.log_path(task_id)
        done = t["status"] not in {"queued", "running"}
        if not path.exists():
            return {"text": "", "offset": 0, "size": 0, "done": done}
        size = path.stat().st_size
        if offset >= size:
            return {"text": "", "offset": size, "size": size, "done": done}
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(LOG_CHUNK)
        return {
            "text": chunk.decode("utf-8", errors="replace"),
            "offset": offset + len(chunk),
            "size": size,
            "done": done and offset + len(chunk) >= size,
        }

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel(task_id: str):
        require(task_id)
        return ctx.scheduler.cancel(task_id)

    @app.post("/api/tasks/{task_id}/retry", status_code=201)
    def retry(task_id: str):
        t = require(task_id)
        params = dict(t["params"])
        return create_task(ctx, t["kind"], params, t.get("source") or "web")

    @app.get("/api/eval/options")
    def eval_options():
        defaults = EvaluateParams(factors=["_"]).model_dump()
        defaults.pop("factors")
        return {
            "standard": asdict(ctx.cfg.web.standard),
            "defaults": defaults,
            "universes": list_universes(ctx.cfg),
            "return_types": ["open_t1", "close_t0"],
        }
