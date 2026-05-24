# Factor Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `config/factors.toml` factor registry with `FactorRegistry` class, registry-driven `evaluate-batch`, and `factor-list` / `factor-info` CLI commands.

**Architecture:** `config/factors.toml` is the human-maintained declaration layer (name, category, source\_type, enabled, tags, evaluate defaults). `FactorStorage` (DuckDB + Parquet) is the machine state layer read-only for validation and display. `FactorRegistry` is the Python bridge between them.

**Tech Stack:** Python 3.11, `tomllib` (stdlib), `click`, `pandas`, `duckdb`, `pytest`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `zer0factor/storage.py` | Modify | Add `FactorStats` dataclass + `factor_stats()` method |
| `zer0factor/registry.py` | Create | `EvaluateMeta`, `FactorMeta`, `RegistryValidation`, `FactorRegistry` |
| `zer0factor/eval/batch.py` | Modify | Registry-mode `factor_source` in `load_batch_evaluation_config` |
| `config/factors.example.toml` | Create | Template factor registry with 2 example factors |
| `main.py` | Modify | Add `factor-list` and `factor-info` CLI commands |
| `tests/test_storage.py` | Modify | Tests for `factor_stats()` |
| `tests/test_registry.py` | Create | Tests for `FactorRegistry` load, filter, validate |
| `tests/test_eval_batch.py` | Create | Tests for registry-mode batch loading |
| `tests/test_main.py` | Modify | Tests for `factor-list`, `factor-info` |

---

## Task 1: `FactorStats` + `FactorStorage.factor_stats()`

**Files:**
- Modify: `zer0factor/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_storage.py`:

```python
from zer0factor.storage import FactorStats, FactorStorage


def test_factor_stats_returns_none_for_missing_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    assert storage.factor_stats("nonexistent") is None


def test_factor_stats_returns_counts_and_dates(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240103", "20240103"],
        "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
        "value": [0.1, 0.2, 0.3],
    })
    storage.write("z_test", df)
    stats = storage.factor_stats("z_test")
    assert isinstance(stats, FactorStats)
    assert stats.rows == 3
    assert str(stats.start_date) == "20240102"
    assert str(stats.end_date) == "20240103"


def test_factor_stats_returns_none_for_empty_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame(columns=["trade_date", "ts_code", "value"])
    storage.write("z_empty", df)
    assert storage.factor_stats("z_empty") is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_storage.py::test_factor_stats_returns_none_for_missing_factor tests/test_storage.py::test_factor_stats_returns_counts_and_dates tests/test_storage.py::test_factor_stats_returns_none_for_empty_factor -v
```

Expected: FAIL — `ImportError: cannot import name 'FactorStats'`

- [ ] **Step 3: Implement `FactorStats` and `factor_stats()`**

At the top of `zer0factor/storage.py`, after the imports, add:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class FactorStats:
    rows: int
    start_date: str
    end_date: str
```

Add this method to the `FactorStorage` class (after `list_factors`):

```python
def factor_stats(self, factor_name: str) -> FactorStats | None:
    factor_path = self._factor_dir / factor_name
    if not factor_path.exists():
        return None
    if not list(factor_path.glob("date=*/data.parquet")):
        return None
    pattern = str(factor_path / "date=*" / "data.parquet")
    row = duckdb.connect().execute(
        "SELECT count(*) AS rows, min(date) AS start_date, max(date) AS end_date"
        " FROM read_parquet(?, hive_partitioning=true)",
        [pattern],
    ).fetchone()
    if row is None or row[0] == 0:
        return None
    return FactorStats(rows=int(row[0]), start_date=str(row[1]), end_date=str(row[2]))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_storage.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add zer0factor/storage.py tests/test_storage.py
git commit -m "feat: add FactorStats and factor_stats() to FactorStorage"
```

---

## Task 2: `zer0factor/registry.py` — data models + load/filter

**Files:**
- Create: `zer0factor/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_registry.py`:

```python
from pathlib import Path

import pytest

from zer0factor.registry import EvaluateMeta, FactorMeta, FactorRegistry


