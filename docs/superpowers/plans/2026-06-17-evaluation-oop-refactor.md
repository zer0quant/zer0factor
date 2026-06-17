# Evaluation OOP Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `zer0factor` evaluation subsystem around explicit domain objects covering factor selection, evaluation execution, artifacts, ranked reporting, and family analysis.

**Architecture:** Introduce an OO layer under `zer0factor/eval/` while preserving the current artifact layout and metric formulas. `EvaluationWorkflow` coordinates the full use case; executors handle serial/parallel strategy; `FactorEvaluator` owns single-factor evaluation; reporter and analyzer are first-class post-run components.

**Tech Stack:** Python 3.11+, pandas, Alphalens, matplotlib Agg, click, pytest, existing `FactorStorage` and zer0share-like provider APIs.

---

## File Structure

Create or substantially refactor these files:

- `zer0factor/eval/domain.py`: run config, run identity, request/result dataclasses, path helpers.
- `zer0factor/eval/selection.py`: explicit and registry-backed factor selection.
- `zer0factor/eval/data.py`: factor, price, universe, benchmark, and max-date loading.
- `zer0factor/eval/artifacts.py`: refactor existing artifact functions into `EvaluationArtifactStore` while keeping small function wrappers during migration.
- `zer0factor/eval/figures.py`: `FactorFigureWriter` wrapper around existing plot functions.
- `zer0factor/eval/calculator.py`: `MetricsCalculator` facade around existing metric functions.
- `zer0factor/eval/evaluator.py`: `FactorEvaluator` for one factor.
- `zer0factor/eval/execution.py`: serial and process-pool executors.
- `zer0factor/eval/reporting.py`: `EvaluationReporter`, `SummaryRanker`, `QuantileMonotonicityLoader`, `MarkdownReportRenderer`.
- `zer0factor/eval/analysis.py`: adapt current analyzer into `FamilyAnalyzer` and `EvaluationAnalysisRunner`.
- `zer0factor/eval/workflow.py`: full evaluation workflow.
- `zer0factor/eval/__init__.py`: export new primary API.
- `zer0factor/services/evaluate.py`: delegate to workflow.
- `zer0factor/cli/evaluate_cmds.py`: turn commands into thin workflow adapters.

Keep these modules as low-level function libraries:

- `zer0factor/eval/alphalens_adapter.py`
- `zer0factor/eval/plots.py`
- `zer0factor/eval/metrics/*`

Existing dirty worktree note: before executing each task, inspect `git status --short` and the relevant file diffs. Do not revert unrelated existing changes.

---

### Task 1: Domain Model

**Files:**
- Create: `zer0factor/eval/domain.py`
- Modify: `zer0factor/eval/__init__.py`
- Test: `tests/test_eval_domain.py`

- [ ] **Step 1: Write failing domain tests**

Create `tests/test_eval_domain.py`:

```python
from pathlib import Path

import pytest

from zer0factor.eval.domain import (
    EvaluationRequest,
    EvaluationRun,
    EvaluationRunConfig,
)


def test_run_config_normalizes_periods_output_dir_and_universe(tmp_path):
    config = EvaluationRunConfig(
        factor_names=["factor_a", "factor_b"],
        start_date="20240101",
        end_date=None,
        periods=["1", 5],
        quantiles=5,
        output_dir=str(tmp_path / "evaluations"),
    )

    assert config.factor_names == ("factor_a", "factor_b")
    assert config.periods == (1, 5)
    assert config.output_dir == tmp_path / "evaluations"
    assert config.universe == "univ_trade_base"
    assert config.workers == 1


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"factor_names": []}, "factor_names must not be empty"),
        ({"periods": [0]}, "periods must be positive integers"),
        ({"quantiles": 1}, "quantiles must be >= 2"),
        ({"return_type": "bad"}, "return_type must be one of"),
        ({"max_loss": 1.0}, "max_loss must satisfy"),
        ({"transaction_cost_bps": -1}, "transaction_cost_bps must be >= 0"),
        ({"workers": 0}, "workers must be >= 1"),
    ],
)
def test_run_config_rejects_invalid_values(tmp_path, kwargs, message):
    values = {
        "factor_names": ("factor_a",),
        "start_date": "20240101",
        "end_date": "20240131",
        "periods": (1,),
        "quantiles": 5,
        "output_dir": tmp_path,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        EvaluationRunConfig(**values)


def test_evaluation_run_exposes_paths(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )
    run = EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)

    assert run.summary_csv == tmp_path / "run_001" / "summary.csv"
    assert run.summary_parquet == tmp_path / "run_001" / "summary.parquet"
    assert run.metadata_json == tmp_path / "run_001" / "metadata.json"
    assert run.ranked_summary_csv == tmp_path / "run_001" / "ranked_summary.csv"
    assert run.report_md == tmp_path / "run_001" / "report.md"
    assert run.factor_dir("factor_a") == tmp_path / "run_001" / "factors" / "factor_a"
    assert run.analysis_dir == tmp_path / "run_001" / "analysis"


def test_evaluation_request_allows_explicit_factor_names(tmp_path):
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date=None,
        output_dir=tmp_path,
    )

    assert request.factor_names == ("factor_a",)
    assert request.factor_source == "explicit"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_domain.py -q
```

Expected: fail with `ModuleNotFoundError` or import error for `zer0factor.eval.domain`.

- [ ] **Step 3: Implement `zer0factor/eval/domain.py`**

Create `zer0factor/eval/domain.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from zer0factor.eval.report import ReportThresholds

ReturnType = Literal["open_t1", "close_t0"]
FactorSource = Literal["explicit", "registry"]
DEFAULT_EVALUATION_UNIVERSE = "univ_trade_base"


def _normalize_period(period: object) -> int:
    if isinstance(period, bool):
        raise ValueError("periods must be positive integers")
    if isinstance(period, int):
        return period
    if isinstance(period, str):
        try:
            normalized = int(period)
        except ValueError as exc:
            raise ValueError("periods must be positive integers") from exc
        if str(normalized) == period:
            return normalized
    raise ValueError("periods must be positive integers")


@dataclass(frozen=True)
class EvaluationRunConfig:
    factor_names: tuple[str, ...]
    start_date: str
    end_date: str | None = None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    max_loss: float = 0.35
    universe: str | None = None
    output_dir: Path = Path("data/evaluations")
    rolling_ic_window: int = 63
    benchmark_index: str | None = None
    transaction_cost_bps: float = 10.0
    workers: int = 1
    report_thresholds: ReportThresholds = field(default_factory=ReportThresholds)
    analysis_family: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.factor_names, (str, bytes)):
            raise ValueError("factor_names must be a sequence of names")
        factor_names = tuple(self.factor_names)
        periods = tuple(_normalize_period(period) for period in self.periods)
        if not factor_names:
            raise ValueError("factor_names must not be empty")
        if any(not name for name in factor_names):
            raise ValueError("factor_names must not contain empty names")
        if not periods or any(period <= 0 for period in periods):
            raise ValueError("periods must be positive integers")
        if self.quantiles < 2:
            raise ValueError("quantiles must be >= 2")
        if self.return_type not in {"open_t1", "close_t0"}:
            raise ValueError("return_type must be one of: open_t1, close_t0")
        if not 0 <= self.max_loss < 1:
            raise ValueError("max_loss must satisfy 0 <= max_loss < 1")
        if self.rolling_ic_window < 2:
            raise ValueError("rolling_ic_window must be >= 2")
        if self.transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be >= 0")
        if self.workers < 1:
            raise ValueError("workers must be >= 1")
        object.__setattr__(self, "factor_names", factor_names)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(
            self,
            "universe",
            DEFAULT_EVALUATION_UNIVERSE if self.universe is None else self.universe,
        )


@dataclass(frozen=True)
class EvaluationRequest:
    factor_names: tuple[str, ...] = ()
    factor_source: FactorSource = "explicit"
    registry_path: Path = Path("config/factors.toml")
    enabled_only: bool = True
    categories: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    max_loss: float = 0.35
    universe: str | None = None
    output_dir: Path = Path("data/evaluations")
    rolling_ic_window: int = 63
    benchmark_index: str | None = None
    transaction_cost_bps: float = 10.0
    workers: int = 1
    report_thresholds: ReportThresholds = field(default_factory=ReportThresholds)
    generate_report: bool = True
    analysis_family: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor_names", tuple(self.factor_names))
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(self, "registry_path", Path(self.registry_path))
        object.__setattr__(self, "output_dir", Path(self.output_dir))


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    run_dir: Path
    config: EvaluationRunConfig
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    @property
    def summary_csv(self) -> Path:
        return self.run_dir / "summary.csv"

    @property
    def summary_parquet(self) -> Path:
        return self.run_dir / "summary.parquet"

    @property
    def metadata_json(self) -> Path:
        return self.run_dir / "metadata.json"

    @property
    def ranked_summary_csv(self) -> Path:
        return self.run_dir / "ranked_summary.csv"

    @property
    def report_md(self) -> Path:
        return self.run_dir / "report.md"

    @property
    def analysis_dir(self) -> Path:
        return self.run_dir / "analysis"

    def factor_dir(self, factor_name: str) -> Path:
        return self.run_dir / "factors" / factor_name

    def finish(self) -> EvaluationRun:
        return EvaluationRun(
            run_id=self.run_id,
            run_dir=self.run_dir,
            config=self.config,
            started_at=self.started_at,
            finished_at=datetime.now(),
        )


@dataclass(frozen=True)
class FactorEvaluationResult:
    factor_name: str
    summary: pd.DataFrame
    output_dir: Path
    clean_factor_data: pd.DataFrame | None = None
    daily_ic: pd.DataFrame | None = None
    quantile_returns: pd.DataFrame | None = None
    figure_paths: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EvaluationWorkflowResult:
    run: EvaluationRun
    factor_results: tuple[FactorEvaluationResult, ...]
    summary: pd.DataFrame
    report: object | None = None
    analysis: object | None = None
```

