# Factor Evaluation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable factor evaluation pipeline from the working Alphalens notebook flow, with Python API, CLI, machine-readable artifacts, and PNG figures.

**Architecture:** Add a focused `zer0factor/eval/` package with config/result dataclasses, loaders/adapters, metrics, plots, artifacts, and orchestration. Keep `main.py` as a thin CLI wrapper that constructs `FactorStorage`, `LocalPro`, and `EvaluationConfig`, then calls the eval API.

**Tech Stack:** Python 3.11, pandas, alphalens-reloaded, matplotlib, click, pytest, pyarrow/parquet, existing `FactorStorage` and zer0share `LocalPro`.

---

## File Structure

Create:

- `zer0factor/eval/config.py`: dataclasses and config validation.
- `zer0factor/eval/alphalens_adapter.py`: factor, price, and universe format conversions.
- `zer0factor/eval/loaders.py`: stored factor, price, and universe loading helpers.
- `zer0factor/eval/metrics.py`: Alphalens metric wrappers and summary table builder.
- `zer0factor/eval/plots.py`: PNG figure writers.
- `zer0factor/eval/artifacts.py`: run directory creation and artifact writes.
- `zer0factor/eval/pipeline.py`: single-factor and multi-factor orchestration.
- `tests/test_eval_config.py`
- `tests/test_eval_alphalens_adapter.py`
- `tests/test_eval_metrics.py`
- `tests/test_eval_artifacts.py`
- `tests/test_eval_pipeline.py`

Modify:

- `zer0factor/eval/__init__.py`: export public API.
- `main.py`: add `evaluate-factor` and `evaluate-factors` commands.
- `tests/test_main.py`: CLI registration smoke tests.

Do not modify:

- `notebooks/01_alphalens_pct_chg.ipynb`
- existing preprocessing, storage, or factor computation behavior

---

### Task 1: Evaluation Config And Result Dataclasses

**Files:**
- Create: `tests/test_eval_config.py`
- Create: `zer0factor/eval/config.py`
- Modify: `zer0factor/eval/__init__.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_eval_config.py`:

```python
from pathlib import Path

import pytest

from zer0factor.eval import EvaluationConfig


def test_evaluation_config_defaults_to_open_t1_and_evaluations_dir():
    config = EvaluationConfig(
        factor_names=("z_neu_daily_return",),
        start_date="20240101",
        end_date="20240131",
    )

    assert config.factor_names == ("z_neu_daily_return",)
    assert config.periods == (1, 5, 10)
    assert config.quantiles == 10
    assert config.return_type == "open_t1"
    assert config.max_loss == 0.35
    assert config.universe is None
    assert config.output_dir == Path("data/evaluations")
    assert config.rolling_ic_window == 63


def test_evaluation_config_normalizes_periods_and_output_dir():
    config = EvaluationConfig(
        factor_names=["factor_a", "factor_b"],
        start_date="20240101",
        end_date=None,
        periods=[1, 3],
        output_dir="tmp/evals",
    )

    assert config.factor_names == ("factor_a", "factor_b")
    assert config.periods == (1, 3)
    assert config.output_dir == Path("tmp/evals")


@pytest.mark.parametrize("return_type", ["bad", "open", "close"])
def test_evaluation_config_rejects_unknown_return_type(return_type):
    with pytest.raises(ValueError, match="return_type must be one of"):
        EvaluationConfig(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240131",
            return_type=return_type,
        )


def test_evaluation_config_rejects_empty_factor_names():
    with pytest.raises(ValueError, match="factor_names must not be empty"):
        EvaluationConfig(
            factor_names=(),
            start_date="20240101",
            end_date="20240131",
        )


def test_evaluation_config_rejects_non_positive_periods():
    with pytest.raises(ValueError, match="periods must be positive integers"):
        EvaluationConfig(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240131",
            periods=(1, 0),
        )
```

- [ ] **Step 2: Run config tests to verify failure**

Run:

```bash
uv run pytest tests/test_eval_config.py -q
```

Expected: FAIL because `EvaluationConfig` is not defined.

- [ ] **Step 3: Implement dataclasses**

Create `zer0factor/eval/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

ReturnType = Literal["open_t1", "close_t0"]


@dataclass(frozen=True)
class EvaluationConfig:
    factor_names: tuple[str, ...]
    start_date: str
    end_date: str | None
    periods: tuple[int, ...] = (1, 5, 10)
    quantiles: int = 10
    return_type: ReturnType = "open_t1"
    max_loss: float = 0.35
    universe: str | None = None
    output_dir: Path = Path("data/evaluations")
    rolling_ic_window: int = 63

    def __post_init__(self) -> None:
        factor_names = tuple(self.factor_names)
        periods = tuple(int(period) for period in self.periods)
        output_dir = Path(self.output_dir)

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

        object.__setattr__(self, "factor_names", factor_names)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "output_dir", output_dir)


@dataclass(frozen=True)
class FactorEvaluationResult:
    factor_name: str
    clean_factor_data: pd.DataFrame
    summary: pd.DataFrame
    daily_ic: pd.DataFrame
    quantile_returns: pd.DataFrame
    figure_paths: tuple[Path, ...] = field(default_factory=tuple)
    output_dir: Path | None = None


@dataclass(frozen=True)
class EvaluationRunResult:
    run_id: str
    output_dir: Path
    factor_results: tuple[FactorEvaluationResult, ...]
    summary: pd.DataFrame
    metadata_path: Path
```

