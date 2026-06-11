# OOP Service-Layer Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dismantle the 1005-line `main.py` god module into a layered architecture: thin CLI → application services (with dependency injection) → existing domain modules, eliminating the three duplicated panel-utility implementations along the way.

**Architecture:** `main.py` becomes a 5-line entry point delegating to a `zer0factor/cli/` package. Business orchestration moves into `zer0factor/services/` classes that receive their dependencies (storage, data provider) via constructor injection. An `AppContext` composition root builds those dependencies from config. `typing.Protocol` interfaces decouple services from `zer0share`. The domain layer (`core`, `preprocess`, `eval`, `storage`, `registry`) is untouched except for one deduplication.

**Tech Stack:** Python 3.11, click, pandas, loguru, pytest. No new dependencies.

**Behavior guarantees:** All CLI commands keep identical names, options, and output. Two intentional micro-changes, both invisible to tests: (1) `compute-market-cap` log event names unify with `compute-returns` (e.g. `market_cap_data_load_started` → `market_data_load_started`); (2) default output names now derive via `FactorName`, which handles already-prefixed inputs correctly (`standardize-factor z_x` defaults to `z_x`, not `z_z_x`).

**Verification after every task:** `uv run pytest` must pass (all existing tests, plus the new ones added by the task). Run `uv run ruff check .` before each commit.

---

## Current-state map (what moves where)

| Today (`main.py` lines) | Destination |
|---|---|
| `_parse_trade_dates`, `_factor_long_to_wide`, `_factor_wide_to_long`, `_filter_long_by_universe`, `_filter_panel_by_universe`, `read_universe_panel` (396–470) | `zer0factor/panel.py` (Task 1) |
| `configure_logging`, `LOG_FORMAT` (51, 202–213) | `zer0factor/context.py` (Task 4) |
| `RETURN_FACTORS`, `MARKET_CAP_FACTORS` (32–41) | `zer0factor/factors/builtin.py` (Task 5) |
| `compute_and_store_factors`, `compute_and_store_market_cap_factors` (227–310) | merged into `zer0factor/services/compute.py` (Task 6) |
| `standardize_stored_factor`, `neutralize_stored_factor`, `preprocess_stored_factor`, `standardize_stored_panel`, `_standardized_factor_name`, `MARKET_CAP_PREPROCESS_CONFIG`, `STANDARD_PREPROCESS_CONFIG`, `NEUTRALIZATION_SIZE_FACTOR` (42–50, 313–393) | `zer0factor/services/preprocess.py` (Task 7) |
| `_run_evaluation_command`, `_run_evaluation_job` (661–745) | `zer0factor/services/evaluate.py` + `zer0factor/cli/evaluate_cmds.py` (Tasks 8, 9) |
| All `@cli.command` functions | `zer0factor/cli/` package (Task 9) |

New abstractions: `zer0factor/core/protocols.py` (Task 2), `zer0factor/naming.py` (Task 3), `zer0factor/context.py` (Task 4).

Note: `STANDARD_PREPROCESS_CONFIG` / `MARKET_CAP_PREPROCESS_CONFIG` have exactly the field values of `PreprocessConfig()` (the dataclass defaults). They are replaced by plain `PreprocessConfig()` calls and deleted.

`tests/test_main.py` shrinks in step with `main.py`: each task that removes a function from `main.py` moves its tests to the matching new test file **in the same commit**, so the top-of-file `from main import (...)` block stays valid at every commit.

---

### Task 1: Panel utilities module (`zer0factor/panel.py`)

**Files:**
- Create: `zer0factor/panel.py`
- Create: `tests/test_panel.py`
- Modify: `main.py` (delete lines 396–470, update imports/callers)
- Modify: `zer0factor/preprocess/pipeline.py` (replace private `_parse_trade_dates`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel.py`:

```python
import pandas as pd
import pytest

from zer0factor.panel import (
    filter_long_by_universe,
    filter_panel_by_universe,
    long_to_wide,
    parse_trade_dates,
    read_universe_panel,
    wide_to_long,
)


class FakeUniversePro:
    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        assert universe == "univ_trade_base"
        assert fields == "trade_date,universe,ts_code"
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240101", "20240102"],
                "universe": ["univ_trade_base"] * 3,
                "ts_code": ["000001.SZ", "000003.SZ", "000002.SZ"],
            }
        )


def _long_frame():
    return pd.DataFrame(
        {
            "trade_date": ["20240101", "20240101", "20240102", "20240102"],
            "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )


def test_parse_trade_dates_handles_strings_and_numerics():
    strings = parse_trade_dates(pd.Series(["20240101", "20240102"]))
    numerics = parse_trade_dates(pd.Series([20240101, 20240102]))
    expected = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]))
    pd.testing.assert_series_equal(strings, expected)
    pd.testing.assert_series_equal(numerics, expected)


def test_long_to_wide_pivots_and_sorts():
    wide = long_to_wide(_long_frame())
    assert list(wide.columns) == ["000001.SZ", "000002.SZ"]
    assert wide.index.tolist() == pd.to_datetime(["2024-01-01", "2024-01-02"]).tolist()
    assert wide.loc[pd.Timestamp("2024-01-02"), "000002.SZ"] == 4.0


def test_long_to_wide_rejects_duplicates():
    frame = _long_frame()
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        long_to_wide(duplicated)


def test_wide_to_long_roundtrips():
    long = wide_to_long(long_to_wide(_long_frame()))
    assert list(long.columns) == ["trade_date", "ts_code", "value"]
    pd.testing.assert_frame_equal(long, _long_frame())


def test_filter_panel_by_universe_masks_and_drops_empty_columns():
    panel = long_to_wide(_long_frame())
    universe = pd.DataFrame(
        {"000001.SZ": [True, True], "000002.SZ": [False, False]},
        index=panel.index,
    )
    filtered = filter_panel_by_universe(panel, universe)
    assert list(filtered.columns) == ["000001.SZ"]
    assert filtered["000001.SZ"].tolist() == [1.0, 3.0]


def test_filter_panel_by_universe_none_is_identity():
    panel = long_to_wide(_long_frame())
    pd.testing.assert_frame_equal(filter_panel_by_universe(panel, None), panel)