- [ ] **Step 4: Export domain objects**

Modify `zer0factor/eval/__init__.py` to import and include these names in `__all__`:

```python
from zer0factor.eval.domain import (
    EvaluationRequest,
    EvaluationRun,
    EvaluationRunConfig,
    EvaluationWorkflowResult,
)
```

Also add these strings to `__all__`:

```python
"EvaluationRequest",
"EvaluationRun",
"EvaluationRunConfig",
"EvaluationWorkflowResult",
```

- [ ] **Step 5: Run domain tests**

Run:

```bash
uv run pytest tests/test_eval_domain.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/domain.py zer0factor/eval/__init__.py tests/test_eval_domain.py
git commit -m "refactor: add evaluation domain model"
```

---

### Task 2: Factor Selection

**Files:**
- Create: `zer0factor/eval/selection.py`
- Test: `tests/test_eval_selection.py`

- [ ] **Step 1: Write failing selector tests**

Create `tests/test_eval_selection.py`:

```python
from pathlib import Path

import pytest

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.selection import FactorSelector


def _write_registry(path: Path) -> None:
    path.write_text(
        """
[[factors]]
name = "factor_a"
category = "price"
source_type = "neutralized"
enabled = true
tags = ["momentum"]
description = ""

[[factors]]
name = "factor_b"
category = "volume"
source_type = "neutralized"
enabled = false
tags = ["turnover"]
description = ""

[[factors]]
name = "factor_c"
category = "price"
source_type = "neutralized"
enabled = true
tags = ["momentum", "short"]
description = ""
""",
        encoding="utf-8",
    )


def test_selector_returns_explicit_names_in_order():
    selector = FactorSelector()
    request = EvaluationRequest(factor_names=("factor_b", "factor_a"))

    assert selector.resolve(request) == ("factor_b", "factor_a")


def test_selector_rejects_empty_explicit_names():
    selector = FactorSelector()

    with pytest.raises(ValueError, match="factor_names must not be empty"):
        selector.resolve(EvaluationRequest(factor_names=()))


def test_selector_loads_enabled_registry_factors(tmp_path):
    registry_path = tmp_path / "factors.toml"
    _write_registry(registry_path)

    selector = FactorSelector()
    request = EvaluationRequest(
        factor_source="registry",
        registry_path=registry_path,
        enabled_only=True,
    )

    assert selector.resolve(request) == ("factor_a", "factor_c")


def test_selector_filters_registry_categories(tmp_path):
    registry_path = tmp_path / "factors.toml"
    _write_registry(registry_path)

    selector = FactorSelector()
    request = EvaluationRequest(
        factor_source="registry",
        registry_path=registry_path,
        enabled_only=False,
        categories=("volume",),
    )

    assert selector.resolve(request) == ("factor_b",)


def test_selector_rejects_empty_registry_match(tmp_path):
    registry_path = tmp_path / "factors.toml"
    _write_registry(registry_path)

    selector = FactorSelector()
    request = EvaluationRequest(
        factor_source="registry",
        registry_path=registry_path,
        enabled_only=True,
        categories=("missing",),
    )

    with pytest.raises(ValueError, match="no factors matched"):
        selector.resolve(request)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_selection.py -q
```

Expected: fail because `zer0factor.eval.selection` does not exist.

- [ ] **Step 3: Implement selector**

Create `zer0factor/eval/selection.py`:

```python
from __future__ import annotations

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.registry import FactorRegistry


class FactorSelector:
    def resolve(self, request: EvaluationRequest) -> tuple[str, ...]:
        if request.factor_source == "explicit":
            return self._resolve_explicit(request)
        if request.factor_source == "registry":
            return self._resolve_registry(request)
        raise ValueError(
            f"unknown factor_source '{request.factor_source}': "
            "must be 'explicit' or 'registry'"
        )

    def _resolve_explicit(self, request: EvaluationRequest) -> tuple[str, ...]:
        factor_names = tuple(request.factor_names)
        if not factor_names:
            raise ValueError("factor_names must not be empty")
        return factor_names

    def _resolve_registry(self, request: EvaluationRequest) -> tuple[str, ...]:
        registry = FactorRegistry(request.registry_path)
        candidates = registry.filter(enabled=True if request.enabled_only else None)
        if request.categories:
            categories = set(request.categories)
            candidates = [factor for factor in candidates if factor.category in categories]
        factor_names = tuple(factor.name for factor in candidates)
        if not factor_names:
            raise ValueError("no factors matched from registry with the given filters")
        return factor_names
```

- [ ] **Step 4: Run selector tests**

Run:

```bash
uv run pytest tests/test_eval_selection.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add zer0factor/eval/selection.py tests/test_eval_selection.py
git commit -m "refactor: add evaluation factor selector"
```

---

### Task 3: Data Loader Object

**Files:**
- Create: `zer0factor/eval/data.py`
- Modify: `zer0factor/eval/loaders.py`
- Test: `tests/test_eval_data.py`

- [ ] **Step 1: Write failing data loader tests**

Create `tests/test_eval_data.py`:

```python
import pandas as pd
import pytest

from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.storage import FactorStorage


class FakePro:
    def __init__(self):
        self.price_end_date = None

    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        self.price_end_date = end_date
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "open": [10.0, 11.0],
                "close": [10.5, 11.5],
            }
        )

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "universe": [universe, universe],
                "ts_code": ["000001.SZ", "000002.SZ"],
            }
        )

    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "pct_chg": [1.0, -0.5],
            }
        )


def test_data_loader_reads_factor_and_extends_price_window(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101"],
                "ts_code": ["000001.SZ"],
                "value": [1.0],
            }
        ),
    )
    pro = FakePro()
    loader = EvaluationDataLoader(storage, pro)

    factor = loader.load_factor("factor_a", start_date="20240101", end_date=None)
    prices = loader.load_prices(
        start_date="20240101",
        end_date="20240102",
        periods=(5,),
    )

    assert factor["value"].tolist() == [1.0]
    assert len(prices) == 2
    assert pro.price_end_date == "20240127"


def test_data_loader_builds_universe_panel(tmp_path):
    loader = EvaluationDataLoader(None, FakePro())

    panel = loader.load_universe(
        universe_name="demo",
        start_date="20240101",
        end_date="20240102",
    )

    assert panel.index.tolist() == pd.to_datetime(["2024-01-01", "2024-01-02"]).tolist()
    assert panel.columns.tolist() == ["000001.SZ", "000002.SZ"]
    assert panel.loc[pd.Timestamp("2024-01-01"), "000001.SZ"]
    assert not panel.loc[pd.Timestamp("2024-01-01"), "000002.SZ"]


def test_data_loader_loads_benchmark_returns(tmp_path):
    loader = EvaluationDataLoader(None, FakePro())

    returns = loader.load_benchmark_returns(
        ts_code="000300.SH",
        start_date="20240101",
        end_date="20240102",
    )

    assert returns.name == "000300.SH"
    assert returns.loc[pd.Timestamp("2024-01-01")] == pytest.approx(0.01)


def test_data_loader_max_factor_trade_date_accepts_float_dates(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": [20240101.0, 20240220.0],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    loader = EvaluationDataLoader(storage, FakePro())

    assert loader.max_factor_trade_date(("factor_a",), start_date="20240101") == "20240220"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_data.py -q
```

Expected: fail because `EvaluationDataLoader` does not exist.

- [ ] **Step 3: Implement data loader**

