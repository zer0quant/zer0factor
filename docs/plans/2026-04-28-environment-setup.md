# Environment Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Scaffold the zer0factor project — git, pyproject.toml, config, storage skeleton, and per-layer init files.

**Architecture:** zer0factor uses `LocalPro` from zer0share directly (`from zer0share.api import LocalPro`). No `loader.py` wrapper needed. Factor storage lives in `data/factors/` with the same Parquet + DuckDB pattern as zer0share.

**Tech Stack:** Python 3.11+, uv, zer0share (path dep), duckdb, pyarrow, pandas, loguru, click, pytest, ruff

---

## Task 1: Git & directory skeleton

**Files:**
- Create: `.gitignore`
- Create: `notebooks/.gitkeep`
- Create: `logs/.gitkeep`
- Create: `src/__init__.py`
- Create: `src/factor/__init__.py`
- Create: `src/eval/__init__.py`
- Create: `src/portfolio/__init__.py`
- Create: `tests/__init__.py`

**Step 1: Init git**

```bash
cd D:\Project\zer0factor
git init
```

Expected: `Initialized empty Git repository`

**Step 2: Create .gitignore**

```
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
config/settings.toml
data/
db/
logs/
*.egg-info/
dist/
.ipynb_checkpoints/
```

**Step 3: Create directories and placeholder files**

```bash
mkdir -p notebooks logs src/factor src/eval src/portfolio tests
touch notebooks/.gitkeep logs/.gitkeep
touch src/__init__.py src/factor/__init__.py src/eval/__init__.py src/portfolio/__init__.py
touch tests/__init__.py
```

**Step 4: Commit**

```bash
git add .gitignore src/ tests/ notebooks/.gitkeep logs/.gitkeep
git commit -m "chore: init repo skeleton"
```

---

## Task 2: pyproject.toml

**Files:**
- Create: `pyproject.toml`

**Step 1: Write pyproject.toml**

```toml
[project]
name = "zer0factor"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "zer0share",
    "duckdb>=1.1.0",
    "pyarrow>=17.0.0",
    "pandas>=2.0.0",
    "numpy>=1.26.0",
    "alphalens-reloaded>=0.4.0",
    "pyfolio-reloaded>=0.9.0",
    "plotly>=5.0.0",
    "jupyter>=1.0.0",
    "ipykernel>=6.0.0",
    "loguru>=0.7.0",
    "click>=8.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.4.0",
]

[tool.uv.sources]
zer0share = { path = "../zer0share" }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"]
```

**Step 2: Install dependencies**

```bash
uv sync --dev
```

Expected: Lockfile created, `.venv` populated, zer0share installed from `../zer0share`.

**Step 3: Verify zer0share import**

```bash
uv run python -c "from zer0share.api import LocalPro; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pyproject.toml with zer0share path dependency"
```

---

## Task 3: Configuration

**Files:**
- Create: `config/settings.example.toml`
- Create: `src/config.py`
- Create: `tests/test_config.py`

**Step 1: Write failing test**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from src.config import load_config, Config


def test_load_config_returns_config(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("""
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path = "db/factor_meta.duckdb"
log_path = "logs/factor.log"

[factor]
universe = "all"
start_date = "20160101"
end_date = ""
""")
    cfg = load_config(toml)
    assert isinstance(cfg, Config)
    assert cfg.zer0share_data_dir == Path("../zer0share/data")
    assert cfg.factor_dir == Path("data/factors")
    assert cfg.universe == "all"
    assert cfg.start_date == "20160101"
    assert cfg.end_date == ""


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("nonexistent.toml"))


def test_load_config_missing_key(tmp_path):
    toml = tmp_path / "settings.toml"
    toml.write_text("[zer0share]\n")
    with pytest.raises(KeyError):
        load_config(toml)
```

**Step 2: Run test — expect FAIL**

```bash
uv run python -m pytest tests/test_config.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.config'`

**Step 3: Write config/settings.example.toml**

```toml
[zer0share]
data_dir = "../zer0share/data"   # zer0share 的 Parquet 数据目录

[paths]
factor_dir = "data/factors"
db_path    = "db/factor_meta.duckdb"
log_path   = "logs/factor.log"

[factor]
universe   = "all"      # all / hs300 / zz500
start_date = "20160101"
end_date   = ""         # 空 = 最新交易日
```

**Step 4: Write src/config.py**

```python
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    zer0share_data_dir: Path
    factor_dir: Path
    db_path: Path
    log_path: Path
    universe: str
    start_date: str
    end_date: str


def load_config(path: Path = Path("config/settings.toml")) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"配置文件格式错误: {e}") from e
    try:
        return Config(
            zer0share_data_dir=Path(raw["zer0share"]["data_dir"]),
            factor_dir=Path(raw["paths"]["factor_dir"]),
            db_path=Path(raw["paths"]["db_path"]),
            log_path=Path(raw["paths"]["log_path"]),
            universe=raw["factor"]["universe"],
            start_date=raw["factor"]["start_date"],
            end_date=raw["factor"]["end_date"],
        )
    except KeyError as e:
        raise KeyError(f"配置文件缺少必要字段: {e}") from e
```

**Step 5: Run test — expect PASS**

```bash
uv run python -m pytest tests/test_config.py -v
```

Expected: 3 PASSED

**Step 6: Commit**