Modify `zer0factor/eval/__init__.py`:

```python
from zer0factor.eval.config import (
    EvaluationConfig,
    EvaluationRunResult,
    FactorEvaluationResult,
)

__all__ = [
    "EvaluationConfig",
    "EvaluationRunResult",
    "FactorEvaluationResult",
]
```

- [ ] **Step 4: Run config tests to verify pass**

Run:

```bash
uv run pytest tests/test_eval_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add zer0factor/eval/__init__.py zer0factor/eval/config.py tests/test_eval_config.py
git commit -m "feat: add evaluation config dataclasses"
```

---

### Task 2: Alphalens Input Adapter

**Files:**
- Create: `tests/test_eval_alphalens_adapter.py`
- Create: `zer0factor/eval/alphalens_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_eval_alphalens_adapter.py`:

```python
import pandas as pd
import pytest

from zer0factor.eval.alphalens_adapter import (
    build_price_matrix,
    factor_long_to_alphalens_series,
    filter_factor_by_universe,
)


def test_factor_long_to_alphalens_series_uses_date_asset_index():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240102", "20240102"],
            "ts_code": ["000001.SZ", "000002.SZ"],
            "value": [1.5, -0.2],
        }
    )

    result = factor_long_to_alphalens_series(factor)

    assert result.index.names == ["date", "asset"]
    assert result.loc[(pd.Timestamp("2024-01-02"), "000001.SZ")] == 1.5
    assert result.name == "factor"


def test_factor_long_to_alphalens_series_rejects_duplicates():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240102", "20240102"],
            "ts_code": ["000001.SZ", "000001.SZ"],
            "value": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="duplicate date/asset"):
        factor_long_to_alphalens_series(factor)


def test_build_price_matrix_open_t1_shifts_open_prices():
    raw = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240102", "20240103"],
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "open": [10.0, 11.0, 12.0],
            "close": [10.5, 11.5, 12.5],
        }
    )

    result = build_price_matrix(raw, return_type="open_t1")

    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 11.0
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 12.0
    assert pd.isna(result.loc[pd.Timestamp("2024-01-03"), "000001.SZ"])


def test_build_price_matrix_close_t0_does_not_shift_close_prices():
    raw = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240102"],
            "ts_code": ["000001.SZ", "000001.SZ"],
            "open": [10.0, 11.0],
            "close": [10.5, 11.5],
        }
    )

    result = build_price_matrix(raw, return_type="close_t0")

    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 10.5
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 11.5


def test_filter_factor_by_universe_keeps_only_members():
    factor = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-01"), "000002.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
        name="factor",
    )
    universe = pd.DataFrame(
        {
            "000001.SZ": [True, False],
            "000002.SZ": [False, True],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )

    result = filter_factor_by_universe(factor, universe)

    assert list(result.index) == [(pd.Timestamp("2024-01-01"), "000001.SZ")]
```

- [ ] **Step 2: Run adapter tests to verify failure**

Run:

```bash
uv run pytest tests/test_eval_alphalens_adapter.py -q
```

Expected: FAIL because `zer0factor.eval.alphalens_adapter` does not exist.

- [ ] **Step 3: Implement adapter functions**

Create `zer0factor/eval/alphalens_adapter.py`:

```python
from __future__ import annotations

import pandas as pd

from zer0factor.eval.config import ReturnType


def factor_long_to_alphalens_series(factor: pd.DataFrame) -> pd.Series:
    required = {"trade_date", "ts_code", "value"}
    if not required.issubset(factor.columns):
        raise ValueError(f"factor data must contain columns: {required}")

    frame = factor.loc[:, ["trade_date", "ts_code", "value"]].copy()
    frame["date"] = _parse_trade_dates(frame["trade_date"])
    frame = frame.rename(columns={"ts_code": "asset", "value": "factor"})
    if frame.duplicated(["date", "asset"]).any():
        raise ValueError("factor data contains duplicate date/asset rows")

    result = (
        frame.set_index(["date", "asset"])["factor"]
        .sort_index()
        .rename("factor")
    )
    return result


def build_price_matrix(price_data: pd.DataFrame, return_type: ReturnType) -> pd.DataFrame:
    if return_type == "open_t1":
        value_column = "open"
        shift_rows = -1
    elif return_type == "close_t0":
        value_column = "close"
        shift_rows = 0
    else:
        raise ValueError("return_type must be one of: open_t1, close_t0")

    required = {"trade_date", "ts_code", value_column}
    if not required.issubset(price_data.columns):
        raise ValueError(f"price data must contain columns: {required}")

    frame = price_data.loc[:, ["trade_date", "ts_code", value_column]].copy()
    frame["date"] = _parse_trade_dates(frame["trade_date"])
    matrix = (
        frame.pivot(index="date", columns="ts_code", values=value_column)
        .sort_index()
        .sort_index(axis=1)
    )
    if shift_rows:
        matrix = matrix.shift(shift_rows)
    return matrix


def filter_factor_by_universe(
    factor: pd.Series,
    universe: pd.DataFrame | None,
) -> pd.Series:
    if universe is None:
        return factor

    universe_bool = universe.astype(bool)
    kept = []
    for date, asset in factor.index:
        try:
            kept.append(bool(universe_bool.at[date, asset]))
        except KeyError:
            kept.append(False)
    return factor.loc[kept]


def _parse_trade_dates(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d")
    return pd.to_datetime(values.astype(str), format="%Y%m%d", errors="coerce").fillna(
        pd.to_datetime(values)
    )
```

- [ ] **Step 4: Run adapter tests to verify pass**

Run:

```bash
uv run pytest tests/test_eval_alphalens_adapter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add zer0factor/eval/alphalens_adapter.py tests/test_eval_alphalens_adapter.py
git commit -m "feat: add alphalens input adapters"
```

---

### Task 3: Evaluation Metrics

**Files:**
- Create: `tests/test_eval_metrics.py`
- Create: `zer0factor/eval/metrics.py`

- [ ] **Step 1: Write failing metrics tests**

Create `tests/test_eval_metrics.py`:

```python
import pandas as pd
import pytest

from zer0factor.eval.metrics import build_summary, calculate_long_short_spread


def test_calculate_long_short_spread_uses_highest_minus_lowest_quantile():
    quantile_returns = pd.DataFrame(
        {
            "1D": [0.001, 0.002, 0.004],
            "5D": [0.005, 0.006, 0.009],
        },
        index=pd.Index([1, 2, 3], name="factor_quantile"),
    )

    result = calculate_long_short_spread(quantile_returns)

    assert result["1D"] == pytest.approx(0.003)
    assert result["5D"] == pytest.approx(0.004)


def test_build_summary_has_one_row_per_period_and_required_fields():
    daily_ic = pd.DataFrame(
        {
            "1D": [0.1, 0.2, -0.1, 0.0],
            "5D": [0.2, 0.3, 0.1, -0.2],
        },
        index=pd.date_range("2024-01-01", periods=4),
    )
    quantile_returns = pd.DataFrame(
        {
            "1D": [0.001, 0.004],
            "5D": [0.002, 0.008],
        },
        index=pd.Index([1, 10], name="factor_quantile"),
    )

    result = build_summary(
        factor_name="factor_a",
        return_type="open_t1",
        clean_factor_data_sample_count=100,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-01-31"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert result["period"].tolist() == ["1D", "5D"]
    assert result.loc[0, "factor_name"] == "factor_a"
    assert result.loc[0, "return_type"] == "open_t1"
    assert result.loc[0, "sample_count"] == 100
    assert result.loc[0, "IC Mean"] == pytest.approx(0.05)
    assert result.loc[0, "IC>0 %"] == pytest.approx(50.0)
    assert result.loc[0, "mean_return_q1"] == pytest.approx(0.001)
    assert result.loc[0, "mean_return_qN"] == pytest.approx(0.004)
    assert result.loc[0, "long_short_spread"] == pytest.approx(0.003)
    assert result.loc[0, "long_short_spread_bps"] == pytest.approx(30.0)
```

- [ ] **Step 2: Run metrics tests to verify failure**

Run:

```bash
uv run pytest tests/test_eval_metrics.py -q
```

Expected: FAIL because `zer0factor.eval.metrics` does not exist.

- [ ] **Step 3: Implement metrics helpers**

Create `zer0factor/eval/metrics.py`:

```python
from __future__ import annotations

import alphalens.performance as al_perf
import pandas as pd

from zer0factor.eval.config import ReturnType


def calculate_daily_ic(clean_factor_data: pd.DataFrame) -> pd.DataFrame:
    return al_perf.factor_information_coefficient(clean_factor_data)


def calculate_quantile_returns(clean_factor_data: pd.DataFrame) -> pd.DataFrame:
    mean_returns, _ = al_perf.mean_return_by_quantile(clean_factor_data, by_date=False)
    return mean_returns


def calculate_long_short_spread(quantile_returns: pd.DataFrame) -> pd.Series:
    q_low = quantile_returns.index.min()
    q_high = quantile_returns.index.max()
    return quantile_returns.loc[q_high] - quantile_returns.loc[q_low]


def build_summary(
    *,
    factor_name: str,
    return_type: ReturnType,
    clean_factor_data_sample_count: int,
    clean_factor_data_start: pd.Timestamp,
    clean_factor_data_end: pd.Timestamp,
    quantiles: int,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
) -> pd.DataFrame:
    spread = calculate_long_short_spread(quantile_returns)
    q_low = quantile_returns.index.min()
    q_high = quantile_returns.index.max()
    rows = []

    for period in daily_ic.columns:
        ic = daily_ic[period].dropna()
        ic_mean = ic.mean()
        ic_std = ic.std()
        icir = ic_mean / ic_std if ic_std != 0 else pd.NA
        rows.append(
            {
                "factor_name": factor_name,
                "return_type": return_type,
                "period": str(period),
                "sample_count": clean_factor_data_sample_count,
                "start_date": pd.Timestamp(clean_factor_data_start).strftime("%Y%m%d"),
                "end_date": pd.Timestamp(clean_factor_data_end).strftime("%Y%m%d"),
                "quantiles": quantiles,
                "IC Mean": ic_mean,
                "IC Std": ic_std,
                "ICIR": icir,
                "t-stat": icir * (len(ic) ** 0.5) if icir is not pd.NA else pd.NA,
                "IC>0 %": (ic > 0).mean() * 100,
                "mean_return_q1": quantile_returns.loc[q_low, period],
                "mean_return_qN": quantile_returns.loc[q_high, period],
                "long_short_spread": spread[period],
                "long_short_spread_bps": spread[period] * 10_000,
            }
        )

    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run metrics tests to verify pass**

Run:

```bash
uv run pytest tests/test_eval_metrics.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add zer0factor/eval/metrics.py tests/test_eval_metrics.py
git commit -m "feat: add evaluation metrics"
```

---

### Task 4: Artifact And Plot Writers

**Files:**
- Create: `tests/test_eval_artifacts.py`
- Create: `zer0factor/eval/artifacts.py`
- Create: `zer0factor/eval/plots.py`

- [ ] **Step 1: Write failing artifact tests**

Create `tests/test_eval_artifacts.py`:

```python
import json

import pandas as pd

from zer0factor.eval.artifacts import (
    create_run_directory,
    write_factor_artifacts,
    write_run_summary,
)
from zer0factor.eval.config import EvaluationConfig


def test_create_run_directory_uses_config_output_dir(tmp_path):
    config = EvaluationConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )

    run_id, run_dir = create_run_directory(config, run_id="20240131_120000")

    assert run_id == "20240131_120000"
    assert run_dir == tmp_path / "20240131_120000"
    assert run_dir.exists()


def test_write_factor_artifacts_creates_expected_files(tmp_path):
    clean = pd.DataFrame({"factor": [1.0]})
    daily_ic = pd.DataFrame({"1D": [0.1]}, index=pd.to_datetime(["2024-01-01"]))
    quantile_returns = pd.DataFrame({"1D": [0.001, 0.002]}, index=[1, 2])

    paths = write_factor_artifacts(
        factor_dir=tmp_path / "factors" / "factor_a",
        clean_factor_data=clean,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    assert paths["clean_factor_data"].name == "clean_factor_data.parquet"
    assert paths["daily_ic"].name == "daily_ic.parquet"
    assert paths["quantile_returns"].name == "quantile_returns.parquet"
    assert paths["clean_factor_data"].exists()
    assert paths["daily_ic"].exists()
    assert paths["quantile_returns"].exists()


def test_write_run_summary_creates_summary_and_metadata(tmp_path):
    summary = pd.DataFrame({"factor_name": ["factor_a"], "period": ["1D"]})
    config = EvaluationConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240131",
        output_dir=tmp_path,
    )

    paths = write_run_summary(
        run_dir=tmp_path,
        summary=summary,
        config=config,
        run_id="run_a",
    )

    assert paths["summary_csv"].exists()
    assert paths["summary_parquet"].exists()
    assert paths["metadata"].exists()
    metadata = json.loads(paths["metadata"].read_text())
    assert metadata["run_id"] == "run_a"
    assert metadata["factor_names"] == ["factor_a"]
    assert metadata["return_type"] == "open_t1"
```

- [ ] **Step 2: Run artifact tests to verify failure**

Run:

```bash
uv run pytest tests/test_eval_artifacts.py -q
```

Expected: FAIL because artifact functions do not exist.

- [ ] **Step 3: Implement artifact writers**

Create `zer0factor/eval/artifacts.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from zer0factor.eval.config import EvaluationConfig


def create_run_directory(
    config: EvaluationConfig,
    run_id: str | None = None,
) -> tuple[str, Path]:
    resolved_run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = config.output_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return resolved_run_id, run_dir