Create `zer0factor/eval/data.py` by moving behavior from `loaders.py` and
`pipeline.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


class EvaluationDataLoader:
    def __init__(self, storage, pro) -> None:
        self.storage = storage
        self.pro = pro

    def load_factor(
        self,
        factor_name: str,
        *,
        start_date: str,
        end_date: str | None,
    ) -> pd.DataFrame:
        return self.storage.read(factor_name, start_date=start_date, end_date=end_date)

    def load_prices(
        self,
        *,
        start_date: str,
        end_date: str | None,
        periods: tuple[int, ...],
    ) -> pd.DataFrame:
        extended_end = _extend_end_date(end_date or start_date, max(periods) * 3 + 10)
        return self.pro.pro_bar(
            ts_code=None,
            start_date=start_date,
            end_date=extended_end,
            adj=None,
        )

    def load_universe(
        self,
        *,
        universe_name: str | None,
        start_date: str,
        end_date: str | None,
    ) -> pd.DataFrame | None:
        if universe_name is None:
            return None
        universe = self.pro.universe(
            universe=universe_name,
            start_date=start_date,
            end_date=end_date,
            fields="trade_date,universe,ts_code",
        )
        return _universe_to_panel(universe)

    def load_benchmark_returns(
        self,
        *,
        ts_code: str | None,
        start_date: str,
        end_date: str | None,
    ) -> pd.Series | None:
        if ts_code is None:
            return None
        df = self.pro.index_daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="trade_date,pct_chg",
        )
        if df.empty:
            return pd.Series(dtype=float, name=ts_code)
        result = (
            df[["trade_date", "pct_chg"]]
            .dropna(subset=["pct_chg"])
            .drop_duplicates(subset=["trade_date"], keep="last")
            .assign(date=lambda d: pd.to_datetime(d["trade_date"], format="%Y%m%d"))
            .set_index("date")["pct_chg"]
            / 100
        )
        result.name = ts_code
        return result.sort_index()

    def max_factor_trade_date(
        self,
        factor_names: tuple[str, ...],
        *,
        start_date: str,
    ) -> str:
        max_dates = []
        for factor_name in factor_names:
            factor_data = self.load_factor(
                factor_name,
                start_date=start_date,
                end_date=None,
            )
            if not factor_data.empty:
                max_dates.append(max_factor_trade_date(factor_data))
        if not max_dates:
            return start_date
        return max(max_dates)


def _universe_to_panel(universe: pd.DataFrame) -> pd.DataFrame:
    if universe.empty:
        return pd.DataFrame(dtype=bool)
    missing_columns = {"trade_date", "ts_code"}.difference(universe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"universe data must contain columns: {missing}")
    universe = universe.dropna(subset=["trade_date", "ts_code"])
    if universe.empty:
        return pd.DataFrame(dtype=bool)
    normalized = pd.DataFrame(
        {
            "date": pd.to_datetime(universe["trade_date"], format="%Y%m%d"),
            "ts_code": universe["ts_code"],
            "member": True,
        }
    )
    panel = normalized.pivot_table(
        index="date",
        columns="ts_code",
        values="member",
        aggfunc="any",
        fill_value=False,
    )
    return panel.astype(bool).sort_index().sort_index(axis=1)


def max_factor_trade_date(factor_data: pd.DataFrame) -> str:
    raw_dates = factor_data["trade_date"]
    if pd.api.types.is_numeric_dtype(raw_dates):
        normalized = raw_dates.astype("Int64").astype(str)
    else:
        numeric_dates = pd.to_numeric(raw_dates, errors="coerce")
        if numeric_dates.notna().all():
            normalized = numeric_dates.astype("Int64").astype(str)
        else:
            normalized = raw_dates.astype(str)
    dates = pd.to_datetime(normalized, format="%Y%m%d")
    return dates.max().strftime("%Y%m%d")


def _extend_end_date(base_date: str, days: int) -> str:
    parsed = datetime.strptime(base_date, "%Y%m%d")
    return (parsed + timedelta(days=days)).strftime("%Y%m%d")
```

- [ ] **Step 4: Keep compatibility wrappers in `loaders.py`**

Modify `zer0factor/eval/loaders.py` so existing tests and imports keep working:

```python
from __future__ import annotations

from zer0factor.eval.data import EvaluationDataLoader


def load_stored_factor(storage, factor_name: str, *, start_date: str, end_date: str | None):
    return EvaluationDataLoader(storage, None).load_factor(
        factor_name,
        start_date=start_date,
        end_date=end_date,
    )


def load_price_data(pro, *, start_date: str, end_date: str | None, periods: tuple[int, ...]):
    return EvaluationDataLoader(None, pro).load_prices(
        start_date=start_date,
        end_date=end_date,
        periods=periods,
    )


def load_universe_panel(pro, *, universe_name: str | None, start_date: str, end_date: str | None):
    return EvaluationDataLoader(None, pro).load_universe(
        universe_name=universe_name,
        start_date=start_date,
        end_date=end_date,
    )


def load_index_daily(pro, *, ts_code: str, start_date: str, end_date: str | None):
    return EvaluationDataLoader(None, pro).load_benchmark_returns(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
    )
```

- [ ] **Step 5: Run data loader and existing loader tests**

Run:

```bash
uv run pytest tests/test_eval_data.py tests/test_eval_loaders.py tests/test_eval_pipeline.py::test_load_price_data_extends_end_date_with_conservative_buffer -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/data.py zer0factor/eval/loaders.py tests/test_eval_data.py
git commit -m "refactor: add evaluation data loader"
```

---

### Task 4: Artifact Store, Figure Writer, and Metrics Facade

**Files:**
- Create: `zer0factor/eval/figures.py`
- Create: `zer0factor/eval/calculator.py`
- Modify: `zer0factor/eval/artifacts.py`
- Test: `tests/test_eval_components.py`

- [ ] **Step 1: Write component tests**

Create `tests/test_eval_components.py`:

```python
import json

import pandas as pd

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig, FactorEvaluationResult


def _run(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        periods=(1,),
        output_dir=tmp_path,
    )
    return EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)


def test_artifact_store_writes_factor_and_run_artifacts(tmp_path):
    run = _run(tmp_path)
    store = EvaluationArtifactStore()
    store.create_run(run)
    result = FactorEvaluationResult(
        factor_name="factor_a",
        output_dir=run.factor_dir("factor_a"),
        summary=pd.DataFrame({"factor_name": ["factor_a"]}),
        clean_factor_data=pd.DataFrame({"x": [1]}),
        daily_ic=pd.DataFrame({"1D": [0.1]}),
        quantile_returns=pd.DataFrame({"1D": [0.01, 0.02]}, index=[1, 2]),
    )

    factor_paths = store.write_factor_artifacts(result)
    run_paths = store.write_run_summary(
        run,
        pd.DataFrame({"factor_name": ["factor_a"]}),
    )

    assert factor_paths["clean_factor_data"].exists()
    assert factor_paths["daily_ic"].exists()
    assert factor_paths["quantile_returns"].exists()
    assert run_paths["summary_csv"] == run.summary_csv
    assert run_paths["summary_parquet"] == run.summary_parquet
    assert run_paths["metadata"] == run.metadata_json
    metadata = json.loads(run.metadata_json.read_text(encoding="utf-8"))
    assert metadata["run_id"] == "run_001"
    assert metadata["factor_names"] == ["factor_a"]


def test_metrics_calculator_builds_period_sample_counts(monkeypatch):
    calculator = MetricsCalculator()

    def fake_clean(*args, **kwargs):
        period = kwargs["periods"][0]
        return pd.DataFrame({f"{period}D": [0.1, None, 0.2]})

    monkeypatch.setattr(
        "zer0factor.eval.calculator.get_clean_factor_and_forward_returns",
        fake_clean,
    )

    counts = calculator.calculate_period_sample_counts(
        pd.Series(dtype=float),
        pd.DataFrame(),
        quantiles=2,
        periods=(1, 5),
        max_loss=0.35,
    )

    assert counts == {"1D": 2, "5D": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_components.py -q
```

Expected: fail because new classes are missing.

- [ ] **Step 3: Refactor `artifacts.py`**

Add `EvaluationArtifactStore` to `zer0factor/eval/artifacts.py`, keeping existing
functions as wrappers:

```python
class EvaluationArtifactStore:
    def create_run(self, run) -> None:
        run.run_dir.mkdir(parents=True, exist_ok=False)

    def write_factor_artifacts(self, result) -> dict[str, Path]:
        if result.clean_factor_data is None:
            raise ValueError("clean_factor_data is required to write factor artifacts")
        if result.daily_ic is None:
            raise ValueError("daily_ic is required to write factor artifacts")
        if result.quantile_returns is None:
            raise ValueError("quantile_returns is required to write factor artifacts")
        return write_factor_artifacts(
            factor_dir=result.output_dir,
            clean_factor_data=result.clean_factor_data,
            daily_ic=result.daily_ic,
            quantile_returns=result.quantile_returns,
        )

    def write_run_summary(self, run, summary: pd.DataFrame) -> dict[str, Path]:
        return write_run_summary(
            run_dir=run.run_dir,
            summary=summary,
            config=run.config,
            run_id=run.run_id,
        )
```