def _write_registry(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "factors.toml"
    p.write_text(content)
    return p


def test_registry_loads_minimal_factor(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = "test"
""")
    reg = FactorRegistry(p)
    assert len(reg.all()) == 1
    meta = reg.all()[0]
    assert meta.name == "z_neu_daily_return"
    assert meta.category == "price"
    assert meta.source_type == "neutralized"
    assert meta.enabled is True
    assert meta.source_factor is None
    assert meta.tags == ()
    assert meta.evaluate is None


def test_registry_loads_factor_with_evaluate_block(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
""")
    reg = FactorRegistry(p)
    meta = reg.all()[0]
    assert isinstance(meta.evaluate, EvaluateMeta)
    assert meta.evaluate.default is True
    assert meta.evaluate.quantiles == 5
    assert meta.evaluate.periods == (1, 5, 10)
    assert meta.evaluate.return_type == "open_t1"


def test_registry_missing_required_field_raises(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "bad_factor"
category = "price"
""")
    with pytest.raises(ValueError, match="missing required fields"):
        FactorRegistry(p)


def test_registry_get_existing_factor(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    meta = reg.get("z_neu_daily_return")
    assert meta.name == "z_neu_daily_return"


def test_registry_get_missing_factor_raises(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    with pytest.raises(KeyError):
        reg.get("does_not_exist")


def test_registry_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FactorRegistry(tmp_path / "nonexistent.toml")


def test_registry_filter_by_enabled(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_a"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_b"
category = "price"
source_type = "neutralized"
enabled = false
description = ""
""")
    reg = FactorRegistry(p)
    enabled = reg.filter(enabled=True)
    assert [f.name for f in enabled] == ["z_a"]
    disabled = reg.filter(enabled=False)
    assert [f.name for f in disabled] == ["z_b"]


def test_registry_filter_by_category(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_price_factor"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_vol_factor"
category = "volume"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    price = reg.filter(category="price")
    assert [f.name for f in price] == ["z_price_factor"]


def test_registry_filter_by_evaluate_default(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_eval_default"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"

[[factors]]
name = "z_no_evaluate"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    reg = FactorRegistry(p)
    defaults = reg.filter(evaluate_default=True)
    assert [f.name for f in defaults] == ["z_eval_default"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_registry.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'zer0factor.registry'`

- [ ] **Step 3: Create `zer0factor/registry.py`**

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluateMeta:
    default: bool
    quantiles: int
    periods: tuple[int, ...]
    return_type: str


@dataclass(frozen=True)
class FactorMeta:
    name: str
    category: str
    source_type: str
    enabled: bool
    source_factor: str | None = None
    tags: tuple[str, ...] = ()
    description: str = ""
    evaluate: EvaluateMeta | None = None


@dataclass(frozen=True)
class RegistryValidation:
    registered_missing: tuple[str, ...]
    orphan_stored: tuple[str, ...]


class FactorRegistry:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._factors: dict[str, FactorMeta] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"factor registry not found: {self._path}")
        with open(self._path, "rb") as f:
            raw = tomllib.load(f)
        for entry in raw.get("factors", []):
            meta = _parse_factor_meta(entry)
            self._factors[meta.name] = meta

    def all(self) -> list[FactorMeta]:
        return list(self._factors.values())

    def get(self, name: str) -> FactorMeta:
        if name not in self._factors:
            raise KeyError(f"factor not registered: {name}")
        return self._factors[name]

    def filter(
        self,
        *,
        enabled: bool | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        evaluate_default: bool | None = None,
    ) -> list[FactorMeta]:
        results = list(self._factors.values())
        if enabled is not None:
            results = [f for f in results if f.enabled == enabled]
        if category is not None:
            results = [f for f in results if f.category == category]
        if tags is not None:
            results = [f for f in results if all(t in f.tags for t in tags)]
        if evaluate_default is not None:
            results = [
                f for f in results
                if f.evaluate is not None and f.evaluate.default == evaluate_default
            ]
        return results

    def validate(self, storage) -> RegistryValidation:
        stored = set(storage.list_factors())
        registered = set(self._factors)
        return RegistryValidation(
            registered_missing=tuple(sorted(registered - stored)),
            orphan_stored=tuple(sorted(stored - registered)),
        )


def _parse_factor_meta(entry: dict) -> FactorMeta:
    required = {"name", "category", "source_type", "enabled"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"factor entry missing required fields: {missing}")

    evaluate: EvaluateMeta | None = None
    if "evaluate" in entry:
        ev = entry["evaluate"]
        evaluate = EvaluateMeta(
            default=bool(ev.get("default", True)),
            quantiles=int(ev.get("quantiles", 5)),
            periods=tuple(ev.get("periods", [1, 5, 10])),
            return_type=str(ev.get("return_type", "open_t1")),
        )

    return FactorMeta(
        name=str(entry["name"]),
        category=str(entry["category"]),
        source_type=str(entry["source_type"]),
        enabled=bool(entry["enabled"]),
        source_factor=entry.get("source_factor"),
        tags=tuple(entry.get("tags", [])),
        description=str(entry.get("description", "")),
        evaluate=evaluate,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_registry.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add zer0factor/registry.py tests/test_registry.py
git commit -m "feat: add FactorRegistry with load, get, filter, validate"
```

---

## Task 3: `FactorRegistry.validate()` tests

`validate()` was already written in Task 2. This task adds tests for it.

**Files:**
- Modify: `tests/test_registry.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_registry.py`:

```python
import pandas as pd
from zer0factor.registry import RegistryValidation
from zer0factor.storage import FactorStorage


def _make_storage_with_factors(tmp_path: Path, names: list[str]) -> FactorStorage:
    storage = FactorStorage(tmp_path / "factors", tmp_path / "meta.duckdb")
    df = pd.DataFrame({
        "trade_date": ["20240102"],
        "ts_code": ["000001.SZ"],
        "value": [0.1],
    })
    for name in names:
        storage.write(name, df)
    return storage


def test_validate_registered_missing(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_registered_only"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    storage = _make_storage_with_factors(tmp_path, [])
    reg = FactorRegistry(p)
    result = reg.validate(storage)
    assert isinstance(result, RegistryValidation)
    assert "z_registered_only" in result.registered_missing
    assert result.orphan_stored == ()


def test_validate_orphan_stored(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_registered"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    storage = _make_storage_with_factors(tmp_path, ["z_registered", "z_orphan"])
    reg = FactorRegistry(p)
    result = reg.validate(storage)
    assert result.registered_missing == ()
    assert "z_orphan" in result.orphan_stored


def test_validate_all_clean(tmp_path):
    p = _write_registry(tmp_path, """
[[factors]]
name = "z_factor_a"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")
    storage = _make_storage_with_factors(tmp_path, ["z_factor_a"])
    reg = FactorRegistry(p)
    result = reg.validate(storage)
    assert result.registered_missing == ()
    assert result.orphan_stored == ()
```

- [ ] **Step 2: Run to verify they pass (validate was already implemented)**

```bash
uv run pytest tests/test_registry.py -v
```

Expected: All PASS (validate is already in the implementation from Task 2)

- [ ] **Step 3: Commit**

```bash
git add tests/test_registry.py
git commit -m "test: add validate() tests to test_registry"
```

---

## Task 4: `config/factors.example.toml`

**Files:**
- Create: `config/factors.example.toml`

- [ ] **Step 1: Create the example file**

Create `config/factors.example.toml`:

```toml
# Factor Registry — copy to config/factors.toml and edit
# source_type: built_in | stored | derived | neutralized

[registry]
version = "1"

[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
source_factor = "daily_return"
enabled = true
tags = ["momentum", "short-term"]
description = "Neutralized daily return factor"

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"

[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
source_factor = "open_return"
enabled = true
tags = ["momentum", "open"]
description = "Neutralized open return factor"

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
```

- [ ] **Step 2: Verify it parses cleanly**

```bash
uv run python -c "
import tomllib
from pathlib import Path
from zer0factor.registry import FactorRegistry
reg = FactorRegistry(Path('config/factors.example.toml'))
print('Loaded', len(reg.all()), 'factors:', [f.name for f in reg.all()])
"
```

Expected output: `Loaded 2 factors: ['z_neu_daily_return', 'z_neu_open_return']`

- [ ] **Step 3: Commit**

```bash
git add config/factors.example.toml
git commit -m "feat: add config/factors.example.toml factor registry template"
```

---

## Task 5: `evaluate-batch` registry mode

**Files:**
- Modify: `zer0factor/eval/batch.py`
- Create: `tests/test_eval_batch.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_eval_batch.py`:

```python
from pathlib import Path

import pytest

from zer0factor.eval.batch import load_batch_evaluation_config


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "batch.toml"
    p.write_text(content)
    return p


def test_load_batch_explicit_mode_unchanged(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factors = ["z_neu_daily_return", "z_neu_open_return"]
periods = [1, 5, 10]
return_type = "open_t1"
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.factor_names == ("z_neu_daily_return", "z_neu_open_return")


def test_load_batch_registry_mode_resolves_factors(tmp_path):
    registry = tmp_path / "factors.toml"
    registry.write_text("""
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
enabled = false
description = ""
""")
    p = _write_toml(tmp_path, f"""
[evaluation]
factor_source = "registry"
registry_path = "{registry}"
enabled_only = true
periods = [1, 5, 10]
return_type = "open_t1"
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.factor_names == ("z_neu_daily_return",)


def test_load_batch_registry_mode_category_filter(tmp_path):
    registry = tmp_path / "factors.toml"
    registry.write_text("""
[[factors]]
name = "z_price_factor"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_vol_factor"
category = "volume"
source_type = "neutralized"
enabled = true
description = ""
""")
    p = _write_toml(tmp_path, f"""
[evaluation]
factor_source = "registry"
registry_path = "{registry}"
categories = ["price"]
enabled_only = false
periods = [1, 5]
return_type = "open_t1"
""")
    cfg = load_batch_evaluation_config(p)
    assert cfg.factor_names == ("z_price_factor",)


def test_load_batch_registry_mode_no_matches_raises(tmp_path):
    registry = tmp_path / "factors.toml"
    registry.write_text("""
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = false
description = ""
""")
    p = _write_toml(tmp_path, f"""
[evaluation]
factor_source = "registry"
registry_path = "{registry}"
enabled_only = true
periods = [1, 5, 10]
return_type = "open_t1"
""")
    with pytest.raises(ValueError, match="no factors matched"):
        load_batch_evaluation_config(p)


def test_load_batch_invalid_factor_source_raises(tmp_path):
    p = _write_toml(tmp_path, """
[evaluation]
factor_source = "unknown"
factors = ["z_neu_daily_return"]
""")
    with pytest.raises(ValueError, match="unknown factor_source"):
        load_batch_evaluation_config(p)
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_eval_batch.py -v
```

Expected: FAIL — existing explicit-mode test passes but registry-mode tests fail

- [ ] **Step 3: Update `zer0factor/eval/batch.py`**

Add import at the top:

```python
from zer0factor.registry import FactorRegistry
```

Replace the `factor_names` resolution block in `load_batch_evaluation_config` (the current block starting with `factors = evaluation.get("factors", ())`) with:

```python
factor_source = evaluation.get("factor_source", "explicit")
if factor_source == "registry":
    registry_path = Path(evaluation.get("registry_path", "config/factors.toml"))
    registry = FactorRegistry(registry_path)
    enabled_only = bool(evaluation.get("enabled_only", True))
    categories = set(evaluation.get("categories") or [])
    candidates = registry.filter(enabled=True if enabled_only else None)
    if categories:
        candidates = [f for f in candidates if f.category in categories]
    factor_names = tuple(f.name for f in candidates)
    if not factor_names:
        raise ValueError("no factors matched from registry with the given filters")
elif factor_source == "explicit":
    raw_factors = evaluation.get("factors", ())
    if isinstance(raw_factors, (str, bytes)):
        raise ValueError("batch config [evaluation].factors must be a list of names")
    factor_names = tuple(raw_factors)
    if not factor_names:
        raise ValueError("batch config [evaluation].factors must not be empty")
else:
    raise ValueError(f"unknown factor_source '{factor_source}': must be 'explicit' or 'registry'")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_eval_batch.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add zer0factor/eval/batch.py tests/test_eval_batch.py
git commit -m "feat: add registry-mode factor_source to evaluate-batch"
```

---

## Task 6: `factor-list` CLI command

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_main.py`:

```python
def _write_settings(tmp_path, factor_dir, db_path):
    p = tmp_path / "settings.toml"
    p.write_text(f"""
[zer0share]
data_dir = "."

[paths]
factor_dir = "{factor_dir}"
db_path = "{db_path}"
log_path = "{tmp_path / 'factor.log'}"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20240101"
end_date = ""
""")
    return p


def _write_registry(tmp_path, content: str):
    p = tmp_path / "factors.toml"
    p.write_text(content)
    return p


def test_factor_list_command_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["factor-list", "--help"])
    assert result.exit_code == 0
    assert "factor-list" in result.output or "List" in result.output


def test_factor_list_shows_registered_and_orphan(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102"],
        "ts_code": ["000001.SZ"],
        "value": [0.1],
    })
    storage.write("z_neu_daily_return", df)
    storage.write("z_orphan_factor", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-list",
        "--registry", str(registry_toml),
    ])
    assert result.exit_code == 0
    assert "z_neu_daily_return" in result.output
    assert "z_neu_open_return" in result.output
    assert "z_orphan_factor" in result.output
    assert "registered but missing" in result.output
    assert "stored but unregistered" in result.output


def test_factor_list_registered_flag_hides_orphans(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102"],
        "ts_code": ["000001.SZ"],
        "value": [0.1],
    })
    storage.write("z_neu_daily_return", df)
    storage.write("z_orphan", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-list",
        "--registry", str(registry_toml),
        "--registered",
    ])
    assert result.exit_code == 0
    assert "z_orphan" not in result.output