def test_filter_long_by_universe_masks_rows():
    panel = long_to_wide(_long_frame())
    universe = pd.DataFrame(
        {"000001.SZ": [True, False], "000002.SZ": [True, True]},
        index=panel.index,
    )
    filtered = filter_long_by_universe(_long_frame(), universe)
    assert filtered[["ts_code", "value"]].values.tolist() == [
        ["000001.SZ", 1.0],
        ["000002.SZ", 2.0],
        ["000002.SZ", 4.0],
    ]


def test_read_universe_panel_builds_boolean_panel():
    panel = read_universe_panel(
        FakeUniversePro(),
        universe_name="univ_trade_base",
        start_date="20240101",
        end_date="20240102",
    )
    assert panel.dtypes.unique().tolist() == [bool]
    assert panel.loc[pd.Timestamp("2024-01-01"), "000001.SZ"]
    assert not panel.loc[pd.Timestamp("2024-01-02"), "000001.SZ"]
    assert panel.loc[pd.Timestamp("2024-01-02"), "000002.SZ"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zer0factor.panel'`

- [ ] **Step 3: Implement `zer0factor/panel.py`**

The function bodies are verbatim moves from `main.py:396-470` (drop the leading underscores):

```python
"""Long/wide factor panel transformations shared across services and CLI."""

from __future__ import annotations

import pandas as pd

from zer0factor.core import to_factor_output

LONG_COLUMNS = ("trade_date", "ts_code", "value")


def parse_trade_dates(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d")
    return pd.to_datetime(values)


def long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.loc[:, list(LONG_COLUMNS)].copy()
    frame["trade_date"] = parse_trade_dates(frame["trade_date"])
    if frame.duplicated(["trade_date", "ts_code"]).any():
        raise ValueError("factor data contains duplicate trade_date/ts_code")
    return (
        frame.pivot(index="trade_date", columns="ts_code", values="value")
        .sort_index()
        .sort_index(axis=1)
    )


def wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    return to_factor_output(df)


def filter_panel_by_universe(
    panel: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return panel
    aligned = universe.reindex(index=panel.index, columns=panel.columns, fill_value=False)
    aligned = aligned.astype(bool)
    return panel.where(aligned).dropna(axis=1, how="all")


def filter_long_by_universe(
    factor: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return factor
    return wide_to_long(filter_panel_by_universe(long_to_wide(factor), universe))


def read_universe_panel(
    pro,
    *,
    universe_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    rows = pro.universe(
        universe=universe_name,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,universe,ts_code",
    )
    if rows.empty:
        return pd.DataFrame(dtype=bool)

    frame = rows.loc[:, ["trade_date", "ts_code"]].copy()
    frame["trade_date"] = parse_trade_dates(frame["trade_date"])
    frame["in_universe"] = True
    return (
        frame.drop_duplicates(["trade_date", "ts_code"])
        .pivot(index="trade_date", columns="ts_code", values="in_universe")
        .pipe(lambda df: df.where(df.notna(), False))
        .astype(bool)
        .sort_index()
        .sort_index(axis=1)
    )
```

Note `wide_to_long` is `to_factor_output` — `main.py:464-470`'s `_factor_wide_to_long` was a byte-for-byte duplicate of the DataFrame branch of `to_factor_output` in `zer0factor/core/__init__.py:102`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_panel.py -v`
Expected: 8 PASS

- [ ] **Step 5: Rewire `main.py` to the new module**

In `main.py`:
1. Add import: `from zer0factor.panel import filter_long_by_universe, filter_panel_by_universe, long_to_wide, parse_trade_dates, read_universe_panel, wide_to_long`
2. Delete `read_universe_panel`, `_filter_long_by_universe`, `_filter_panel_by_universe`, `_factor_long_to_wide`, `_parse_trade_dates`, `_factor_wide_to_long` (lines 396–470).
3. Update callers inside `main.py`: `_factor_long_to_wide` → `long_to_wide`, `_factor_wide_to_long` → `wide_to_long`, `_filter_long_by_universe` → `filter_long_by_universe`, `_filter_panel_by_universe` → `filter_panel_by_universe` (occurrences in `neutralize_stored_factor` and `standardize_stored_factor`).

- [ ] **Step 6: Dedupe `zer0factor/preprocess/pipeline.py`**

Delete its private `_parse_trade_dates` (lines 127–130), add `from zer0factor.panel import parse_trade_dates`, and rename the two call sites in `_to_wide` from `_parse_trade_dates` to `parse_trade_dates`. (No import cycle: `panel` imports `zer0factor.core` only.)

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest`
Expected: all PASS (test_main.py still imports `read_universe_panel` from `main`; it remains re-exported via the new import in step 5)

- [ ] **Step 8: Commit**

```bash
git add zer0factor/panel.py tests/test_panel.py main.py zer0factor/preprocess/pipeline.py
git commit -m "refactor: extract shared panel utilities into zer0factor.panel"
```

---

### Task 2: Data-source protocols (`zer0factor/core/protocols.py`)

**Files:**
- Create: `zer0factor/core/protocols.py`
- Create: `tests/test_protocols.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocols.py`:

```python
from zer0factor.core import Zer0ShareDataProvider
from zer0factor.core.protocols import DataProvider, IndustrySource, UniverseSource


class _FakePro:
    def universe(self, *, universe=None, start_date=None, end_date=None, fields=None):
        raise NotImplementedError

    def index_member_all(self, fields=None):
        raise NotImplementedError


def test_zer0share_provider_satisfies_data_provider():
    assert isinstance(Zer0ShareDataProvider(pro=None), DataProvider)


def test_fake_pro_satisfies_source_protocols():
    assert isinstance(_FakePro(), UniverseSource)
    assert isinstance(_FakePro(), IndustrySource)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zer0factor.core.protocols'`

- [ ] **Step 3: Implement `zer0factor/core/protocols.py`**

```python
"""Structural interfaces for external data sources (dependency inversion)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import pandas as pd

if TYPE_CHECKING:
    from zer0factor.core import FactorFrame


@runtime_checkable
class DataProvider(Protocol):
    """Loads standardized field panels for factor computation."""

    def history(
        self,
        fields: Iterable[str],
        start_date: str,
        end_date: str | None,
        universe: str | Iterable[str] = "all",
        adjust: str | None = "hfq",
        progress: Callable[[int, int, str], None] | None = None,
    ) -> "FactorFrame": ...


@runtime_checkable
class UniverseSource(Protocol):
    """Yields universe membership rows (trade_date, universe, ts_code)."""

    def universe(
        self,
        *,
        universe: str,
        start_date: str | None,
        end_date: str | None,
        fields: str,
    ) -> pd.DataFrame: ...


@runtime_checkable
class IndustrySource(Protocol):
    """Yields industry membership rows for exposure construction."""

    def index_member_all(self, fields: str) -> pd.DataFrame: ...
```

(`zer0factor/core/__init__.py` is NOT modified — `protocols` is a submodule of the existing `core` package directory.)

- [ ] **Step 4: Run tests, type the existing seams**

Run: `uv run pytest tests/test_protocols.py -v` — expected: 2 PASS.

Then annotate `zer0factor/panel.py`'s `read_universe_panel` first parameter: `pro: UniverseSource` (add `from zer0factor.core.protocols import UniverseSource`), and `zer0factor/exposures.py`'s `build_sw_l1_industry_panel` first parameter: `pro: IndustrySource` (same import). Run `uv run pytest` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add zer0factor/core/protocols.py tests/test_protocols.py zer0factor/panel.py zer0factor/exposures.py
git commit -m "refactor: add DataProvider/UniverseSource/IndustrySource protocols"
```

---

### Task 3: Factor naming value object (`zer0factor/naming.py`)

**Files:**
- Create: `zer0factor/naming.py`
- Create: `tests/test_naming.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_naming.py`:

```python
import pytest

from zer0factor.naming import FactorName


@pytest.mark.parametrize(
    "name,raw",
    [
        ("ret20", "ret20"),
        ("z_ret20", "ret20"),
        ("z_neu_ret20", "ret20"),
    ],
)
def test_parse_strips_known_prefixes(name, raw):
    assert FactorName.parse(name).raw == raw


def test_derived_names():
    name = FactorName.parse("z_ret20")
    assert name.standardized == "z_ret20"
    assert name.neutralized == "z_neu_ret20"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zer0factor.naming'`

- [ ] **Step 3: Implement `zer0factor/naming.py`**

```python
"""Naming policy for derived factors (z-scored, neutralized variants)."""

from __future__ import annotations

from dataclasses import dataclass

STANDARDIZED_PREFIX = "z_"
NEUTRALIZED_PREFIX = "z_neu_"


@dataclass(frozen=True)
class FactorName:
    raw: str

    @classmethod
    def parse(cls, name: str) -> "FactorName":
        if name.startswith(NEUTRALIZED_PREFIX):
            return cls(name[len(NEUTRALIZED_PREFIX):])
        if name.startswith(STANDARDIZED_PREFIX):
            return cls(name[len(STANDARDIZED_PREFIX):])
        return cls(name)

    @property
    def standardized(self) -> str:
        return f"{STANDARDIZED_PREFIX}{self.raw}"

    @property
    def neutralized(self) -> str:
        return f"{NEUTRALIZED_PREFIX}{self.raw}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_naming.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add zer0factor/naming.py tests/test_naming.py
git commit -m "refactor: add FactorName value object for derived-factor naming"
```

---

### Task 4: Composition root (`zer0factor/context.py`)

**Files:**
- Create: `zer0factor/context.py`
- Create: `tests/test_context.py`
- Modify: `main.py` (delete `configure_logging` + `LOG_FORMAT`, use `AppContext`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context.py`:

```python
from pathlib import Path

from zer0factor.context import AppContext
from zer0factor.storage import FactorStorage


def _write_settings(tmp_path: Path) -> Path:
    settings = tmp_path / "settings.toml"
    settings.write_text(
        f"""
[zer0share]
data_dir = "{(tmp_path / 'data').as_posix()}"

[paths]
factor_dir = "{(tmp_path / 'factors').as_posix()}"
db_path = "{(tmp_path / 'factor.duckdb').as_posix()}"
log_path = "{(tmp_path / 'logs' / 'app.log').as_posix()}"

[factor]
universe = "all"
start_date = "20240101"
end_date = ""
""",
        encoding="utf-8",
    )
    return settings


def test_from_config_path_loads_config(tmp_path):
    app = AppContext.from_config_path(_write_settings(tmp_path))
    assert app.config.universe == "all"
    assert app.config.start_date == "20240101"


def test_storage_is_built_lazily_and_cached(tmp_path):
    app = AppContext.from_config_path(_write_settings(tmp_path))
    storage = app.storage
    assert isinstance(storage, FactorStorage)
    assert app.storage is storage


def test_configure_logging_creates_log_dir(tmp_path):
    app = AppContext.from_config_path(_write_settings(tmp_path))
    app.configure_logging()
    assert (tmp_path / "logs").is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zer0factor.context'`

- [ ] **Step 3: Implement `zer0factor/context.py`**

`configure_logging` body is a verbatim move from `main.py:202-213`; `pro`/`provider` keep the lazy `zer0share` import that commands use today:

```python
"""Composition root: builds and caches application dependencies from config."""

from __future__ import annotations

import sys
from functools import cached_property
from pathlib import Path

from loguru import logger

from zer0factor.config import Config, load_config
from zer0factor.storage import FactorStorage

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}"


class AppContext:
    def __init__(self, config: Config) -> None:
        self.config = config

    @classmethod
    def from_config_path(cls, path: Path) -> "AppContext":
        return cls(load_config(Path(path)))

    @cached_property
    def storage(self) -> FactorStorage:
        return FactorStorage(self.config.factor_dir, self.config.db_path)

    @cached_property
    def pro(self):
        from zer0share.api import LocalPro

        return LocalPro(self.config.zer0share_data_dir)

    @cached_property
    def provider(self):
        from zer0factor.core import Zer0ShareDataProvider

        return Zer0ShareDataProvider(self.pro)

    def configure_logging(self) -> None:
        log_path = self.config.log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.remove()
        logger.add(sys.stderr, level="INFO", format=LOG_FORMAT)
        logger.add(
            log_path,
            level="INFO",
            format=LOG_FORMAT,
            rotation="100 MB",
            retention=10,
            enqueue=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_context.py -v`
Expected: 3 PASS

- [ ] **Step 5: Adopt `AppContext` in `main.py`**

In every command that currently does `cfg = load_config(ctx.obj["config_path"])`, replace the boilerplate:

```python
# before
cfg = load_config(ctx.obj["config_path"])
configure_logging(cfg.log_path)
storage = FactorStorage(cfg.factor_dir, cfg.db_path)
pro = LocalPro(cfg.zer0share_data_dir)            # where present
provider = Zer0ShareDataProvider(LocalPro(...))   # where present

# after
app = AppContext.from_config_path(ctx.obj["config_path"])
app.configure_logging()        # only in commands that configured logging before
cfg = app.config               # keep local alias; bodies read cfg.start_date etc.
storage = app.storage
pro = app.pro                  # where present
provider = app.provider        # where present
```

Affected commands: `status`, `factor_list_command`, `factor_info_command`, `compute_returns`, `compute_market_cap`, `standardize_factor`, `neutralize_factor`, `_run_evaluation_job`. Delete `configure_logging`, `LOG_FORMAT`, the now-unused `import sys`, the `from loguru import logger` stays (commands still log). Delete the `from zer0share.api import LocalPro` lines inside command bodies and the `Zer0ShareDataProvider` import if no longer referenced.

The `cli` group callback is unchanged — it keeps storing only `config_path` so that `--help` works without a config file.

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest` — all PASS.

```bash
git add zer0factor/context.py tests/test_context.py main.py
git commit -m "refactor: add AppContext composition root, remove per-command wiring"
```

---

### Task 5: Built-in factor groups (`zer0factor/factors/builtin.py`)

**Files:**
- Create: `zer0factor/factors/builtin.py`
- Modify: `main.py` (replace tuple definitions with import)
- Modify: `tests/test_main.py` (import from new location)

- [ ] **Step 1: Implement `zer0factor/factors/builtin.py`**

```python
"""Built-in factor instances grouped for batch computation."""

from zer0factor.factors.market_cap import LogCirculatingMarketCap, LogTotalMarketCap
from zer0factor.factors.returns import (
    DailyReturn,
    IntradayReturn,
    OpenReturn,
    OvernightReturn,
)

RETURN_FACTORS = (
    DailyReturn(),
    OpenReturn(),
    IntradayReturn(),
    OvernightReturn(),
)
MARKET_CAP_FACTORS = (
    LogTotalMarketCap(),
    LogCirculatingMarketCap(),
)

FACTOR_GROUPS = {
    "returns": RETURN_FACTORS,
    "market_cap": MARKET_CAP_FACTORS,
}
```

- [ ] **Step 2: Rewire callers**

In `main.py`: delete the `RETURN_FACTORS` / `MARKET_CAP_FACTORS` definitions (lines 32–41) and add `from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS`.

In `tests/test_main.py`: remove `MARKET_CAP_FACTORS, RETURN_FACTORS` from the `from main import (...)` block and add `from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS`.

- [ ] **Step 3: Run the full suite and commit**

Run: `uv run pytest` — all PASS.

```bash
git add zer0factor/factors/builtin.py main.py tests/test_main.py
git commit -m "refactor: move built-in factor groups into zer0factor.factors.builtin"
```

---

### Task 6: Compute service (`zer0factor/services/compute.py`)

Merges `compute_and_store_factors` and `compute_and_store_market_cap_factors` — they differ only in (a) `adjust` (now derived from `FactorSpec.adjust`, which is already `None` for market-cap factors and `"hfq"` for return factors) and (b) the z-score side-write (now a `ZScorePostProcess` strategy).

**Files:**
- Create: `zer0factor/services/__init__.py`
- Create: `zer0factor/services/compute.py`
- Create: `tests/test_services_compute.py`
- Modify: `main.py` (commands call the service; old functions deleted)
- Modify: `tests/test_main.py` (move the two compute tests + their fakes out)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_services_compute.py`. `FakeProvider` / `FakeMarketCapProvider` are verbatim moves from `tests/test_main.py:22-56`; the two tests are ports of `tests/test_main.py:72-126` onto the service API:

```python
import pandas as pd

from zer0factor.core import FactorFrame
from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS
from zer0factor.services.compute import FactorComputeService, ZScorePostProcess
from zer0factor.storage import FactorStorage


class FakeProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["close", "open"]
        assert start_date == "20240101"
        assert end_date == "20240103"
        assert universe == "000001.SZ"
        assert adjust == "hfq"
        if progress is not None:
            progress(0, 1, "")
            progress(1, 1, "000001.SZ")

        index = pd.date_range("2024-01-01", periods=3, freq="D")
        open_ = pd.DataFrame({"000001.SZ": [10.0, 11.0, 12.0]}, index=index)
        close = pd.DataFrame({"000001.SZ": [10.5, 12.0, 12.6]}, index=index)
        return FactorFrame({"open": open_, "close": close})


class FakeMarketCapProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["circ_mv", "total_mv"]
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert universe == "000001.SZ,000002.SZ"
        assert adjust is None

        index = pd.date_range("2024-01-01", periods=2, freq="D")
        total_mv = pd.DataFrame(
            {"000001.SZ": [100.0, 110.0], "000002.SZ": [200.0, 220.0]},
            index=index,
        )
        circ_mv = pd.DataFrame(
            {"000001.SZ": [50.0, 55.0], "000002.SZ": [80.0, 88.0]},
            index=index,
        )
        return FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})


def test_compute_and_store_return_factors(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    service = FactorComputeService(provider=FakeProvider(), storage=storage)

    row_counts = service.compute_and_store(
        RETURN_FACTORS,
        start_date="20240101",
        end_date="20240103",
        universe="000001.SZ",
    )

    assert row_counts == {
        "daily_return": 2,
        "open_return": 2,
        "intraday_return": 3,
        "overnight_return": 2,
    }
    assert storage.list_factors() == [
        "daily_return",
        "intraday_return",
        "open_return",
        "overnight_return",
    ]


def test_compute_and_store_market_cap_factors_writes_raw_and_zscored(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    service = FactorComputeService(provider=FakeMarketCapProvider(), storage=storage)

    row_counts = service.compute_and_store(
        MARKET_CAP_FACTORS,
        start_date="20240101",
        end_date="20240102",
        universe="000001.SZ,000002.SZ",
        postprocess=ZScorePostProcess(storage),
    )

    assert row_counts == {
        "log_total_market_cap": 4,
        "log_circulating_market_cap": 4,
        "z_log_total_market_cap": 4,
        "z_log_circulating_market_cap": 4,
    }
    assert sorted(storage.list_factors()) == [
        "log_circulating_market_cap",
        "log_total_market_cap",
        "z_log_circulating_market_cap",
        "z_log_total_market_cap",
    ]

    z_total = storage.read("z_log_total_market_cap")
    assert sorted(z_total["trade_date"].astype(str).unique()) == ["20240101", "20240102"]
    assert z_total.groupby("trade_date")["value"].mean().abs().max() < 1e-12
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services_compute.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zer0factor.services'`

- [ ] **Step 3: Implement the service**

Create empty `zer0factor/services/__init__.py` (docstring only: `"""Application services orchestrating domain modules."""`).

Create `zer0factor/services/compute.py`:

```python
"""Compute factors from a data provider and persist them."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from zer0factor.core import Factor, run_factor
from zer0factor.core.protocols import DataProvider
from zer0factor.naming import FactorName
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.storage import FactorStorage

ProgressFn = Callable[[int, int, str], None]
LogFn = Callable[[str], None]
PostProcessFn = Callable[[str, pd.DataFrame], dict[str, int]]


class ZScorePostProcess:
    """Post-compute strategy: store a z-scored variant alongside the raw factor."""

    def __init__(
        self,
        storage: FactorStorage,
        config: PreprocessConfig | None = None,
    ) -> None:
        self._storage = storage
        self._pipeline = FactorPreprocessPipeline(config or PreprocessConfig())

    def __call__(self, factor_name: str, raw: pd.DataFrame) -> dict[str, int]:
        z_name = FactorName.parse(factor_name).standardized
        z_scored = self._pipeline.transform(raw)
        self._storage.write(z_name, z_scored)
        return {z_name: len(z_scored)}


class FactorComputeService:
    def __init__(
        self,
        provider: DataProvider,
        storage: FactorStorage,
        *,
        log_info: LogFn | None = None,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._log: LogFn = log_info or (lambda message: None)

    def compute_and_store(
        self,
        factors: tuple[Factor, ...],
        *,
        start_date: str,
        end_date: str | None,
        universe: str,
        progress: ProgressFn | None = None,
        postprocess: PostProcessFn | None = None,
    ) -> dict[str, int]:
        fields = sorted({field for factor in factors for field in factor.spec.inputs})
        adjust_values = {factor.spec.adjust for factor in factors}
        if len(adjust_values) != 1:
            raise ValueError("factors with mixed adjust settings cannot share one data load")

        self._log(f"market_data_load_started fields={','.join(fields)}")
        data = self._provider.history(
            fields=fields,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            adjust=adjust_values.pop(),
            progress=progress,
        )
        self._log("market_data_load_finished")
        self._log("factor_write_stage_started")

        row_counts: dict[str, int] = {}
        for factor in factors:
            name = factor.spec.name
            self._log(f"factor_write_started factor={name}")
            result = run_factor(factor, data, storage=self._storage)
            row_counts[name] = len(result)
            self._log(f"factor_write_finished factor={name} rows={len(result)}")
            if postprocess is not None:
                row_counts.update(postprocess(name, result))
        return row_counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services_compute.py -v`
Expected: 2 PASS

- [ ] **Step 5: Rewire `main.py`, delete old functions and tests**

In `main.py`:
1. Delete `compute_and_store_factors` and `compute_and_store_market_cap_factors` (lines 227–310). Delete `MARKET_CAP_PREPROCESS_CONFIG` and rebind its alias (still referenced by `standardize_stored_factor` until Task 7) to the equivalent defaults: `STANDARD_PREPROCESS_CONFIG = PreprocessConfig()`.
2. Add `from zer0factor.services.compute import FactorComputeService, ZScorePostProcess`.
3. In `compute_returns`, replace the `compute_and_store_factors(...)` call:

```python
    service = FactorComputeService(app.provider, app.storage, log_info=logger.info)
    row_counts = service.compute_and_store(
        RETURN_FACTORS,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
    )
```

4. In `compute_market_cap`, replace the `compute_and_store_market_cap_factors(...)` call:

```python
    service = FactorComputeService(app.provider, app.storage, log_info=logger.info)
    row_counts = service.compute_and_store(
        MARKET_CAP_FACTORS,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        postprocess=ZScorePostProcess(app.storage),
    )
```

In `tests/test_main.py`: delete `FakeProvider`, `FakeMarketCapProvider`, `test_compute_and_store_return_factors`, `test_compute_and_store_market_cap_factors_writes_raw_and_zscored`, and remove `compute_and_store_factors`, `compute_and_store_market_cap_factors`, `MARKET_CAP_FACTORS`, `RETURN_FACTORS` imports (keep the `zer0factor.factors.builtin` import only if still referenced elsewhere in the file; if not, delete it).

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest` — all PASS.

```bash
git add zer0factor/services/ tests/test_services_compute.py main.py tests/test_main.py
git commit -m "refactor: merge factor computation into FactorComputeService"
```

---

### Task 7: Preprocess service (`zer0factor/services/preprocess.py`)

**Files:**
- Create: `zer0factor/services/preprocess.py`
- Create: `tests/test_services_preprocess.py`
- Modify: `main.py`, `tests/test_main.py`

- [ ] **Step 1: Check external references to the alias**

Run: `uv run python -c "import subprocess; print(subprocess.run(['git','grep','-n','preprocess_stored_factor','--','*.py','*.md'],capture_output=True,text=True).stdout)"`

If `preprocess_stored_factor` appears only in `main.py` and `tests/test_main.py`, delete it and its alias test outright in step 5. If docs/skills reference it, keep a one-line deprecated alias in the new module: `def preprocess_stored_factor(**kwargs): ...` delegating to the service, and keep the alias test pointed at it.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_services_preprocess.py`. `FakeUniversePro` is the same fake as in `tests/test_panel.py`; `FakeIndustryNeutralizationPro` is a verbatim move from `tests/test_main.py:536` onward. The first two tests below are ports of `tests/test_main.py:449-510`; additionally move `test_neutralize_stored_factor_reads_z_factor_and_writes_standardized_neutral_factor` (line 565) and `test_neutralize_stored_factor_filters_by_process_universe` (line 640) verbatim, changing only the call sites as shown at the bottom.

```python
import pandas as pd
import pytest

from zer0factor.panel import read_universe_panel
from zer0factor.services.preprocess import FactorPreprocessService
from zer0factor.storage import FactorStorage


class FakeUniversePro:
    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        assert universe == "univ_trade_base"
        assert fields == "trade_date,universe,ts_code"
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240101", "20240102"],
                "universe": ["univ_trade_base"] * 3,
                "ts_code": ["000001.SZ", "000003.SZ", "000002.SZ"],
            }
        )


def test_standardize_writes_z_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "daily_return",
        pd.DataFrame(
            {
                "trade_date": ["20240101"] * 4,
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
                "value": [1.0, 2.0, None, 100.0],
            }
        ),
    )
    service = FactorPreprocessService(storage)

    rows = service.standardize(
        "daily_return",
        start_date="20240101",
        end_date="20240101",
    )

    result = storage.read("z_daily_return")
    assert rows == 4
    assert len(result) == 4
    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert "z_daily_return" in storage.list_factors()
    values = result.sort_values("ts_code")["value"]
    assert values.isna().sum() == 0
    assert values.mean() == pytest.approx(0.0)
    assert values.std() == pytest.approx(1.0)


def test_standardize_filters_by_process_universe(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "daily_return",
        pd.DataFrame(
            {
                "trade_date": ["20240101"] * 4,
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
                "value": [1.0, 2.0, 3.0, 100.0],
            }
        ),
    )
    service = FactorPreprocessService(storage)

    rows = service.standardize(
        "daily_return",
        start_date="20240101",
        end_date="20240101",
        universe=read_universe_panel(
            FakeUniversePro(),
            universe_name="univ_trade_base",
            start_date="20240101",
            end_date="20240101",
        ),
    )

    result = storage.read("z_daily_return")
    assert rows == 2
    assert result["ts_code"].tolist() == ["000001.SZ", "000003.SZ"]
    assert result["value"].mean() == pytest.approx(0.0)
    assert result["value"].std() == pytest.approx(1.0)
```

Call-site replacement for the two moved neutralization tests:

```python
# before (in test_main.py)
rows = neutralize_stored_factor(
    factor_name=...,
    output_name=...,
    storage=storage,
    pro=FakeIndustryNeutralizationPro(),
    ...,
)

# after (in test_services_preprocess.py)
service = FactorPreprocessService(storage, industry_source=FakeIndustryNeutralizationPro())
rows = service.neutralize(
    <factor_name>,
    output_name=...,
    ...,
)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_services_preprocess.py -v`
Expected: FAIL — `ImportError` (module does not exist)

- [ ] **Step 4: Implement `zer0factor/services/preprocess.py`**

Bodies are moves of `standardize_stored_factor` / `neutralize_stored_factor` from `main.py:313-371` with `FactorName` replacing string surgery and `PreprocessConfig()` replacing `STANDARD_PREPROCESS_CONFIG`:

```python
"""Standardize and neutralize stored factors."""

from __future__ import annotations

import pandas as pd

from zer0factor.core.protocols import IndustrySource
from zer0factor.exposures import build_sw_l1_industry_panel
from zer0factor.naming import FactorName
from zer0factor.panel import (
    filter_long_by_universe,
    filter_panel_by_universe,
    long_to_wide,
    wide_to_long,
)
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.storage import FactorStorage

NEUTRALIZATION_SIZE_FACTOR = "z_log_circulating_market_cap"

_NEUTRALIZE_ONLY = PreprocessConfig(
    winsorize_method="none",
    impute_method="none",
    standardize_method="none",
    neutralize_method="size_industry",
)
_ZSCORE_ONLY = PreprocessConfig(
    winsorize_method="none",
    impute_method="none",
    standardize_method="zscore",
    neutralize_method=None,
)


class FactorPreprocessService:
    def __init__(
        self,
        storage: FactorStorage,
        industry_source: IndustrySource | None = None,
    ) -> None:
        self._storage = storage
        self._industry_source = industry_source

    def standardize(
        self,
        factor_name: str,
        *,
        output_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        config: PreprocessConfig | None = None,
        universe: pd.DataFrame | None = None,
    ) -> int:
        resolved_output = output_name or FactorName.parse(factor_name).standardized
        source = self._storage.read(factor_name, start_date=start_date, end_date=end_date)
        source = filter_long_by_universe(source, universe)
        pipeline = FactorPreprocessPipeline(config or PreprocessConfig())
        output = pipeline.transform(source)
        self._storage.write(resolved_output, output)
        return len(output)

    def neutralize(
        self,
        factor_name: str,
        *,
        output_name: str | None = None,
        size_factor_name: str = NEUTRALIZATION_SIZE_FACTOR,
        start_date: str | None = None,
        end_date: str | None = None,
        universe: pd.DataFrame | None = None,
    ) -> int:
        if self._industry_source is None:
            raise ValueError("neutralize requires an industry_source")

        name = FactorName.parse(factor_name)
        resolved_output = output_name or name.neutralized
        source = self._storage.read(
            name.standardized, start_date=start_date, end_date=end_date
        )
        size = self._storage.read(
            size_factor_name, start_date=start_date, end_date=end_date
        )
        source_panel = long_to_wide(source)
        size_panel = long_to_wide(size)
        dates = source_panel.index.intersection(size_panel.index)
        ts_codes = source_panel.columns.intersection(size_panel.columns)
        source_panel = source_panel.reindex(index=dates, columns=ts_codes)
        size_panel = size_panel.reindex(index=dates, columns=ts_codes)
        source_panel = filter_panel_by_universe(source_panel, universe)
        size_panel = size_panel.reindex(
            index=source_panel.index, columns=source_panel.columns
        )
        industry_panel = build_sw_l1_industry_panel(
            self._industry_source, dates=dates, ts_codes=ts_codes
        )
        industry_panel = industry_panel.reindex(
            index=source_panel.index, columns=source_panel.columns
        )

        residual = FactorPreprocessPipeline(_NEUTRALIZE_ONLY).transform(
            source_panel,
            exposures={"size": size_panel, "industry": industry_panel},
        )
        standardized = FactorPreprocessPipeline(_ZSCORE_ONLY).transform(residual)
        output = wide_to_long(standardized)
        self._storage.write(resolved_output, output)
        return len(output)
```

- [ ] **Step 5: Run new tests, rewire `main.py`, delete old functions and tests**

Run: `uv run pytest tests/test_services_preprocess.py -v` — all PASS.

In `main.py`:
1. Delete `standardize_stored_factor`, `neutralize_stored_factor`, `preprocess_stored_factor`, `standardize_stored_panel`, `_standardized_factor_name`, `STANDARD_PREPROCESS_CONFIG`, `NEUTRALIZATION_SIZE_FACTOR` (per step-1 grep result).
2. Add `from zer0factor.services.preprocess import NEUTRALIZATION_SIZE_FACTOR, FactorPreprocessService` and `from zer0factor.naming import FactorName`.
3. `standardize_factor` command body: `resolved_output = output_name or FactorName.parse(factor_name).standardized`, then

```python
    service = FactorPreprocessService(app.storage)
    rows = service.standardize(
        factor_name,
        output_name=resolved_output,
        start_date=resolved_start,
        end_date=resolved_end,
        universe=universe,
    )
```

4. `neutralize_factor` command body: `resolved_output = output_name or FactorName.parse(factor_name).neutralized` (replaces the `factor_name[2:]` logic), the log line's `source=` field uses `FactorName.parse(factor_name).standardized`, then

```python
    service = FactorPreprocessService(app.storage, industry_source=app.pro)
    rows = service.neutralize(
        factor_name,
        output_name=resolved_output,
        size_factor_name=size_factor_name,
        start_date=resolved_start,
        end_date=resolved_end,
        universe=universe,
    )
```

In `tests/test_main.py`: delete the moved tests (`test_standardize_stored_factor_writes_z_factor`, `test_standardize_stored_factor_filters_by_process_universe`, `test_preprocess_stored_factor_alias_matches_standardize_stored_factor`, both `test_neutralize_stored_factor_*`), `FakeUniversePro`, `FakeIndustryNeutralizationPro`, and the corresponding names from the `from main import (...)` block (`neutralize_stored_factor`, `preprocess_stored_factor`, `read_universe_panel`, `standardize_stored_factor`).

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest` — all PASS.

```bash
git add zer0factor/services/preprocess.py tests/test_services_preprocess.py main.py tests/test_main.py
git commit -m "refactor: extract FactorPreprocessService for standardize/neutralize"
```

---

### Task 8: Evaluation service (`zer0factor/services/evaluate.py`)

**Files:**
- Create: `zer0factor/services/evaluate.py`
- Modify: `main.py` (`_run_evaluation_job` shrinks to config-building + service call)

- [ ] **Step 1: Implement `zer0factor/services/evaluate.py`**

A facade so the CLI no longer reaches into `eval` internals with loose deps (it is exercised end-to-end by the existing `test_evaluate_*` CLI tests, which monkeypatch `LocalPro`):

```python
"""Run factor evaluations against stored factors."""

from __future__ import annotations

from collections.abc import Callable

from zer0factor.eval import EvaluationConfig, EvaluationRunResult, evaluate_factors
from zer0factor.storage import FactorStorage

LogFn = Callable[[str], None]


class EvaluationService:
    def __init__(
        self,
        storage: FactorStorage,
        pro,
        *,
        log_info: LogFn | None = None,
    ) -> None:
        self._storage = storage
        self._pro = pro
        self._log: LogFn = log_info or (lambda message: None)

    def run(self, config: EvaluationConfig) -> EvaluationRunResult:
        return evaluate_factors(
            factor_names=config.factor_names,
            storage=self._storage,
            pro=self._pro,
            config=config,
            log_info=self._log,
        )
```

- [ ] **Step 2: Rewire `main.py`**

In `_run_evaluation_job` (main.py:693), replace the storage/pro construction and `evaluate_factors(...)` call:

```python
    app = AppContext.from_config_path(ctx.obj["config_path"])
    app.configure_logging()
    cfg = app.config
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

    service = EvaluationService(app.storage, app.pro, log_info=log_progress)
    result = service.run(config)
```

(The trailing `logger.info("factor_evaluation_job_finished ...")` and `return result` stay unchanged.) Add `from zer0factor.services.evaluate import EvaluationService`; remove `evaluate_factors` from the `zer0factor.eval` import block in `main.py` and the now-dead `from zer0share.api import LocalPro` inside the function.

- [ ] **Step 3: Run the full suite and commit**

Run: `uv run pytest` — all PASS (CLI evaluation tests in test_main.py cover this path; check how they monkeypatch `LocalPro` — if they patch `main.LocalPro` or `zer0share.api.LocalPro`, the lazy import in `AppContext.pro` resolves through `zer0share.api`, so patching `zer0share.api.LocalPro` keeps working; adjust the monkeypatch target in the test if it patched a `main` attribute).

```bash
git add zer0factor/services/evaluate.py main.py tests/test_main.py
git commit -m "refactor: extract EvaluationService facade"
```

---

### Task 9: CLI package split (`zer0factor/cli/`), thin `main.py`

After Tasks 1–8, `main.py` contains only the click group, 12 commands, `configure-free` helpers (`_parse_periods`, `_run_evaluation_command`, `_run_evaluation_job`), and imports. This task relocates them. **Every command moves verbatim** (decorators and bodies unchanged) — only module-level imports are rebuilt per file.

**Files:**
- Create: `zer0factor/cli/__init__.py`
- Create: `zer0factor/cli/root.py` — `cli` group + `status`
- Create: `zer0factor/cli/registry_cmds.py` — `factor-list`, `factor-info`
- Create: `zer0factor/cli/compute_cmds.py` — `compute-returns`, `compute-market-cap`
- Create: `zer0factor/cli/preprocess_cmds.py` — `standardize-factor`, `neutralize-factor`
- Create: `zer0factor/cli/evaluate_cmds.py` — `_parse_periods`, `_run_evaluation_command`, `_run_evaluation_job`, `evaluate-factor`, `evaluate-factors`, `evaluate-batch`, `evaluate-summary`, `show-summary`
- Rewrite: `main.py`
- Rename: `tests/test_main.py` → `tests/test_cli.py`

- [ ] **Step 1: Create `zer0factor/cli/root.py`**

Move the `cli` group callback and `status` command verbatim from `main.py`, with imports:

```python
"""CLI root group and library status."""

from pathlib import Path

import click

from zer0factor.context import AppContext


@click.group()
@click.option("--config", default="config/settings.toml", show_default=True)
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config)


@cli.command()
@click.pass_context
def status(ctx):
    """Show factor library status."""
    app = AppContext.from_config_path(ctx.obj["config_path"])
    factors = app.storage.list_factors()
    if not factors:
        click.echo("No factors computed yet.")
    else:
        click.echo(f"Factors ({len(factors)}):")
        for name in factors:
            click.echo(f"  {name}")
```

- [ ] **Step 2: Create the four command modules**

Each module starts with `from zer0factor.cli.root import cli` and registers commands via the existing `@cli.command(...)` decorators. Move each command function verbatim from `main.py` (bodies already use `AppContext`/services after Tasks 4–8):

- `registry_cmds.py`: `factor_list_command`, `factor_info_command`. Imports: `click`, `pandas as pd`, `Path`, `AppContext`, `FactorRegistry`.
- `compute_cmds.py`: `compute_returns`, `compute_market_cap`. Imports: `click`, `logger`, `AppContext`, `FactorComputeService`, `ZScorePostProcess`, `MARKET_CAP_FACTORS`, `RETURN_FACTORS`.
- `preprocess_cmds.py`: `standardize_factor`, `neutralize_factor`. Imports: `click`, `logger`, `AppContext`, `FactorName`, `FactorPreprocessService`, `NEUTRALIZATION_SIZE_FACTOR`, `read_universe_panel`.
- `evaluate_cmds.py`: `_parse_periods`, `_run_evaluation_command`, `_run_evaluation_job`, `evaluate_factor_command`, `evaluate_factors_command`, `evaluate_batch_command`, `evaluate_summary_command`, `show_summary_command`. Imports: `click`, `pandas as pd`, `Path`, `logger`, `AppContext`, `EvaluationService`, and from `zer0factor.eval`: `EvaluationConfig`, `ReportThresholds`, `find_latest_run_dir`, `generate_evaluation_report`, `load_batch_evaluation_config`.

- [ ] **Step 3: Create `zer0factor/cli/__init__.py`**

Importing the command modules is what registers them on the group:

```python
"""Click CLI assembled from per-domain command modules."""

from zer0factor.cli import (  # noqa: F401  (imports register commands)
    compute_cmds,
    evaluate_cmds,
    preprocess_cmds,
    registry_cmds,
)
from zer0factor.cli.root import cli

__all__ = ["cli"]
```

- [ ] **Step 4: Rewrite `main.py`**

```python
from zer0factor.cli import cli

if __name__ == "__main__":
    cli()
```

(`pyproject.toml` defines no console script, and the READMEs invoke `python main.py ...` — unchanged.)

- [ ] **Step 5: Move the test file**

```bash
git mv tests/test_main.py tests/test_cli.py
```

In `tests/test_cli.py`, the remaining import from `main` is only `cli` — replace `from main import (cli,)` with `from zer0factor.cli import cli`. If any test monkeypatches `main.<attr>`, retarget to the module that now owns the attribute (e.g. `zer0factor.cli.evaluate_cmds`).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest` and `uv run python main.py --help`
Expected: all tests PASS; help lists all 12 commands (`status`, `factor-list`, `factor-info`, `compute-returns`, `compute-market-cap`, `standardize-factor`, `neutralize-factor`, `evaluate-factor`, `evaluate-factors`, `evaluate-batch`, `evaluate-summary`, `show-summary`).

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check .
git add main.py zer0factor/cli/ tests/test_cli.py
git commit -m "refactor: split CLI into zer0factor.cli package, main.py is a thin entry"
```

---

## Final structure

```
main.py                      # 4 lines: entry point
zer0factor/
  config.py                  # unchanged
  context.py                 # NEW: AppContext composition root
  naming.py                  # NEW: FactorName value object
  panel.py                   # NEW: shared long/wide panel utilities
  core/
    __init__.py              # unchanged (Factor/FactorSpec/FactorFrame/provider)
    protocols.py             # NEW: DataProvider/UniverseSource/IndustrySource
  factors/
    builtin.py               # NEW: RETURN_FACTORS / MARKET_CAP_FACTORS / FACTOR_GROUPS
  services/                  # NEW: application layer
    compute.py               # FactorComputeService + ZScorePostProcess
    preprocess.py            # FactorPreprocessService
    evaluate.py              # EvaluationService
  cli/                       # NEW: presentation layer
    root.py  registry_cmds.py  compute_cmds.py  preprocess_cmds.py  evaluate_cmds.py
  preprocess/  eval/  storage.py  registry.py  exposures.py   # unchanged
```

## Out of scope (deliberately)

- Moving `Zer0ShareDataProvider` out of `core/__init__.py` — cosmetic, adds import-cycle risk, defer.
- Registry-driven factor factory (`source_type` → class mapping) — wait until a second factor source type actually exists (YAGNI); `FACTOR_GROUPS` is the seam to extend.
- Protocol-typing the evaluation `pro` — `eval/loaders.py` uses a wider zer0share surface; type it when `eval` itself is next touched.