Update `_build_metadata` to accept both old `EvaluationConfig` and new
`EvaluationRunConfig`; both expose the same fields used by metadata.

- [ ] **Step 4: Create `figures.py`**

Create `zer0factor/eval/figures.py`:

```python
from __future__ import annotations

from pathlib import Path

from zer0factor.eval.plots import (
    plot_cumulative_ic,
    plot_quantile_returns,
    plot_rolling_ic,
)


class FactorFigureWriter:
    def write(self, result, *, rolling_ic_window: int) -> tuple[Path, ...]:
        if result.daily_ic is None:
            raise ValueError("daily_ic is required to write figures")
        if result.quantile_returns is None:
            raise ValueError("quantile_returns is required to write figures")
        if result.quantile_returns.empty or len(result.quantile_returns.columns) == 0:
            raise ValueError(f"{result.factor_name}: no quantile return periods")
        figures_dir = result.output_dir / "figures"
        quantile_return_paths = tuple(
            plot_quantile_returns(
                result.quantile_returns,
                period=str(period),
                output_path=figures_dir / f"quantile_returns_{period}.png",
            )
            for period in result.quantile_returns.columns
        )
        return quantile_return_paths + (
            plot_cumulative_ic(
                result.daily_ic,
                output_path=figures_dir / "cumulative_ic.png",
            ),
            plot_rolling_ic(
                result.daily_ic,
                window=rolling_ic_window,
                output_path=figures_dir / f"rolling_ic_{rolling_ic_window}.png",
            ),
        )
```

- [ ] **Step 5: Create `calculator.py`**

Create `zer0factor/eval/calculator.py`:

```python
from __future__ import annotations

import io
import warnings
from contextlib import contextmanager, redirect_stdout

import pandas as pd
from alphalens.utils import get_clean_factor_and_forward_returns

from zer0factor.eval.metrics import (
    build_summary,
    calculate_daily_ic,
    calculate_quantile_returns,
)


class MetricsCalculator:
    def clean_factor_and_forward_returns(
        self,
        factor: pd.Series,
        prices: pd.DataFrame,
        *,
        quantiles: int,
        periods: tuple[int, ...],
        max_loss: float,
    ) -> pd.DataFrame:
        with suppress_known_evaluation_warnings(), redirect_stdout(io.StringIO()):
            return get_clean_factor_and_forward_returns(
                factor,
                prices,
                quantiles=quantiles,
                periods=periods,
                max_loss=max_loss,
            )

    def calculate_daily_ic(self, clean_factor_data: pd.DataFrame) -> pd.DataFrame:
        return calculate_daily_ic(clean_factor_data)

    def calculate_quantile_returns(self, clean_factor_data: pd.DataFrame) -> pd.DataFrame:
        return calculate_quantile_returns(clean_factor_data)

    def build_factor_summary(self, **kwargs) -> pd.DataFrame:
        return build_summary(**kwargs)

    def calculate_period_sample_counts(
        self,
        factor: pd.Series,
        prices: pd.DataFrame,
        *,
        quantiles: int,
        periods: tuple[int, ...],
        max_loss: float,
    ) -> dict[str, int]:
        counts = {}
        for period in periods:
            period_label = f"{period}D"
            clean = self.clean_factor_and_forward_returns(
                factor,
                prices,
                quantiles=quantiles,
                periods=(period,),
                max_loss=max_loss,
            )
            counts[period_label] = (
                int(clean[period_label].count()) if period_label in clean else 0
            )
        return counts


@contextmanager
def suppress_known_evaluation_warnings():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The default fill_method='pad' in DataFrame.pct_change is deprecated.*",
            category=FutureWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Series.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="DataFrame.fillna with 'method' is deprecated.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Downcasting object dtype arrays on \\.fillna.*",
            category=FutureWarning,
            module=r"alphalens\.performance",
        )
        warnings.filterwarnings(
            "ignore",
            message="Non-vectorized DateOffset being applied.*",
            category=pd.errors.PerformanceWarning,
            module=r"alphalens\.utils",
        )
        yield
```

- [ ] **Step 6: Run component tests**

Run:

```bash
uv run pytest tests/test_eval_components.py tests/test_eval_artifacts.py tests/test_eval_metrics.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add zer0factor/eval/artifacts.py zer0factor/eval/figures.py zer0factor/eval/calculator.py tests/test_eval_components.py
git commit -m "refactor: add evaluation component objects"
```

---

### Task 5: Single-Factor Evaluator

**Files:**
- Create: `zer0factor/eval/evaluator.py`
- Modify: `zer0factor/eval/pipeline.py`
- Test: `tests/test_eval_evaluator.py`

- [ ] **Step 1: Write evaluator integration test**

Create `tests/test_eval_evaluator.py`:

```python
import pandas as pd

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig
from zer0factor.eval.evaluator import FactorEvaluator
from zer0factor.eval.figures import FactorFigureWriter
from zer0factor.storage import FactorStorage


class FakePro:
    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102", "20240103", "20240104"],
                "ts_code": ["000001.SZ"] * 4,
                "open": [10.0, 11.0, 12.0, 13.0],
                "close": [10.5, 11.5, 12.5, 13.5],
            }
        )

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "universe": [universe, universe],
                "ts_code": ["000001.SZ", "000001.SZ"],
            }
        )


def test_factor_evaluator_writes_outputs(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    clean = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 2],
            "1D": [0.01, 0.02],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )
    monkeypatch.setattr(
        "zer0factor.eval.calculator.get_clean_factor_and_forward_returns",
        lambda *args, **kwargs: clean,
    )
    config = EvaluationRunConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240102",
        periods=(1,),
        quantiles=2,
        output_dir=tmp_path / "evaluations",
    )
    run = EvaluationRun(
        run_id="run_001",
        run_dir=tmp_path / "evaluations" / "run_001",
        config=config,
    )
    run.run_dir.mkdir(parents=True)
    evaluator = FactorEvaluator(
        data_loader=EvaluationDataLoader(storage, FakePro()),
        metric_calculator=MetricsCalculator(),
        artifact_store=EvaluationArtifactStore(),
        figure_writer=FactorFigureWriter(),
    )

    result = evaluator.evaluate("factor_a", run)

    assert result.factor_name == "factor_a"
    assert result.output_dir == run.factor_dir("factor_a")
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert (result.output_dir / "clean_factor_data.parquet").exists()
    assert (result.output_dir / "daily_ic.parquet").exists()
    assert (result.output_dir / "quantile_returns.parquet").exists()
    assert (result.output_dir / "figures" / "quantile_returns_1D.png").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_evaluator.py -q
```

Expected: fail because `FactorEvaluator` does not exist.

- [ ] **Step 3: Implement `FactorEvaluator`**

Create `zer0factor/eval/evaluator.py` by moving single-factor logic from
`pipeline.evaluate_factor`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from zer0factor.eval.alphalens_adapter import (
    build_price_matrix,
    factor_long_to_alphalens_series,
    filter_factor_by_universe,
)


@dataclass(frozen=True)
class EvaluationSharedData:
    price_data: pd.DataFrame | None = None
    universe_panel: pd.DataFrame | None = None