def write_factor_artifacts(
    *,
    factor_dir: Path,
    clean_factor_data: pd.DataFrame,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
) -> dict[str, Path]:
    factor_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "clean_factor_data": factor_dir / "clean_factor_data.parquet",
        "daily_ic": factor_dir / "daily_ic.parquet",
        "quantile_returns": factor_dir / "quantile_returns.parquet",
    }
    clean_factor_data.to_parquet(paths["clean_factor_data"])
    daily_ic.to_parquet(paths["daily_ic"])
    quantile_returns.to_parquet(paths["quantile_returns"])
    return paths


def write_run_summary(
    *,
    run_dir: Path,
    summary: pd.DataFrame,
    config: EvaluationConfig,
    run_id: str,
) -> dict[str, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_csv": run_dir / "summary.csv",
        "summary_parquet": run_dir / "summary.parquet",
        "metadata": run_dir / "metadata.json",
    }
    summary.to_csv(paths["summary_csv"], index=False)
    summary.to_parquet(paths["summary_parquet"])
    metadata = {
        "run_id": run_id,
        "factor_names": list(config.factor_names),
        "start_date": config.start_date,
        "end_date": config.end_date,
        "periods": list(config.periods),
        "quantiles": config.quantiles,
        "return_type": config.return_type,
        "max_loss": config.max_loss,
        "universe": config.universe,
        "rolling_ic_window": config.rolling_ic_window,
    }
    paths["metadata"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return paths
```

- [ ] **Step 4: Implement plot writers**

Create `zer0factor/eval/plots.py`:

```python
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def plot_quantile_returns(
    quantile_returns: pd.DataFrame,
    *,
    period: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    values = quantile_returns[period] * 10_000
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#d62728" if value < 0 else "#2ca02c" for value in values]
    ax.bar(values.index.astype(str), values.values, color=colors, width=0.65)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Quantile")
    ax.set_ylabel("Mean Return (bps)")
    ax.set_title(f"Quantile Mean Return - {period}")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_cumulative_ic(daily_ic: pd.DataFrame, *, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    daily_ic.cumsum().plot(ax=ax)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_title("Cumulative IC")
    ax.set_ylabel("Cumulative IC")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_rolling_ic(
    daily_ic: pd.DataFrame,
    *,
    window: int,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    daily_ic.rolling(window).mean().plot(ax=ax)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_title(f"Rolling IC Mean - {window}D")
    ax.set_ylabel("Rolling IC Mean")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
```

- [ ] **Step 5: Run artifact tests to verify pass**

Run:

```bash
uv run pytest tests/test_eval_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add zer0factor/eval/artifacts.py zer0factor/eval/plots.py tests/test_eval_artifacts.py
git commit -m "feat: add evaluation artifact writers"
```

---

### Task 5: Loaders And Pipeline Orchestration

**Files:**
- Create: `tests/test_eval_pipeline.py`
- Create: `zer0factor/eval/loaders.py`
- Create: `zer0factor/eval/pipeline.py`
- Modify: `zer0factor/eval/__init__.py`

- [ ] **Step 1: Write failing pipeline tests with monkeypatched Alphalens**

Create `tests/test_eval_pipeline.py`:

```python
import pandas as pd

from zer0factor.eval import EvaluationConfig, evaluate_factors
from zer0factor.storage import FactorStorage


class FakePro:
    def pro_bar(self, ts_code="", start_date=None, end_date=None, adj=None):
        assert start_date == "20240101"
        assert end_date is not None
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102", "20240103", "20240104"],
                "ts_code": ["000001.SZ"] * 4,
                "open": [10.0, 11.0, 12.0, 13.0],
                "close": [10.5, 11.5, 12.5, 13.5],
            }
        )


def test_evaluate_factors_writes_run_artifacts(tmp_path, monkeypatch):
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
            "1D": [0.01, 0.02],
            "factor_quantile": [1, 2],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )

    def fake_clean_factor_and_forward_returns(*args, **kwargs):
        return clean

    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        fake_clean_factor_and_forward_returns,
    )

    config = EvaluationConfig(
        factor_names=("factor_a",),
        start_date="20240101",
        end_date="20240102",
        periods=(1,),
        quantiles=2,
        output_dir=tmp_path / "evaluations",
    )

    result = evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=FakePro(),
        config=config,
        run_id="run_001",
    )

    assert result.run_id == "run_001"
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert (result.output_dir / "summary.csv").exists()
    assert (result.output_dir / "metadata.json").exists()
    factor_dir = result.output_dir / "factors" / "factor_a"
    assert (factor_dir / "clean_factor_data.parquet").exists()
    assert (factor_dir / "daily_ic.parquet").exists()
    assert (factor_dir / "quantile_returns.parquet").exists()
    assert (factor_dir / "figures" / "quantile_returns_1D.png").exists()
