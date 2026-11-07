"""Validate task parameters and turn them into CLI command lines.

Only structured parameters are accepted; the command is always assembled here from a fixed
set of subcommands, so no caller can run an arbitrary command through the task system.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zer0factor.config import Config


Date = Annotated[str, Field(pattern=r"^\d{8}$")]
Code = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.]{1,64}$")]


class SpecError(ValueError):
    pass


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluateParams(_Params):
    factors: list[Code] = Field(min_length=1, max_length=500)
    start_date: Date = "20160101"
    end_date: Date | None = None
    periods: list[Annotated[int, Field(ge=1, le=250)]] = Field(
        default_factory=lambda: [1, 5, 10], min_length=1, max_length=10
    )
    quantiles: int = Field(10, ge=2, le=50)
    return_type: Literal["open_t1", "close_t0"] = "open_t1"
    universe: Code | None = None
    max_loss: float = Field(0.35, ge=0, le=1)
    transaction_cost_bps: float = Field(10.0, ge=0, le=1000)
    benchmark_index: Code | None = None
    workers: int = Field(1, ge=1, le=64)


class BuildParams(_Params):
    family: Code
    stage: Literal["raw", "preprocess", "all"] = "all"
    start_date: Date | None = None
    end_date: Date | None = None
    workers: int = Field(1, ge=1, le=64)
    update_registry: bool = False


class BaseParams(_Params):
    target: Literal["returns", "market_cap"]


class WarmParams(_Params):
    run_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{1,64}$")]
    workers: int = Field(8, ge=1, le=32)


PARAMS = {
    "evaluate": EvaluateParams,
    "build": BuildParams,
    "base": BaseParams,
    "warm": WarmParams,
}
QUEUES = {"evaluate": "heavy", "build": "heavy", "base": "heavy", "warm": "light"}


@dataclass(frozen=True)
class TaskSpec:
    kind: str
    queue: str
    title: str
    params: dict
    command: list[str]
    run_id: str | None = None
    progress_total: int | None = None
    extra: dict = field(default_factory=dict)


def cli_head(cfg: Config, config_path: Path) -> list[str]:
    """Command prefix for running the zer0factor CLI with the configured interpreter."""
    python = cfg.web.task_python or sys.executable
    return [python, "-m", "zer0factor.cli", "--config", str(Path(config_path).resolve())]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _new_run_id(known_runs: set[str], evaluations_dir: Path) -> str:
    base = _timestamp()
    candidate, n = base, 1
    while candidate in known_runs or (evaluations_dir / candidate).exists():
        n += 1
        candidate = f"{base}_{n}"
    return candidate


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err["loc"])
    return f"{loc}: {err['msg']}" if loc else err["msg"]


def build_spec(
    kind: str,
    raw: dict,
    *,
    cfg: Config,
    config_path: Path,
    known_factors: set[str],
    known_families: set[str],
    known_runs: set[str],
    run_factor_counts: dict[str, int] | None = None,
) -> TaskSpec:
    model = PARAMS.get(kind)
    if model is None:
        raise SpecError(f"unknown task kind: {kind}")
    try:
        params = model.model_validate(raw or {})
    except ValidationError as exc:
        raise SpecError(_first_error(exc)) from exc

    head = cli_head(cfg, config_path)
    run_id = None
    total = None

    if isinstance(params, EvaluateParams):
        unknown = [f for f in params.factors if f not in known_factors]
        if unknown:
            raise SpecError(f"unknown factors: {', '.join(unknown[:10])}")
        factors = list(dict.fromkeys(params.factors))
        params = params.model_copy(update={"factors": factors})
        evaluations_dir = Path(cfg.web.evaluations_dir).resolve()
        run_id = _new_run_id(known_runs, evaluations_dir)
        args = ["evaluate-factors", *factors, "--start-date", params.start_date]
        if params.end_date:
            args += ["--end-date", params.end_date]
        args += [
            "--periods", ",".join(str(p) for p in params.periods),
            "--quantiles", str(params.quantiles),
            "--return-type", params.return_type,
            "--max-loss", str(params.max_loss),
            "--transaction-cost-bps", str(params.transaction_cost_bps),
        ]
        if params.universe:
            args += ["--universe", params.universe]
        if params.benchmark_index:
            args += ["--benchmark-index", params.benchmark_index]
        if params.workers > 1:
            args += ["--workers", str(params.workers)]
        args += ["--output-dir", str(evaluations_dir), "--run-id", run_id]
        total = len(factors)
        title = f"评估 {factors[0]}" + (f" 等 {len(factors)} 个因子" if len(factors) > 1 else "")
    elif isinstance(params, BuildParams):
        if params.family not in known_families:
            raise SpecError(f"unknown factor family: {params.family}")
        args = ["build-factors", "--family", params.family, "--stage", params.stage,
                "--workers", str(params.workers)]
        if params.start_date:
            args += ["--start-date", params.start_date]
        if params.end_date:
            args += ["--end-date", params.end_date]
        if params.update_registry:
            args += ["--update-registry"]
        stage = {"raw": "原始计算", "preprocess": "预处理", "all": "原始计算 + 预处理"}
        title = f"构建 {params.family}（{stage[params.stage]}）"
    elif isinstance(params, BaseParams):
        args = ["compute-returns" if params.target == "returns" else "compute-market-cap"]
        title = "计算基础收益因子" if params.target == "returns" else "计算市值因子"
    else:
        if params.run_id not in known_runs:
            raise SpecError(f"unknown evaluation run: {params.run_id}")
        args = ["web-warm", "--run", params.run_id, "--workers", str(params.workers)]
        run_id = params.run_id
        total = (run_factor_counts or {}).get(params.run_id)
        title = f"预热缓存 {params.run_id}"

    return TaskSpec(
        kind=kind,
        queue=QUEUES[kind],
        title=title,
        params=params.model_dump(),
        command=head + args,
        run_id=run_id,
        progress_total=total,
    )