class FactorEvaluator:
    def __init__(
        self,
        *,
        data_loader,
        metric_calculator,
        artifact_store,
        figure_writer,
        log_info=None,
    ) -> None:
        self.data_loader = data_loader
        self.metric_calculator = metric_calculator
        self.artifact_store = artifact_store
        self.figure_writer = figure_writer
        self.log_info = log_info or (lambda message: None)

    def evaluate(
        self,
        factor_name: str,
        run,
        shared_data: EvaluationSharedData | None = None,
    ):
        from zer0factor.eval.domain import FactorEvaluationResult

        config = run.config
        if factor_name not in config.factor_names:
            raise ValueError("factor_name must be included in config.factor_names")
        shared_data = shared_data or EvaluationSharedData()
        factor_data = self.data_loader.load_factor(
            factor_name,
            start_date=config.start_date,
            end_date=config.end_date,
        )
        if factor_data.empty:
            raise ValueError(f"{factor_name}: no factor data")
        self.log_info(f"evaluation_factor_load_finished factor={factor_name} rows={len(factor_data)}")

        factor = factor_long_to_alphalens_series(factor_data)
        factor = filter_factor_by_universe(factor, shared_data.universe_panel)
        if factor.empty:
            raise ValueError(f"{factor_name}: no factor data after universe filtering")

        price_data = shared_data.price_data
        if price_data is None:
            price_end_date = config.end_date or self.data_loader.max_factor_trade_date(
                (factor_name,),
                start_date=config.start_date,
            )
            price_data = self.data_loader.load_prices(
                start_date=config.start_date,
                end_date=price_end_date,
                periods=config.periods,
            )
        prices = build_price_matrix(price_data, config.return_type)

        self.log_info(f"evaluation_clean_factor_started factor={factor_name}")
        clean_factor_data = self.metric_calculator.clean_factor_and_forward_returns(
            factor,
            prices,
            quantiles=config.quantiles,
            periods=config.periods,
            max_loss=config.max_loss,
        )
        if clean_factor_data.empty:
            raise ValueError(f"{factor_name}: no clean factor data")
        self.log_info(
            f"evaluation_clean_factor_finished factor={factor_name} rows={len(clean_factor_data)}"
        )

        daily_ic = self.metric_calculator.calculate_daily_ic(clean_factor_data)
        quantile_returns = self.metric_calculator.calculate_quantile_returns(clean_factor_data)
        if quantile_returns.empty or len(quantile_returns.columns) == 0:
            raise ValueError(f"{factor_name}: no quantile return periods")
        self.log_info(
            f"evaluation_metrics_finished factor={factor_name} periods={len(quantile_returns.columns)}"
        )

        index_returns = self.data_loader.load_benchmark_returns(
            ts_code=config.benchmark_index,
            start_date=config.start_date,
            end_date=config.end_date,
        )
        summary = self.metric_calculator.build_factor_summary(
            factor_name=factor_name,
            return_type=config.return_type,
            clean_factor_data_sample_count=len(clean_factor_data),
            clean_factor_data_start=clean_factor_data.index.get_level_values("date").min(),
            clean_factor_data_end=clean_factor_data.index.get_level_values("date").max(),
            quantiles=config.quantiles,
            daily_ic=daily_ic,
            quantile_returns=quantile_returns,
            clean_factor_data=clean_factor_data,
            index_returns=index_returns,
            transaction_cost_bps=config.transaction_cost_bps,
            period_sample_counts=self.metric_calculator.calculate_period_sample_counts(
                factor,
                prices,
                quantiles=config.quantiles,
                periods=config.periods,
                max_loss=config.max_loss,
            ),
        )
        result = FactorEvaluationResult(
            factor_name=factor_name,
            clean_factor_data=clean_factor_data,
            summary=summary,
            daily_ic=daily_ic,
            quantile_returns=quantile_returns,
            output_dir=run.factor_dir(factor_name),
        )
        self.artifact_store.write_factor_artifacts(result)
        figure_paths = self.figure_writer.write(
            result,
            rolling_ic_window=config.rolling_ic_window,
        )
        self.log_info(
            f"evaluation_artifacts_written factor={factor_name} output_dir={result.output_dir}"
        )
        return FactorEvaluationResult(
            factor_name=factor_name,
            clean_factor_data=clean_factor_data,
            summary=summary,
            daily_ic=daily_ic,
            quantile_returns=quantile_returns,
            figure_paths=figure_paths,
            output_dir=result.output_dir,
        )
```

- [ ] **Step 4: Add temporary compatibility in `pipeline.evaluate_factor`**

Modify `zer0factor/eval/pipeline.py` so `evaluate_factor` delegates to
`FactorEvaluator`. Keep the old signature during this task to avoid a large
CLI/test update:

```python
from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig
from zer0factor.eval.evaluator import EvaluationSharedData, FactorEvaluator
from zer0factor.eval.figures import FactorFigureWriter
```

Inside `evaluate_factor`, convert old `EvaluationConfig` to `EvaluationRunConfig`
and delegate:

```python
run = EvaluationRun(
    run_id=Path(run_dir).name,
    run_dir=Path(run_dir),
    config=EvaluationRunConfig(
        factor_names=tuple(config.factor_names),
        start_date=config.start_date,
        end_date=config.end_date,
        periods=config.periods,
        quantiles=config.quantiles,
        return_type=config.return_type,
        max_loss=config.max_loss,
        universe=config.universe,
        output_dir=config.output_dir,
        rolling_ic_window=config.rolling_ic_window,
        benchmark_index=config.benchmark_index,
        transaction_cost_bps=config.transaction_cost_bps,
    ),
)
return FactorEvaluator(
    data_loader=EvaluationDataLoader(storage, pro),
    metric_calculator=MetricsCalculator(),
    artifact_store=EvaluationArtifactStore(),
    figure_writer=FactorFigureWriter(),
    log_info=log_info,
).evaluate(
    factor_name,
    run,
    EvaluationSharedData(price_data=price_data, universe_panel=universe_panel),
)
```

Remove now-unused single-factor helper code only when tests confirm the wrapper
works.

- [ ] **Step 5: Run evaluator and existing pipeline tests**

Run:

```bash
uv run pytest tests/test_eval_evaluator.py tests/test_eval_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/evaluator.py zer0factor/eval/pipeline.py tests/test_eval_evaluator.py
git commit -m "refactor: add single factor evaluator"
```

---

### Task 6: Serial and Parallel Executors

**Files:**
- Create: `zer0factor/eval/execution.py`
- Modify: `zer0factor/eval/pipeline.py`
- Test: `tests/test_eval_execution.py`

- [ ] **Step 1: Write executor tests**

Create `tests/test_eval_execution.py`:

```python
import pandas as pd

from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig, FactorEvaluationResult
from zer0factor.eval.execution import SerialEvaluationExecutor


class RecordingEvaluator:
    def __init__(self):
        self.calls = []

    def evaluate(self, factor_name, run, shared_data=None):
        self.calls.append((factor_name, shared_data))
        return FactorEvaluationResult(
            factor_name=factor_name,
            output_dir=run.factor_dir(factor_name),
            summary=pd.DataFrame({"factor_name": [factor_name]}),
        )