def test_factor_list_orphan_flag_shows_only_orphans(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102"],
        "ts_code": ["000001.SZ"],
        "value": [0.1],
    })
    storage.write("z_orphan", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-list",
        "--registry", str(registry_toml),
        "--orphan",
    ])
    assert result.exit_code == 0
    assert "z_orphan" in result.output
    assert "z_neu_daily_return" not in result.output
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_main.py::test_factor_list_command_shows_help tests/test_main.py::test_factor_list_shows_registered_and_orphan -v
```

Expected: FAIL — `No such command 'factor-list'`

- [ ] **Step 3: Add `factor-list` command to `main.py`**

Add import at the top of `main.py` (after existing imports):

```python
from zer0factor.registry import FactorRegistry
```

Add the command after the `status` command:

```python
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

    cfg = load_config(ctx.obj["config_path"])
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    registry = FactorRegistry(Path(registry_path))
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

    if not registered:
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
            click.echo(f"\nregistered but missing in storage ({len(validation.registered_missing)}): {names}")
        if not registered and validation.orphan_stored:
            names = ", ".join(validation.orphan_stored)
            click.echo(f"stored but unregistered ({len(validation.orphan_stored)}): {names}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_main.py::test_factor_list_command_shows_help tests/test_main.py::test_factor_list_shows_registered_and_orphan tests/test_main.py::test_factor_list_registered_flag_hides_orphans tests/test_main.py::test_factor_list_orphan_flag_shows_only_orphans -v
```

Expected: All PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v --ignore=tests/test_factor_research_skill_scripts.py
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add factor-list CLI command"
```

---

## Task 7: `factor-info` CLI command

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_main.py`:

```python
def test_factor_info_command_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["factor-info", "--help"])
    assert result.exit_code == 0