```

- [ ] **Step 2: Run pipeline tests to verify failure**

Run:

```bash
uv run pytest tests/test_eval_pipeline.py -q
```

Expected: FAIL because `evaluate_factors` is not defined.

- [ ] **Step 3: Implement loaders**

Create `zer0factor/eval/loaders.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from zer0factor.storage import FactorStorage


def load_stored_factor(
    storage: FactorStorage,
    factor_name: str,
    *,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    return storage.read(factor_name, start_date=start_date, end_date=end_date)


def load_price_data(
    pro,
    *,
    start_date: str,
    end_date: str | None,
    periods: tuple[int, ...],
) -> pd.DataFrame:
    resolved_end = _extend_end_date(end_date or start_date, periods)
    return pro.pro_bar(
        ts_code="",
        start_date=start_date,
        end_date=resolved_end,
        adj=None,
    )


def load_universe_panel(
    pro,
    *,
    universe_name: str | None,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame | None:
    if universe_name is None:
        return None
    rows = pro.universe(
        universe=universe_name,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,universe,ts_code",
    )
    if rows.empty:
        return pd.DataFrame(dtype=bool)
    frame = rows.loc[:, ["trade_date", "ts_code"]].copy()
    frame["date"] = pd.to_datetime(frame["trade_date"].astype(str), format="%Y%m%d")
    frame["in_universe"] = True
    return (
        frame.drop_duplicates(["date", "ts_code"])
        .pivot(index="date", columns="ts_code", values="in_universe")
        .fillna(False)
        .astype(bool)
        .sort_index()
        .sort_index(axis=1)
    )


def _extend_end_date(end_date: str, periods: tuple[int, ...]) -> str:
    parsed = datetime.strptime(end_date, "%Y%m%d")
    buffer_days = max(periods) + 10
    return (parsed + timedelta(days=buffer_days)).strftime("%Y%m%d")
```

- [ ] **Step 4: Implement pipeline orchestration**

Create `zer0factor/eval/pipeline.py`:

```python
from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence

import pandas as pd
from alphalens.utils import get_clean_factor_and_forward_returns

from zer0factor.eval.alphalens_adapter import (
    build_price_matrix,
    factor_long_to_alphalens_series,
    filter_factor_by_universe,
)
from zer0factor.eval.artifacts import (
    create_run_directory,
    write_factor_artifacts,
    write_run_summary,
)
from zer0factor.eval.config import (
    EvaluationConfig,
    EvaluationRunResult,
    FactorEvaluationResult,
)
from zer0factor.eval.loaders import (
    load_price_data,
    load_stored_factor,
    load_universe_panel,
)
from zer0factor.eval.metrics import (
    build_summary,
    calculate_daily_ic,
    calculate_quantile_returns,
)
from zer0factor.eval.plots import (
    plot_cumulative_ic,
    plot_quantile_returns,
    plot_rolling_ic,
)
from zer0factor.storage import FactorStorage


def evaluate_factor(
    *,
    factor_name: str,
    storage: FactorStorage,
    pro,
    config: EvaluationConfig,
    run_dir: Path,
    price_data: pd.DataFrame | None = None,
    universe_panel: pd.DataFrame | None = None,
) -> FactorEvaluationResult:
    factor_raw = load_stored_factor(
        storage,
        factor_name,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    factor = factor_long_to_alphalens_series(factor_raw)
    factor = filter_factor_by_universe(factor, universe_panel)

    raw_prices = price_data
    if raw_prices is None:
        raw_prices = load_price_data(
            pro,
            start_date=config.start_date,
            end_date=config.end_date,
            periods=config.periods,
        )
    prices = build_price_matrix(raw_prices, config.return_type)

    clean_factor_data = get_clean_factor_and_forward_returns(
        factor,
        prices,
        quantiles=config.quantiles,
        periods=config.periods,
        max_loss=config.max_loss,
    )
    daily_ic = calculate_daily_ic(clean_factor_data)
    quantile_returns = calculate_quantile_returns(clean_factor_data)
    dates = clean_factor_data.index.get_level_values("date")
    summary = build_summary(
        factor_name=factor_name,
        return_type=config.return_type,
        clean_factor_data_sample_count=len(clean_factor_data),
        clean_factor_data_start=dates.min(),
        clean_factor_data_end=dates.max(),
        quantiles=config.quantiles,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )

    factor_dir = run_dir / "factors" / factor_name
    write_factor_artifacts(
        factor_dir=factor_dir,
        clean_factor_data=clean_factor_data,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )
    figure_dir = factor_dir / "figures"
    first_period = str(quantile_returns.columns[0])
    figure_paths = (
        plot_quantile_returns(
            quantile_returns,
            period=first_period,
            output_path=figure_dir / f"quantile_returns_{first_period}.png",
        ),
        plot_cumulative_ic(daily_ic, output_path=figure_dir / "cumulative_ic.png"),
        plot_rolling_ic(
            daily_ic,
            window=config.rolling_ic_window,
            output_path=figure_dir / f"rolling_ic_{config.rolling_ic_window}D.png",
        ),
    )

    return FactorEvaluationResult(
        factor_name=factor_name,
        clean_factor_data=clean_factor_data,
        summary=summary,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        figure_paths=figure_paths,
        output_dir=factor_dir,
    )


def evaluate_factors(
    *,
    factor_names: Sequence[str],
    storage: FactorStorage,
    pro,
    config: EvaluationConfig,
    run_id: str | None = None,
) -> EvaluationRunResult:
    resolved_config = EvaluationConfig(
        factor_names=tuple(factor_names),
        start_date=config.start_date,
        end_date=config.end_date,
        periods=config.periods,
        quantiles=config.quantiles,
        return_type=config.return_type,
        max_loss=config.max_loss,
        universe=config.universe,
        output_dir=config.output_dir,
        rolling_ic_window=config.rolling_ic_window,
    )
    resolved_run_id, run_dir = create_run_directory(resolved_config, run_id=run_id)
    price_data = load_price_data(
        pro,
        start_date=resolved_config.start_date,
        end_date=resolved_config.end_date,
        periods=resolved_config.periods,
    )
    universe_panel = load_universe_panel(
        pro,
        universe_name=resolved_config.universe,
        start_date=resolved_config.start_date,
        end_date=resolved_config.end_date,
    )

    factor_results = tuple(
        evaluate_factor(
            factor_name=factor_name,
            storage=storage,
            pro=pro,
            config=resolved_config,
            run_dir=run_dir,
            price_data=price_data,
            universe_panel=universe_panel,
        )
        for factor_name in resolved_config.factor_names
    )
    combined_summary = pd.concat(
        [result.summary for result in factor_results],
        ignore_index=True,
    )
    run_paths = write_run_summary(
        run_dir=run_dir,
        summary=combined_summary,
        config=resolved_config,
        run_id=resolved_run_id,
    )
    return EvaluationRunResult(
        run_id=resolved_run_id,
        output_dir=run_dir,
        factor_results=factor_results,
        summary=combined_summary,
        metadata_path=run_paths["metadata"],
    )
```

- [ ] **Step 5: Export public API**

Modify `zer0factor/eval/__init__.py`:

```python
from zer0factor.eval.config import (
    EvaluationConfig,
    EvaluationRunResult,
    FactorEvaluationResult,
)
from zer0factor.eval.pipeline import evaluate_factor, evaluate_factors

__all__ = [
    "EvaluationConfig",
    "EvaluationRunResult",
    "FactorEvaluationResult",
    "evaluate_factor",
    "evaluate_factors",
]
```

- [ ] **Step 6: Run pipeline tests to verify pass**

Run:

```bash
uv run pytest tests/test_eval_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add zer0factor/eval/loaders.py zer0factor/eval/pipeline.py zer0factor/eval/__init__.py tests/test_eval_pipeline.py
git commit -m "feat: add factor evaluation pipeline"
```

---

### Task 6: CLI Commands

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing CLI registration tests**

Append to `tests/test_main.py`:

```python
def test_evaluate_factor_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["evaluate-factor", "--help"])

    assert result.exit_code == 0
    assert "Evaluate one stored factor" in result.output
    assert "--periods" in result.output
    assert "--return-type" in result.output


def test_evaluate_factors_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["evaluate-factors", "--help"])

    assert result.exit_code == 0
    assert "Evaluate one or more stored factors" in result.output
    assert "--universe" in result.output
    assert "--output-dir" in result.output
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```bash
uv run pytest tests/test_main.py::test_evaluate_factor_command_is_registered tests/test_main.py::test_evaluate_factors_command_is_registered -q
```

Expected: FAIL because commands are not registered.

- [ ] **Step 3: Add CLI helpers and commands**

Modify `main.py` imports:

```python
from zer0factor.eval import EvaluationConfig, evaluate_factors
```

Add helper near other helpers:

```python
def _parse_periods(value: str) -> tuple[int, ...]:
    try:
        periods = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as exc:
        raise click.BadParameter("periods must be comma-separated integers") from exc
    if not periods or any(period <= 0 for period in periods):
        raise click.BadParameter("periods must be positive integers")
    return periods
```

Add commands before `if __name__ == "__main__":`:

```python
@cli.command("evaluate-factor")
@click.argument("factor_name")
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--periods", default="1,5,10", show_default=True)
@click.option("--quantiles", default=10, show_default=True, type=int)
@click.option(
    "--return-type",
    default="open_t1",
    show_default=True,
    type=click.Choice(["open_t1", "close_t0"]),
)
@click.option("--universe", default=None)
@click.option("--max-loss", default=0.35, show_default=True, type=float)
@click.option("--output-dir", default="data/evaluations", show_default=True)
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
    )


@cli.command("evaluate-factors")
@click.argument("factor_names", nargs=-1, required=True)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--periods", default="1,5,10", show_default=True)
@click.option("--quantiles", default=10, show_default=True, type=int)
@click.option(
    "--return-type",
    default="open_t1",
    show_default=True,
    type=click.Choice(["open_t1", "close_t0"]),
)
@click.option("--universe", default=None)
@click.option("--max-loss", default=0.35, show_default=True, type=float)
@click.option("--output-dir", default="data/evaluations", show_default=True)
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
):
    """Evaluate one or more stored factors."""
    _run_evaluation_command(
        ctx,
        factor_names=tuple(factor_names),
        start_date=start_date,
        end_date=end_date,
        periods=periods,
        quantiles=quantiles,
        return_type=return_type,
        universe=universe,
        max_loss=max_loss,
        output_dir=output_dir,
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
) -> None:
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    config = EvaluationConfig(
        factor_names=factor_names,
        start_date=resolved_start,
        end_date=resolved_end,
        periods=_parse_periods(periods),
        quantiles=quantiles,
        return_type=return_type,
        max_loss=max_loss,
        universe=universe,
        output_dir=Path(output_dir),
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    result = evaluate_factors(
        factor_names=factor_names,
        storage=storage,
        pro=LocalPro(cfg.zer0share_data_dir),
        config=config,
    )
    logger.info(
        "factor_evaluation_finished run_id={} output_dir={} factors={}",
        result.run_id,
        result.output_dir,
        len(result.factor_results),
    )
    click.echo(f"Evaluation run: {result.run_id}")
    click.echo(f"Output: {result.output_dir}")
```

- [ ] **Step 4: Run CLI tests to verify pass**

Run:

```bash
uv run pytest tests/test_main.py::test_evaluate_factor_command_is_registered tests/test_main.py::test_evaluate_factors_command_is_registered -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add main.py tests/test_main.py
git commit -m "feat: add factor evaluation CLI"
```

---

### Task 7: Full Verification And Cleanup

**Files:**
- Inspect: all files changed in Tasks 1-6.

- [ ] **Step 1: Run focused eval tests**

Run:

```bash
uv run pytest tests/test_eval_config.py tests/test_eval_alphalens_adapter.py tests/test_eval_metrics.py tests/test_eval_artifacts.py tests/test_eval_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 2: Run affected existing tests**

Run:

```bash
uv run pytest tests/test_main.py tests/test_storage.py -q
```

Expected: PASS.

- [ ] **Step 3: Run lint on changed modules**

Run:

```bash
uv run ruff check main.py zer0factor/eval tests/test_eval_config.py tests/test_eval_alphalens_adapter.py tests/test_eval_metrics.py tests/test_eval_artifacts.py tests/test_eval_pipeline.py tests/test_main.py
```

Expected: PASS.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git diff --stat
git diff -- zer0factor/eval main.py tests/test_eval_config.py tests/test_eval_alphalens_adapter.py tests/test_eval_metrics.py tests/test_eval_artifacts.py tests/test_eval_pipeline.py tests/test_main.py
```

Expected: Diff only contains the evaluation pipeline, CLI additions, and tests. No notebook or unrelated local files are included.

- [ ] **Step 5: Final commit if verification required fixes**

If Step 1-4 required any fixes, commit them:

```bash
git add zer0factor/eval main.py tests/test_eval_config.py tests/test_eval_alphalens_adapter.py tests/test_eval_metrics.py tests/test_eval_artifacts.py tests/test_eval_pipeline.py tests/test_main.py
git commit -m "fix: polish factor evaluation pipeline"
```

Expected: Either a small fix commit is created, or no commit is needed because prior task commits already pass verification.

---

## Self-Review Notes

Spec coverage:

- Python API and CLI: Tasks 1, 5, and 6.
- Batch stored-factor evaluation: Task 5.
- `FactorStorage` input: Task 5.
- `open_t1` and `close_t0`: Task 2.
- Optional universe filtering: Task 2 and loader boundary in Task 5.
- Machine-readable artifacts: Task 4.
- PNG figures: Task 4 and Task 5.
- Tests: each task starts with focused failing tests and verification commands.

Intentional exclusions remain excluded:

- No index excess returns.
- No turnover metrics.
- No factor-weighted full cross-section portfolio.
- No direction adjustment.
- No report renderer.
- No external CSV/Parquet factor loader.

Placeholder scan:

- No `TBD`, `TODO`, `FIXME`, or unspecified implementation steps.
- Each code-changing step includes concrete code.

Type consistency:

- `EvaluationConfig`, `FactorEvaluationResult`, `EvaluationRunResult`, `evaluate_factor`, and `evaluate_factors` signatures match across tasks.
- `return_type` values are consistently `open_t1` and `close_t0`.
- Artifact paths match the approved spec layout.