def test_serial_executor_preserves_factor_order(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_b", "factor_a"),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )
    run = EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)
    evaluator = RecordingEvaluator()
    executor = SerialEvaluationExecutor(evaluator=evaluator, data_loader=None)

    results = executor.execute(run)

    assert [r.factor_name for r in results] == ["factor_b", "factor_a"]
    assert [call[0] for call in evaluator.calls] == ["factor_b", "factor_a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_execution.py -q
```

Expected: fail because `SerialEvaluationExecutor` does not exist.

- [ ] **Step 3: Implement executors**

Create `zer0factor/eval/execution.py`:

```python
from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from zer0factor.eval.calculator import suppress_known_evaluation_warnings
from zer0factor.eval.domain import FactorEvaluationResult
from zer0factor.eval.evaluator import EvaluationSharedData


class EvaluationExecutor(Protocol):
    def execute(self, run) -> tuple[FactorEvaluationResult, ...]:
        ...


@dataclass
class SerialEvaluationExecutor:
    evaluator: object
    data_loader: object
    log_info: object | None = None

    def execute(self, run) -> tuple[FactorEvaluationResult, ...]:
        shared_data = self._load_shared_data(run)
        results = []
        with suppress_known_evaluation_warnings():
            for factor_name in run.config.factor_names:
                self._log(f"evaluation_factor_started factor={factor_name}")
                results.append(
                    self.evaluator.evaluate(
                        factor_name,
                        run,
                        shared_data=shared_data,
                    )
                )
        return tuple(results)

    def _load_shared_data(self, run) -> EvaluationSharedData:
        if self.data_loader is None:
            return EvaluationSharedData()
        price_end_date = run.config.end_date or self.data_loader.max_factor_trade_date(
            run.config.factor_names,
            start_date=run.config.start_date,
        )
        self._log(
            "evaluation_price_load_started "
            f"start_date={run.config.start_date} end_date={price_end_date}"
        )
        price_data = self.data_loader.load_prices(
            start_date=run.config.start_date,
            end_date=price_end_date,
            periods=run.config.periods,
        )
        self._log(f"evaluation_price_load_finished rows={len(price_data)}")
        universe_panel = self.data_loader.load_universe(
            universe_name=run.config.universe,
            start_date=run.config.start_date,
            end_date=run.config.end_date,
        )
        return EvaluationSharedData(price_data=price_data, universe_panel=universe_panel)

    def _log(self, message: str) -> None:
        if self.log_info is not None:
            self.log_info(message)
```

Then add `ProcessPoolEvaluationExecutor` by moving the current
`_init_evaluation_worker`, `_evaluate_factor_task`, and `_evaluate_factors_parallel`
logic from `pipeline.py`. Keep module-level worker globals in `execution.py` so
spawn workers can import them. The worker context should include a factory or the
picklable dependencies needed to construct `FactorEvaluator` inside the worker.

- [ ] **Step 4: Delegate old `evaluate_factors` to executors**

Modify `zer0factor/eval/pipeline.py`:

- create an `EvaluationRun` after `create_run_directory`
- create `EvaluationDataLoader`, `MetricsCalculator`, `EvaluationArtifactStore`,
  `FactorFigureWriter`, and `FactorEvaluator`
- select `SerialEvaluationExecutor` for `workers == 1`
- select `ProcessPoolEvaluationExecutor` for `workers > 1`
- write the run summary with `EvaluationArtifactStore`

Keep the old `evaluate_factors` signature during this task.

- [ ] **Step 5: Run serial and parallel regression tests**

Run:

```bash
uv run pytest tests/test_eval_execution.py tests/test_eval_pipeline.py::test_evaluate_factors_writes_run_artifacts tests/test_eval_pipeline.py::test_evaluate_factors_parallel_matches_serial tests/test_eval_pipeline.py::test_evaluate_factors_rejects_bad_workers -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/execution.py zer0factor/eval/pipeline.py tests/test_eval_execution.py
git commit -m "refactor: add evaluation executors"
```

---

### Task 7: Reporting Objects

**Files:**
- Create: `zer0factor/eval/reporting.py`
- Modify: `zer0factor/eval/report.py`
- Test: `tests/test_eval_reporting.py`

- [ ] **Step 1: Write reporting object tests**

Create `tests/test_eval_reporting.py`:

```python
import pandas as pd
import pytest

from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig
from zer0factor.eval.report import ReportThresholds
from zer0factor.eval.reporting import (
    EvaluationReporter,
    MarkdownReportRenderer,
    QuantileMonotonicityLoader,
    SummaryRanker,
)


def _summary():
    return pd.DataFrame(
        {
            "factor_name": ["factor_good", "factor_bad"],
            "period": ["1D", "1D"],
            "sample_count": [2000, 500],
            "IC Mean": [0.03, 0.01],
            "adjusted_ICIR": [0.5, 0.2],
            "directional_IC>0 %": [55.0, 49.0],
            "long_short_spread_bps": [4.0, -1.0],
        }
    )


def test_summary_ranker_scores_and_flags_rows():
    monotonicity = pd.Series(
        [0.8, -0.2],
        index=pd.MultiIndex.from_tuples(
            [("factor_good", "1D"), ("factor_bad", "1D")],
            names=["factor_name", "period"],
        ),
    )
    ranked = SummaryRanker(ReportThresholds()).rank(_summary(), monotonicity)

    assert ranked["factor_name"].tolist() == ["factor_good", "factor_bad"]
    assert ranked.loc[0, "adjusted_score"] == pytest.approx(4.7)
    assert ranked.loc[0, "passed"]
    assert not ranked.loc[1, "passed"]


def test_reporter_writes_ranked_summary_and_markdown(tmp_path):
    config = EvaluationRunConfig(
        factor_names=("factor_good", "factor_bad"),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )
    run = EvaluationRun(run_id="run_001", run_dir=tmp_path / "run_001", config=config)
    run.run_dir.mkdir(parents=True)
    factor_dir = run.factor_dir("factor_good")
    factor_dir.mkdir(parents=True)
    pd.DataFrame({"1D": [0.01, 0.02, 0.03]}, index=[1, 2, 3]).to_parquet(
        factor_dir / "quantile_returns.parquet"
    )
    (factor_dir / "figures").mkdir()
    (factor_dir / "figures" / "quantile_returns_1D.png").write_text("fake")
    reporter = EvaluationReporter(
        ranker=SummaryRanker(ReportThresholds()),
        monotonicity_loader=QuantileMonotonicityLoader(),
        renderer=MarkdownReportRenderer(),
    )

    result = reporter.generate(run, _summary())

    assert result.ranked_summary_path == run.ranked_summary_csv
    assert result.report_path == run.report_md
    assert result.ranked_summary_path.exists()
    assert result.report_path.exists()
    assert "factor_good" in result.report_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_reporting.py -q
```

Expected: fail because `zer0factor.eval.reporting` does not exist.

- [ ] **Step 3: Implement `reporting.py`**

Create `zer0factor/eval/reporting.py` by moving the logic currently in
`report.py` into classes:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from zer0factor.eval.report import (
    EvaluationReportResult,
    ReportThresholds,
    build_ranked_summary,
    load_quantile_monotonicity,
    render_markdown_report,
)


@dataclass(frozen=True)
class SummaryRanker:
    thresholds: ReportThresholds

    def rank(
        self,
        summary: pd.DataFrame,
        monotonicity: pd.Series | None = None,
    ) -> pd.DataFrame:
        return build_ranked_summary(
            summary,
            self.thresholds,
            monotonicity=monotonicity,
        )


class QuantileMonotonicityLoader:
    def load(self, run, summary: pd.DataFrame) -> pd.Series:
        return load_quantile_monotonicity(run.run_dir, summary)


class MarkdownReportRenderer:
    def render(self, run, ranked_summary: pd.DataFrame, thresholds: ReportThresholds) -> str:
        return render_markdown_report(
            run_dir=run.run_dir,
            ranked_summary=ranked_summary,
            thresholds=thresholds,
        )


class EvaluationReporter:
    def __init__(
        self,
        *,
        ranker: SummaryRanker,
        monotonicity_loader: QuantileMonotonicityLoader,
        renderer: MarkdownReportRenderer,
    ) -> None:
        self.ranker = ranker
        self.monotonicity_loader = monotonicity_loader
        self.renderer = renderer

    def generate(self, run, summary: pd.DataFrame) -> EvaluationReportResult:
        monotonicity = self.monotonicity_loader.load(run, summary)
        ranked = self.ranker.rank(summary, monotonicity)
        ranked.to_csv(run.ranked_summary_csv, index=False)
        run.report_md.write_text(
            self.renderer.render(run, ranked, self.ranker.thresholds),
            encoding="utf-8",
        )
        return EvaluationReportResult(
            run_dir=run.run_dir,
            report_path=run.report_md,
            ranked_summary_path=run.ranked_summary_csv,
            ranked_summary=ranked,
        )
```

- [ ] **Step 4: Make `report.py` delegate to objects**

Modify `generate_evaluation_report` in `zer0factor/eval/report.py` to construct
a lightweight run adapter or `EvaluationRun` and call `EvaluationReporter`.
Keep `build_ranked_summary` and `render_markdown_report` during this task so
existing tests remain valid.

- [ ] **Step 5: Run report tests**

Run:

```bash
uv run pytest tests/test_eval_reporting.py tests/test_eval_report.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/reporting.py zer0factor/eval/report.py tests/test_eval_reporting.py
git commit -m "refactor: add evaluation reporting objects"
```

---

### Task 8: Family Analysis Runner

**Files:**
- Modify: `zer0factor/eval/analysis.py`
- Test: `tests/test_eval_analysis.py`

- [ ] **Step 1: Add runner tests**

Append to `tests/test_eval_analysis.py`:

```python
def test_analysis_runner_writes_family_outputs(tmp_path):
    from zer0factor.eval.analysis import EvaluationAnalysisRunner
    from zer0factor.eval.domain import EvaluationRun, EvaluationRunConfig

    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    pd.DataFrame([
        _row("z_size_industry_neu_intraday_return_ma20"),
        _row("z_neu_daily_return"),
    ]).to_csv(run_dir / "ranked_summary.csv", index=False)
    config = EvaluationRunConfig(
        factor_names=("z_size_industry_neu_intraday_return_ma20", "z_neu_daily_return"),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
        analysis_family="rolling_return",
    )
    run = EvaluationRun(run_id="run_001", run_dir=run_dir, config=config)

    result = EvaluationAnalysisRunner().run(run, family_name="rolling_return")

    assert result.report_path == run.analysis_dir / "analysis_report.md"
    assert result.analyzed_count == 1
    assert result.skipped_count == 1
    assert (run.analysis_dir / "ranked_factors.csv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_analysis.py::test_analysis_runner_writes_family_outputs -q
```

Expected: fail because `EvaluationAnalysisRunner` does not exist.

- [ ] **Step 3: Add `FamilyAnalyzer` alias and runner**

Modify `zer0factor/eval/analysis.py`:

```python
FamilyAnalyzer = EvaluationAnalyzer


class EvaluationAnalysisRunner:
    def __init__(self, configs: dict[str, EvaluationAnalysisConfig] | None = None) -> None:
        self.configs = configs or ANALYSIS_CONFIGS

    def run(self, run, *, family_name: str) -> AnalysisRunResult:
        if family_name not in self.configs:
            known = ", ".join(sorted(self.configs))
            raise ValueError(f"unknown analysis family: {family_name}; known families: {known}")
        summary_path = (
            run.ranked_summary_csv
            if run.ranked_summary_csv.exists()
            else run.summary_csv
        )
        if not summary_path.exists():
            raise FileNotFoundError(f"evaluation summary not found: {summary_path}")
        return run_analysis(
            summary_path=summary_path,
            output_dir=run.analysis_dir,
            config=self.configs[family_name],
        )
```

- [ ] **Step 4: Run analysis tests**

Run:

```bash
uv run pytest tests/test_eval_analysis.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add zer0factor/eval/analysis.py tests/test_eval_analysis.py
git commit -m "refactor: add evaluation analysis runner"
```

---

### Task 9: Evaluation Workflow

**Files:**
- Create: `zer0factor/eval/workflow.py`
- Modify: `zer0factor/eval/__init__.py`
- Test: `tests/test_eval_workflow.py`

- [ ] **Step 1: Write workflow integration test**

Create `tests/test_eval_workflow.py`:

```python
import pandas as pd

from zer0factor.eval.workflow import EvaluationWorkflow
from zer0factor.eval.domain import EvaluationRequest
from zer0factor.storage import FactorStorage


class FakePro:
    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102", "20240103", "20240104"],
                "ts_code": ["000001.SZ"] * 4,
                "open": [10.0, 11.0, 12.0, 13.0],
                "close": [10.5, 11.5, 12.5, 13.5],
            }
        )

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "universe": [universe, universe],
                "ts_code": ["000001.SZ", "000001.SZ"],
            }
        )

    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(columns=["trade_date", "pct_chg"])


def test_workflow_runs_evaluation_and_report(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    clean = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 2],
            "1D": [0.01, 0.02],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )
    monkeypatch.setattr(
        "zer0factor.eval.calculator.get_clean_factor_and_forward_returns",
        lambda *args, **kwargs: clean,
    )
    workflow = EvaluationWorkflow.from_dependencies(storage=storage, pro=FakePro())

    result = workflow.run(
        EvaluationRequest(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240102",
            periods=(1,),
            quantiles=2,
            output_dir=tmp_path / "evaluations",
            generate_report=True,
        )
    )

    assert result.run.summary_csv.exists()
    assert result.run.ranked_summary_csv.exists()
    assert result.run.report_md.exists()
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert result.report is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_eval_workflow.py -q
```

Expected: fail because `EvaluationWorkflow` does not exist.

- [ ] **Step 3: Implement workflow**

Create `zer0factor/eval/workflow.py`:

```python
from __future__ import annotations

from datetime import datetime

import pandas as pd

from zer0factor.eval.artifacts import EvaluationArtifactStore
from zer0factor.eval.calculator import MetricsCalculator
from zer0factor.eval.data import EvaluationDataLoader
from zer0factor.eval.domain import (
    EvaluationRequest,
    EvaluationRun,
    EvaluationRunConfig,
    EvaluationWorkflowResult,
)
from zer0factor.eval.evaluator import FactorEvaluator
from zer0factor.eval.execution import ProcessPoolEvaluationExecutor, SerialEvaluationExecutor
from zer0factor.eval.figures import FactorFigureWriter
from zer0factor.eval.reporting import (
    EvaluationReporter,
    MarkdownReportRenderer,
    QuantileMonotonicityLoader,
    SummaryRanker,
)
from zer0factor.eval.selection import FactorSelector
from zer0factor.notify.null import NullNotifier


class EvaluationRunFactory:
    def create(self, config: EvaluationRunConfig, run_id: str | None = None) -> EvaluationRun:
        resolved_run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        run = EvaluationRun(
            run_id=resolved_run_id,
            run_dir=config.output_dir / resolved_run_id,
            config=config,
        )
        run.run_dir.mkdir(parents=True, exist_ok=False)
        return run


class EvaluationWorkflow:
    def __init__(
        self,
        *,
        selector: FactorSelector,
        run_factory: EvaluationRunFactory,
        data_loader: EvaluationDataLoader,
        artifact_store: EvaluationArtifactStore,
        metric_calculator: MetricsCalculator,
        figure_writer: FactorFigureWriter,
        reporter_factory,
        analysis_runner=None,
        notifier=None,
        log_info=None,
    ) -> None:
        self.selector = selector
        self.run_factory = run_factory
        self.data_loader = data_loader
        self.artifact_store = artifact_store
        self.metric_calculator = metric_calculator
        self.figure_writer = figure_writer
        self.reporter_factory = reporter_factory
        self.analysis_runner = analysis_runner
        self.notifier = notifier or NullNotifier()
        self.log_info = log_info or (lambda message: None)

    @classmethod
    def from_dependencies(cls, *, storage, pro, notifier=None, log_info=None):
        data_loader = EvaluationDataLoader(storage, pro)
        return cls(
            selector=FactorSelector(),
            run_factory=EvaluationRunFactory(),
            data_loader=data_loader,
            artifact_store=EvaluationArtifactStore(),
            metric_calculator=MetricsCalculator(),
            figure_writer=FactorFigureWriter(),
            reporter_factory=lambda thresholds: EvaluationReporter(
                ranker=SummaryRanker(thresholds),
                monotonicity_loader=QuantileMonotonicityLoader(),
                renderer=MarkdownReportRenderer(),
            ),
            notifier=notifier,
            log_info=log_info,
        )

    def run(self, request: EvaluationRequest, *, run_id: str | None = None) -> EvaluationWorkflowResult:
        factor_names = self.selector.resolve(request)
        config = EvaluationRunConfig(
            factor_names=factor_names,
            start_date=self._require_start_date(request),
            end_date=request.end_date,
            periods=request.periods,
            quantiles=request.quantiles,
            return_type=request.return_type,
            max_loss=request.max_loss,
            universe=request.universe,
            output_dir=request.output_dir,
            rolling_ic_window=request.rolling_ic_window,
            benchmark_index=request.benchmark_index,
            transaction_cost_bps=request.transaction_cost_bps,
            workers=request.workers,
            report_thresholds=request.report_thresholds,
            analysis_family=request.analysis_family,
        )
        run = self.run_factory.create(config, run_id=run_id)
        self.notifier.notify_start(
            "evaluate",
            details={"因子数": str(len(config.factor_names)), "workers": str(config.workers)},
        )
        self.log_info(
            "evaluation_run_started "
            f"factors={len(config.factor_names)} "
            f"start_date={config.start_date} "
            f"end_date={config.end_date or 'latest'} "
            f"periods={','.join(str(period) for period in config.periods)} "
            f"return_type={config.return_type}"
        )
        evaluator = FactorEvaluator(
            data_loader=self.data_loader,
            metric_calculator=self.metric_calculator,
            artifact_store=self.artifact_store,
            figure_writer=self.figure_writer,
            log_info=self.log_info,
        )
        if config.workers > 1 and len(config.factor_names) > 1:
            executor = ProcessPoolEvaluationExecutor.from_workflow(
                run=run,
                data_loader=self.data_loader,
                workers=config.workers,
                log_info=self.log_info,
            )
        else:
            executor = SerialEvaluationExecutor(
                evaluator=evaluator,
                data_loader=self.data_loader,
                log_info=self.log_info,
            )
        factor_results = executor.execute(run)
        summary = pd.concat(
            [factor_result.summary for factor_result in factor_results],
            ignore_index=True,
        )
        self.artifact_store.write_run_summary(run, summary)
        report = None
        if request.generate_report:
            report = self.reporter_factory(config.report_thresholds).generate(run, summary)
        analysis = None
        if request.analysis_family and self.analysis_runner is not None:
            analysis = self.analysis_runner.run(run, family_name=request.analysis_family)
        finished_run = run.finish()
        self.log_info(
            "evaluation_run_finished "
            f"run_id={run.run_id} output_dir={run.run_dir} factors={len(factor_results)}"
        )
        return EvaluationWorkflowResult(
            run=finished_run,
            factor_results=factor_results,
            summary=summary,
            report=report,
            analysis=analysis,
        )

    def _require_start_date(self, request: EvaluationRequest) -> str:
        if request.start_date is None:
            raise ValueError("start_date is required")
        return request.start_date
```

If `ProcessPoolEvaluationExecutor.from_workflow` is not yet available from Task
6, add it there as a constructor helper or temporarily raise only when selected.

- [ ] **Step 4: Export workflow**

Modify `zer0factor/eval/__init__.py`:

```python
from zer0factor.eval.workflow import EvaluationRunFactory, EvaluationWorkflow
```

Add to `__all__`:

```python
"EvaluationRunFactory",
"EvaluationWorkflow",
```

- [ ] **Step 5: Run workflow tests**

Run:

```bash
uv run pytest tests/test_eval_workflow.py tests/test_eval_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/workflow.py zer0factor/eval/__init__.py tests/test_eval_workflow.py
git commit -m "refactor: add evaluation workflow"
```

---

### Task 10: Batch Config and Service Layer

**Files:**
- Modify: `zer0factor/eval/batch.py`
- Modify: `zer0factor/services/evaluate.py`
- Test: `tests/test_eval_batch.py`
- Test: `tests/test_services_evaluate.py`

- [ ] **Step 1: Add service test**

Create `tests/test_services_evaluate.py`:

```python
from zer0factor.eval.domain import EvaluationRequest
from zer0factor.services.evaluate import EvaluationService


class RecordingWorkflow:
    def __init__(self):
        self.requests = []

    def run(self, request, *, run_id=None):
        self.requests.append((request, run_id))
        return "result"


def test_evaluation_service_delegates_to_workflow():
    workflow = RecordingWorkflow()
    service = EvaluationService(workflow=workflow)
    request = EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
    )

    result = service.run(request, run_id="run_001")

    assert result == "result"
    assert workflow.requests == [(request, "run_001")]
```

- [ ] **Step 2: Run service test to verify it fails**

Run:

```bash
uv run pytest tests/test_services_evaluate.py -q
```

Expected: fail because `EvaluationService` still expects storage/pro/config.

- [ ] **Step 3: Refactor `EvaluationService`**

Modify `zer0factor/services/evaluate.py`:

```python
from __future__ import annotations

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.workflow import EvaluationWorkflow


class EvaluationService:
    def __init__(self, workflow: EvaluationWorkflow) -> None:
        self._workflow = workflow

    @classmethod
    def from_dependencies(cls, storage, pro, *, log_info=None, notifier=None):
        return cls(
            EvaluationWorkflow.from_dependencies(
                storage=storage,
                pro=pro,
                log_info=log_info,
                notifier=notifier,
            )
        )

    def run(self, request: EvaluationRequest, *, run_id: str | None = None):
        return self._workflow.run(request, run_id=run_id)
```

- [ ] **Step 4: Update batch config loader to emit request-friendly fields**

Keep `BatchEvaluationConfig` for now, but add:

```python
def to_request(self) -> EvaluationRequest:
    return EvaluationRequest(
        factor_names=self.factor_names,
        factor_source="explicit",
        start_date=self.start_date,
        end_date=self.end_date,
        periods=self.periods,
        quantiles=self.quantiles,
        return_type=self.return_type,
        universe=self.universe,
        max_loss=self.max_loss,
        output_dir=self.output_dir,
        transaction_cost_bps=self.transaction_cost_bps,
        workers=self.workers,
        report_thresholds=self.report_thresholds,
        generate_report=True,
    )
```

If `factor_source = "registry"` is present in the TOML, preserve the current
behavior of resolving to concrete factor names in `load_batch_evaluation_config`
for this migration step.

- [ ] **Step 5: Run batch and service tests**

Run:

```bash
uv run pytest tests/test_eval_batch.py tests/test_services_evaluate.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/batch.py zer0factor/services/evaluate.py tests/test_services_evaluate.py
git commit -m "refactor: route evaluation service through workflow"
```

---

### Task 11: CLI Migration

**Files:**
- Modify: `zer0factor/cli/evaluate_cmds.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Update CLI tests for workflow request fields**

In `tests/test_cli.py`, update existing evaluation command tests so their fake
service captures an `EvaluationRequest`, not `EvaluationConfig`. Assert:

```python
assert request.factor_names == ("factor_a",)
assert request.start_date == "20240101"
assert request.periods == (1, 5, 10)
assert request.workers == 2
```

For `evaluate-batch`, assert:

```python
assert request.generate_report
assert request.report_thresholds.min_ic == expected_value
```

- [ ] **Step 2: Run focused CLI tests to verify failure**

Run:

```bash
uv run pytest tests/test_cli.py -q
```

Expected: fail because CLI still constructs `EvaluationConfig` and calls old service API.

- [ ] **Step 3: Update `_run_evaluation_job`**

Modify `zer0factor/cli/evaluate_cmds.py`:

```python
from zer0factor.eval import EvaluationRequest
```

In `_run_evaluation_job`, construct `EvaluationRequest`:

```python
request = EvaluationRequest(
    factor_names=factor_names,
    factor_source="explicit",
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
    workers=workers,
    generate_report=False,
)
service = EvaluationService.from_dependencies(
    app.storage,
    app.pro,
    log_info=log_progress,
    notifier=notifier,
)
result = service.run(request)
```

For `evaluate-batch`, use `batch.to_request()` and set `benchmark_index` from
the CLI option by creating a new `EvaluationRequest` with the same fields and
the override:

```python
request = batch.to_request()
request = replace(request, benchmark_index=benchmark_index)
result = service.run(request)
```

Import `replace` from `dataclasses`.

- [ ] **Step 4: Keep command output compatible**

Because the workflow result stores the run under `result.run`, update prints:

```python
click.echo(f"Evaluation run {result.run.run_id} written to {result.run.run_dir}")
```

For batch report preview, use:

```python
report = result.report
if report is None:
    raise click.ClickException("evaluation report was not generated")
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/cli/evaluate_cmds.py tests/test_cli.py
git commit -m "refactor: migrate evaluation cli to workflow"
```

---

### Task 12: Remove Old Pipeline API as Primary Path

**Files:**
- Modify: `zer0factor/eval/pipeline.py`
- Modify: `zer0factor/eval/config.py`
- Modify: `zer0factor/eval/__init__.py`
- Modify tests that import old functions directly.

- [ ] **Step 1: Move remaining tests from old functions to objects**

Update tests that import `evaluate_factor` or `evaluate_factors` so they use:

```python
from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.workflow import EvaluationWorkflow
```

The test setup should call:

```python
workflow = EvaluationWorkflow.from_dependencies(storage=storage, pro=pro)
result = workflow.run(
    EvaluationRequest(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240102",
        periods=(1,),
        quantiles=2,
        output_dir=tmp_path / "evaluations",
        generate_report=False,
    ),
    run_id="run_001",
)
```

Use `result.run.run_dir`, `result.factor_results`, and `result.summary` in
assertions.

- [ ] **Step 2: Run migrated tests to verify failures are only API-related**

Run:

```bash
uv run pytest tests/test_eval_pipeline.py tests/test_eval_workflow.py -q
```

Expected: failures point to old function assumptions, not metric behavior.

- [ ] **Step 3: Shrink `pipeline.py`**

Replace `zer0factor/eval/pipeline.py` with compatibility wrappers or remove it
from exports. If wrappers are kept for one transition commit, they should be
thin:

```python
from __future__ import annotations

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.eval.workflow import EvaluationWorkflow


def run_evaluation(request: EvaluationRequest, *, storage, pro, run_id: str | None = None):
    return EvaluationWorkflow.from_dependencies(storage=storage, pro=pro).run(
        request,
        run_id=run_id,
    )
```

Do not keep duplicated single-factor or parallel logic in `pipeline.py`.

- [ ] **Step 4: Update exports**

Modify `zer0factor/eval/__init__.py` so the primary exported API is:

```python
"EvaluationRequest",
"EvaluationRun",
"EvaluationRunConfig",
"EvaluationWorkflow",
"EvaluationWorkflowResult",
```

Remove `evaluate_factor` and `evaluate_factors` from `__all__` after tests and
CLI no longer use them.

- [ ] **Step 5: Run full eval test suite**

Run:

```bash
uv run pytest tests/test_eval_*.py tests/test_services_evaluate.py tests/test_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/pipeline.py zer0factor/eval/config.py zer0factor/eval/__init__.py tests
git commit -m "refactor: make evaluation workflow primary api"
```

---

### Task 13: Final Verification and Cleanup

**Files:**
- Modify only files with unused imports or references exposed by verification.

- [ ] **Step 1: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: no lint errors.

- [ ] **Step 3: Inspect evaluation package size and imports**

Run:

```bash
wc -l zer0factor/eval/*.py zer0factor/eval/metrics/*.py
```

Expected: `pipeline.py` is no longer the largest orchestration file; responsibilities
are distributed across focused modules.

- [ ] **Step 4: Confirm artifact behavior manually with a small run**

Run a minimal existing CLI command appropriate for local data:

```bash
uv run python main.py evaluate-factor log_total_market_cap --periods 1 --quantiles 5
```

Expected: command prints a run ID and writes `summary.csv`, factor artifacts,
`ranked_summary.csv`, and `report.md` under `data/evaluations/<run_id>/`.

If local data for `log_total_market_cap` is unavailable, record the exact
missing-data error and rely on the integration tests from Tasks 9 and 11.

- [ ] **Step 5: Commit cleanup**

If verification required cleanup:

```bash
git add <changed-files>
git commit -m "chore: clean up evaluation oop refactor"
```

If no cleanup was required, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Complete evaluation flow: Tasks 1, 5, 6, 9, 11, 12.
- Factor selection: Task 2.
- Data loading: Task 3.
- Metrics and artifacts: Task 4.
- Reporting and ranking: Task 7.
- Family analysis: Task 8.
- CLI and service adapter: Tasks 10 and 11.
- Removal of old primary API: Task 12.
- Verification: Task 13.

Gap scan:

- This plan contains no unspecified steps.
- Each code-bearing task includes exact file paths, expected tests, and concrete
  code skeletons.

Type consistency:

- The plan consistently uses `EvaluationRequest`, `EvaluationRunConfig`,
  `EvaluationRun`, `FactorEvaluationResult`, and `EvaluationWorkflowResult`.
- `EvaluationWorkflow.run()` is the final primary API.
- `FactorEvaluator.evaluate()` accepts `factor_name`, `run`, and optional
  `EvaluationSharedData`.