def test_factor_info_shows_registry_and_storage(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
source_factor = "daily_return"
enabled = true
tags = ["momentum"]
description = "Test factor"

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240103"],
        "ts_code": ["000001.SZ", "000001.SZ"],
        "value": [0.1, 0.2],
    })
    storage.write("z_neu_daily_return", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-info", "z_neu_daily_return",
        "--registry", str(registry_toml),
    ])
    assert result.exit_code == 0
    assert "z_neu_daily_return" in result.output
    assert "price" in result.output
    assert "neutralized" in result.output
    assert "daily_return" in result.output
    assert "momentum" in result.output
    assert "20240102" in result.output
    assert "20240103" in result.output


def test_factor_info_unregistered_factor_exits_nonzero(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-info", "z_does_not_exist",
        "--registry", str(registry_toml),
    ])
    assert result.exit_code != 0


def test_factor_info_shows_not_found_when_missing_from_storage(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    FactorStorage(factor_dir, db_path)  # init storage, write nothing

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-info", "z_neu_daily_return",
        "--registry", str(registry_toml),
    ])
    assert result.exit_code == 0
    assert "not found" in result.output.lower() or "N" in result.output
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_main.py::test_factor_info_command_shows_help tests/test_main.py::test_factor_info_shows_registry_and_storage -v
```

Expected: FAIL — `No such command 'factor-info'`

- [ ] **Step 3: Add `factor-info` command to `main.py`**

Add after the `factor-list` command:

```python
@cli.command("factor-info")
@click.argument("name")
@click.option("--registry", "registry_path", default="config/factors.toml", show_default=True)
@click.pass_context
def factor_info_command(ctx, name, registry_path):
    """Show registry metadata and storage status for a single factor."""
    cfg = load_config(ctx.obj["config_path"])
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    registry = FactorRegistry(Path(registry_path))

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_main.py::test_factor_info_command_shows_help tests/test_main.py::test_factor_info_shows_registry_and_storage tests/test_main.py::test_factor_info_unregistered_factor_exits_nonzero tests/test_main.py::test_factor_info_shows_not_found_when_missing_from_storage -v
```

Expected: All PASS

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/ -v --ignore=tests/test_factor_research_skill_scripts.py
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add factor-info CLI command"
```

---

## Done

After all tasks are committed, the factor registry is operational:

```bash
# List all factors with storage status
uv run python main.py factor-list

# List only enabled, price-category factors
uv run python main.py factor-list --enabled --category price

# Show detailed info for one factor
uv run python main.py factor-info z_neu_daily_return

# Run batch evaluation driven by registry
uv run python main.py evaluate-batch --file config/evaluation_batch.example.toml
# (with factor_source = "registry" in the batch TOML)
```