```bash
git add config/settings.example.toml src/config.py tests/test_config.py
git commit -m "feat: add config loader with tests"
```

---

## Task 4: FactorStorage

**Files:**
- Create: `src/storage.py`
- Create: `tests/test_storage.py`

**Context:** FactorStorage writes factor values as Parquet partitioned by date, tracks metadata in DuckDB. Factor DataFrame shape: long-format with columns `(trade_date, ts_code, value)`.

**Step 1: Write failing tests**

```python
# tests/test_storage.py
import pytest
import pandas as pd
from pathlib import Path
from src.storage import FactorStorage


def test_factor_storage_init(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    assert storage is not None


def test_write_and_read_factor(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240102"],
        "ts_code": ["000001.SZ", "000002.SZ"],
        "value": [0.5, -0.3],
    })
    storage.write("momentum_1m", df)

    result = storage.read("momentum_1m", start_date="20240101", end_date="20240131")
    assert len(result) == 2
    assert set(result.columns) == {"trade_date", "ts_code", "value"}


def test_list_factors_empty(tmp_path):
    storage = FactorStorage(
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "meta.duckdb",
    )
    assert storage.list_factors() == []
```

**Step 2: Run test — expect FAIL**

```bash
uv run python -m pytest tests/test_storage.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

**Step 3: Write src/storage.py**

```python
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class FactorStorage:
    def __init__(self, factor_dir: Path, db_path: Path):
        self._factor_dir = Path(factor_dir)
        self._db_path = Path(db_path)
        self._factor_dir.mkdir(parents=True, exist_ok=True)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with duckdb.connect(str(self._db_path)) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS factor_registry (
                    factor_name VARCHAR PRIMARY KEY,
                    last_updated TIMESTAMP DEFAULT now()
                )
            """)

    def write(self, factor_name: str, df: pd.DataFrame) -> None:
        required = {"trade_date", "ts_code", "value"}
        if not required.issubset(df.columns):
            raise ValueError(f"DataFrame must have columns: {required}")

        for date, group in df.groupby("trade_date"):
            partition = self._factor_dir / factor_name / f"date={date}"
            partition.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pandas(
                group[["ts_code", "value"]].reset_index(drop=True),
                preserve_index=False,
            )
            pq.write_table(table, partition / "data.parquet")

        with duckdb.connect(str(self._db_path)) as con:
            con.execute("""
                INSERT INTO factor_registry (factor_name) VALUES (?)
                ON CONFLICT (factor_name) DO UPDATE SET last_updated = now()
            """, [factor_name])

    def read(
        self,
        factor_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        factor_path = self._factor_dir / factor_name
        if not factor_path.exists():
            raise FileNotFoundError(f"Factor '{factor_name}' not found")

        pattern = str(factor_path / "date=*" / "data.parquet")
        where = []
        params: list = [pattern]
        if start_date:
            where.append("trade_date >= ?")
            params.append(start_date)
        if end_date:
            where.append("trade_date <= ?")
            params.append(end_date)

        sql = "SELECT trade_date, ts_code, value FROM read_parquet(?, hive_partitioning=true)"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY trade_date, ts_code"

        return duckdb.connect().execute(sql, params).fetchdf()

    def list_factors(self) -> list[str]:
        with duckdb.connect(str(self._db_path)) as con:
            rows = con.execute(
                "SELECT factor_name FROM factor_registry ORDER BY factor_name"
            ).fetchall()
        return [r[0] for r in rows]
```

**Step 4: Run test — expect PASS**

```bash
uv run python -m pytest tests/test_storage.py -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/storage.py tests/test_storage.py
git commit -m "feat: add FactorStorage with Parquet write/read and DuckDB registry"
```

---

## Task 5: CLI entry point

**Files:**
- Create: `main.py`

**Step 1: Write main.py**

```python
import click
from pathlib import Path

from src.config import load_config
from src.storage import FactorStorage


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
    cfg = load_config(ctx.obj["config_path"])
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    factors = storage.list_factors()
    if not factors:
        click.echo("No factors computed yet.")
    else:
        click.echo(f"Factors ({len(factors)}):")
        for name in factors:
            click.echo(f"  {name}")


if __name__ == "__main__":
    cli()
```

**Step 2: Verify CLI runs**

```bash
uv run python main.py --help
```

Expected: Help text with `status` command listed.

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add Click CLI with status command"
```

---

## Task 6: Full verification

**Step 1: Run all tests with coverage**

```bash
uv run python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected: All tests PASS, coverage ≥ 80% on `config.py` and `storage.py`.

**Step 2: Run ruff lint**

```bash
uv run ruff check src/ tests/
```

Expected: No errors.

**Step 3: Copy and configure settings**

```bash
cp config/settings.example.toml config/settings.toml
```

Edit `config/settings.toml` — set `zer0share.data_dir` to zer0share's actual data path (e.g. `../zer0share/data`).

**Step 4: Verify status command**

```bash
uv run python main.py status
```

Expected: `No factors computed yet.`

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: environment setup complete"
```

---

## Completion Checklist

- [ ] Git initialized, .gitignore in place
- [ ] `uv sync --dev` succeeds, `from zer0share.api import LocalPro` works
- [ ] `src/config.py` — 3 tests pass
- [ ] `src/storage.py` — 3 tests pass
- [ ] `main.py status` runs without error
- [ ] `ruff check` clean
- [ ] Coverage ≥ 80% on implemented modules
