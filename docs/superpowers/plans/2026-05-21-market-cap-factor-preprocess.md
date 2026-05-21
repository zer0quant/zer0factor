# Market Cap Factor Preprocess Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add total and circulating market cap as first-class log factors, preprocess them with the existing pipeline, and store raw plus z-scored versions.

**Architecture:** Extend the standard `FactorFrame` field contract with `total_mv` and `circ_mv`, loading those fields from `zer0share.daily_basic` while keeping OHLCV fields on `pro_bar`. Add dedicated market-cap factor classes and a small market-cap storage helper used by a new `compute-market-cap` CLI command.

**Tech Stack:** Python 3.11, pandas, numpy, click, pytest, existing zer0factor `Factor`, `FactorFrame`, `FactorStorage`, and `FactorPreprocessPipeline`.

---

## File Structure

- Modify `zer0factor/core/__init__.py`: add `total_mv` and `circ_mv` standard fields; route market-cap fields through `daily_basic`.
- Create `zer0factor/factors/market_cap.py`: `LogTotalMarketCap` and `LogCirculatingMarketCap`.
- Modify `zer0factor/factors/__init__.py`: export market-cap factor classes.
- Modify `main.py`: add market-cap factor constants, a helper to write raw and z-scored variants, and `compute-market-cap` CLI.
- Modify `tests/test_factor_standard.py`: validate new fields and provider loading behavior.
- Create `tests/test_market_cap_factors.py`: validate log market-cap factor computation.
- Modify `tests/test_main.py`: validate the market-cap storage helper writes all four factor names.

## Task 1: Provider Market Cap Fields

**Files:**
- Modify: `zer0factor/core/__init__.py`
- Modify: `tests/test_factor_standard.py`

- [ ] **Step 1: Add failing provider and field-contract tests**

Append or modify tests in `tests/test_factor_standard.py`:

```python
def test_factor_spec_accepts_market_cap_fields():
    spec = FactorSpec(
        name="log_total_market_cap",
        inputs=["total_mv", "circ_mv"],
        min_window=1,
        adjust=None,
    )

    assert spec.inputs == ("total_mv", "circ_mv")


def test_factor_frame_exposes_market_cap_fields():
    total_mv = _wide_frame(rows=2).astype(float) * 1000
    circ_mv = _wide_frame(rows=2).astype(float) * 500
    frame = FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})

    assert frame.total_mv.equals(total_mv)
    assert frame.circ_mv.equals(circ_mv)
```

Update `FakeLocalPro` in `tests/test_factor_standard.py`:

```python
class FakeLocalPro:
    def __init__(self):
        self.pro_bar_calls = 0
        self.daily_basic_calls = 0

    def stock_basic(self, list_status="L", fields=None):
        return pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"]})

    def pro_bar(self, ts_code, start_date, end_date, adj):
        self.pro_bar_calls += 1
        assert ts_code == "000001.SZ,000002.SZ"
        assert adj == "hfq"
        dates = pd.date_range("2024-01-01", periods=2, freq="D").strftime("%Y%m%d")
        frames = []
        for code, base in [("000001.SZ", 1), ("000002.SZ", 10)]:
            frames.append(
                pd.DataFrame(
                    {
                        "ts_code": [code, code],
                        "trade_date": dates,
                        "close": [base, base + 1],
                        "vol": [base * 100, (base + 1) * 100],
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)

    def daily_basic(self, ts_code=None, start_date=None, end_date=None, fields=None):
        self.daily_basic_calls += 1
        assert ts_code == "000001.SZ,000002.SZ"
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert fields == "ts_code,trade_date,total_mv,circ_mv"
        dates = pd.date_range("2024-01-01", periods=2, freq="D").strftime("%Y%m%d")
        frames = []
        for code, total_base, circ_base in [
            ("000001.SZ", 1000, 500),
            ("000002.SZ", 2000, 1000),
        ]:
            frames.append(
                pd.DataFrame(
                    {
                        "ts_code": [code, code],
                        "trade_date": dates,
                        "total_mv": [total_base, total_base + 100],
                        "circ_mv": [circ_base, circ_base + 50],
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)
```

Add provider tests:

```python
def test_zer0share_provider_loads_market_cap_fields_from_daily_basic():
    pro = FakeLocalPro()
    provider = Zer0ShareDataProvider(pro)

    frame = provider.history(
        fields=["total_mv", "circ_mv"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust=None,
    )

    assert pro.pro_bar_calls == 0
    assert pro.daily_basic_calls == 1
    assert frame.total_mv.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 1000
    assert frame.circ_mv.loc[pd.Timestamp("2024-01-02"), "000002.SZ"] == 1050


def test_zer0share_provider_combines_price_and_market_cap_fields():
    pro = FakeLocalPro()
    provider = Zer0ShareDataProvider(pro)

    frame = provider.history(
        fields=["close", "total_mv"],
        start_date="20240101",
        end_date="20240102",
        universe="all",
        adjust="hfq",
    )

    assert pro.pro_bar_calls == 1
    assert pro.daily_basic_calls == 1
    assert frame.close.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 2
    assert frame.total_mv.loc[pd.Timestamp("2024-01-02"), "000002.SZ"] == 2100
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_factor_standard.py -q`

Expected: FAIL because `total_mv` and `circ_mv` are unknown fields.

- [ ] **Step 3: Implement provider support**

Modify `zer0factor/core/__init__.py`:

```python
STANDARD_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "return_",
        "total_mv",
        "circ_mv",
    }
)
```

Add source groups near `_SOURCE_COLUMNS`:

```python
    _BAR_SOURCE_COLUMNS = {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "vol",
        "amount": "amount",
        "return_": "pct_chg",
    }
    _DAILY_BASIC_SOURCE_COLUMNS = {
        "total_mv": "total_mv",
        "circ_mv": "circ_mv",
    }
```

Replace the existing `history()` loading block with:

```python
        panels: dict[str, pd.DataFrame] = {}
        bar_fields = [field for field in requested if field in self._BAR_SOURCE_COLUMNS]
        basic_fields = [
            field for field in requested if field in self._DAILY_BASIC_SOURCE_COLUMNS
        ]

        if bar_fields:
            if codes:
                raw_bar = self._pro.pro_bar(
                    ts_code=",".join(codes),
                    start_date=start_date,
                    end_date=end_date,
                    adj=None if adjust == "none" else adjust,
                )
                if progress is not None:
                    progress(total, total, codes[-1])
            else:
                raw_bar = pd.DataFrame(columns=["trade_date", "ts_code"])
            panels.update(
                {
                    field: self._pivot_field(raw_bar, self._BAR_SOURCE_COLUMNS[field])
                    for field in bar_fields
                }
            )

        if basic_fields:
            if codes:
                source_fields = [
                    self._DAILY_BASIC_SOURCE_COLUMNS[field] for field in basic_fields
                ]
                raw_basic = self._pro.daily_basic(
                    ts_code=",".join(codes),
                    start_date=start_date,
                    end_date=end_date,
                    fields=",".join(["ts_code", "trade_date", *source_fields]),
                )
            else:
                raw_basic = pd.DataFrame(columns=["trade_date", "ts_code"])
            panels.update(
                {
                    field: self._pivot_field(
                        raw_basic,
                        self._DAILY_BASIC_SOURCE_COLUMNS[field],
                    )
                    for field in basic_fields
                }
            )
```

Keep existing validation and `FactorFrame(panels)` behavior.

- [ ] **Step 4: Run provider tests**

Run: `uv run pytest tests/test_factor_standard.py -q`

Expected: all tests in `tests/test_factor_standard.py` pass.

- [ ] **Step 5: Commit provider support**

```bash
git add zer0factor/core/__init__.py tests/test_factor_standard.py
git commit -m "feat: load market cap fields"
```

## Task 2: Log Market Cap Factors

**Files:**
- Create: `zer0factor/factors/market_cap.py`
- Modify: `zer0factor/factors/__init__.py`
- Create: `tests/test_market_cap_factors.py`

- [ ] **Step 1: Add failing market-cap factor tests**

Create `tests/test_market_cap_factors.py`:

```python
import numpy as np
import pandas as pd

from zer0factor.core import FactorFrame
from zer0factor.factors import LogCirculatingMarketCap, LogTotalMarketCap


def _market_cap_frame() -> FactorFrame:
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    total_mv = pd.DataFrame(
        {
            "000001.SZ": [100.0, 0.0],
            "000002.SZ": [np.e**2, -1.0],
        },
        index=idx,
    )
    circ_mv = pd.DataFrame(
        {
            "000001.SZ": [np.e, 50.0],
            "000002.SZ": [0.0, np.e**3],
        },
        index=idx,
    )
    return FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})


def test_log_total_market_cap_computes_natural_log_and_drops_non_positive_values():
    result = LogTotalMarketCap().compute(_market_cap_frame())

    assert result.to_dict("records") == [
        {
            "trade_date": "20240101",
            "ts_code": "000001.SZ",
            "value": np.log(100.0),
        },
        {
            "trade_date": "20240101",
            "ts_code": "000002.SZ",
            "value": 2.0,
        },
    ]


def test_log_circulating_market_cap_computes_natural_log_and_drops_non_positive_values():
    result = LogCirculatingMarketCap().compute(_market_cap_frame())

    assert result.to_dict("records") == [
        {
            "trade_date": "20240101",
            "ts_code": "000001.SZ",
            "value": 1.0,
        },
        {
            "trade_date": "20240102",
            "ts_code": "000001.SZ",
            "value": np.log(50.0),
        },
        {
            "trade_date": "20240102",
            "ts_code": "000002.SZ",
            "value": 3.0,
        },
    ]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_market_cap_factors.py -q`

Expected: FAIL because `LogTotalMarketCap` and `LogCirculatingMarketCap` are not exported.

- [ ] **Step 3: Implement market-cap factors**

Create `zer0factor/factors/market_cap.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from zer0factor.core import Factor, FactorFrame, FactorSpec, to_factor_output


class LogTotalMarketCap(Factor):
    spec = FactorSpec(
        name="log_total_market_cap",
        inputs=["total_mv"],
        min_window=1,
        frequency="1d",
        adjust=None,
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.total_mv.where(data.total_mv > 0)
        return to_factor_output(np.log(value), self.spec.name)


class LogCirculatingMarketCap(Factor):
    spec = FactorSpec(
        name="log_circulating_market_cap",
        inputs=["circ_mv"],
        min_window=1,
        frequency="1d",
        adjust=None,
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.circ_mv.where(data.circ_mv > 0)
        return to_factor_output(np.log(value), self.spec.name)
```

Modify `zer0factor/factors/__init__.py`:

```python
from zer0factor.factors.market_cap import (
    LogCirculatingMarketCap,
    LogTotalMarketCap,
)
from zer0factor.factors.returns import (
    DailyReturn,
    IntradayReturn,
    OpenReturn,
    OvernightReturn,
)

__all__ = [
    "DailyReturn",
    "IntradayReturn",
    "LogCirculatingMarketCap",
    "LogTotalMarketCap",
    "OpenReturn",
    "OvernightReturn",
]
```

- [ ] **Step 4: Run market-cap factor tests**

Run: `uv run pytest tests/test_market_cap_factors.py -q`

Expected: 2 tests pass.

- [ ] **Step 5: Commit market-cap factors**

```bash
git add zer0factor/factors/market_cap.py zer0factor/factors/__init__.py tests/test_market_cap_factors.py
git commit -m "feat: add log market cap factors"
```

## Task 3: Store Raw and Z-Scored Market Cap Factors

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing storage-helper test**

Append to `tests/test_main.py`:

```python
from main import MARKET_CAP_FACTORS, compute_and_store_market_cap_factors
```

If `tests/test_main.py` already imports from `main`, merge the imports into one line.

Add:

```python
class FakeMarketCapProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["circ_mv", "total_mv"]
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert universe == "000001.SZ,000002.SZ"
        assert adjust is None

        index = pd.date_range("2024-01-01", periods=2, freq="D")
        total_mv = pd.DataFrame(
            {
                "000001.SZ": [100.0, 110.0],
                "000002.SZ": [200.0, 220.0],
            },
            index=index,
        )
        circ_mv = pd.DataFrame(
            {
                "000001.SZ": [50.0, 55.0],
                "000002.SZ": [80.0, 88.0],
            },
            index=index,
        )
        return FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})


def test_compute_and_store_market_cap_factors_writes_raw_and_zscored(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")

    row_counts = compute_and_store_market_cap_factors(
        factors=MARKET_CAP_FACTORS,
        provider=FakeMarketCapProvider(),
        storage=storage,
        start_date="20240101",
        end_date="20240102",
        universe="000001.SZ,000002.SZ",
    )

    assert row_counts == {
        "log_total_market_cap": 4,
        "log_circulating_market_cap": 4,
        "z_log_total_market_cap": 4,
        "z_log_circulating_market_cap": 4,
    }
    assert storage.list_factors() == [
        "log_circulating_market_cap",
        "log_total_market_cap",
        "z_log_circulating_market_cap",
        "z_log_total_market_cap",
    ]

    z_total = storage.read("z_log_total_market_cap")
    assert set(z_total["trade_date"]) == {"20240101", "20240102"}
    assert z_total.groupby("trade_date")["value"].mean().abs().max() < 1e-12
```

- [ ] **Step 2: Run helper test to verify failure**

Run: `uv run pytest tests/test_main.py::test_compute_and_store_market_cap_factors_writes_raw_and_zscored -q`

Expected: FAIL because `MARKET_CAP_FACTORS` or `compute_and_store_market_cap_factors` is missing.

- [ ] **Step 3: Implement storage helper**

Modify `main.py` imports:

```python
from zer0factor.core import Factor, Zer0ShareDataProvider, run_factor, to_factor_output
from zer0factor.factors import (
    DailyReturn,
    IntradayReturn,
    LogCirculatingMarketCap,
    LogTotalMarketCap,
    OpenReturn,
    OvernightReturn,
)
from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig
```

Add constants:

```python
MARKET_CAP_FACTORS = (
    LogTotalMarketCap(),
    LogCirculatingMarketCap(),
)
MARKET_CAP_PREPROCESS_CONFIG = PreprocessConfig(
    winsorize_method="mad",
    winsorize_n=5.0,
    impute_method="cross_section_median",
    standardize_method="zscore",
    neutralize_method=None,
)
```

Add helper near `compute_and_store_factors()`:

```python
def compute_and_store_market_cap_factors(
    factors: tuple[Factor, ...],
    provider: Zer0ShareDataProvider,
    storage: FactorStorage,
    start_date: str,
    end_date: str | None,
    universe: str,
    progress: Callable[[int, int, str], None] | None = None,
    log_info: Callable[[str], None] | None = None,
) -> dict[str, int]:
    fields = sorted({field for factor in factors for field in factor.spec.inputs})
    if log_info is not None:
        log_info(f"market_cap_data_load_started fields={','.join(fields)}")
    data = provider.history(
        fields=fields,
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        adjust=None,
        progress=progress,
    )
    if log_info is not None:
        log_info("market_cap_data_load_finished")

    pipeline = FactorPreprocessPipeline(MARKET_CAP_PREPROCESS_CONFIG)
    row_counts: dict[str, int] = {}
    for factor in factors:
        raw = run_factor(factor, data, storage=storage)
        row_counts[factor.spec.name] = len(raw)

        z_name = f"z_{factor.spec.name}"
        z_factor = pipeline.transform(raw)
        storage.write(z_name, z_factor)
        row_counts[z_name] = len(z_factor)
        if log_info is not None:
            log_info(
                f"market_cap_factor_write_finished factor={factor.spec.name} "
                f"rows={len(raw)} z_factor={z_name} z_rows={len(z_factor)}"
            )
    return row_counts
```

- [ ] **Step 4: Run helper test**

Run: `uv run pytest tests/test_main.py::test_compute_and_store_market_cap_factors_writes_raw_and_zscored -q`

Expected: test passes.

- [ ] **Step 5: Commit helper**

```bash
git add main.py tests/test_main.py
git commit -m "feat: store preprocessed market cap factors"
```

## Task 4: Market Cap CLI Command

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing CLI smoke test**

Append to `tests/test_main.py`:

```python
from click.testing import CliRunner
from main import cli


def test_compute_market_cap_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["compute-market-cap", "--help"])

    assert result.exit_code == 0
    assert "Compute built-in market cap factors" in result.output
```

- [ ] **Step 2: Run CLI smoke test to verify failure**

Run: `uv run pytest tests/test_main.py::test_compute_market_cap_command_is_registered -q`

Expected: FAIL because the command is not registered.

- [ ] **Step 3: Implement CLI command**

Add to `main.py` after `compute_returns()`:

```python
@cli.command("compute-market-cap")
@click.pass_context
def compute_market_cap(ctx):
    """Compute built-in market cap factors and store raw plus z-scored values."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    end_date = cfg.end_date or None
    configure_logging(cfg.log_path)
    logger.info(
        "market_cap_factor_job_started universe={} start_date={} end_date={} fields={}",
        cfg.universe,
        cfg.start_date,
        end_date or "latest",
        "circ_mv,total_mv",
    )

    def show_progress(index: int, total: int, code: str) -> None:
        if index == 0:
            logger.info("universe_resolved stocks={}", total)
        elif index == total or index % 100 == 0:
            logger.info(
                "market_cap_data_load_progress loaded={} total={} code={}",
                index,
                total,
                code,
            )

    provider = Zer0ShareDataProvider(LocalPro(cfg.zer0share_data_dir))
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    row_counts = compute_and_store_market_cap_factors(
        factors=MARKET_CAP_FACTORS,
        provider=provider,
        storage=storage,
        start_date=cfg.start_date,
        end_date=end_date,
        universe=cfg.universe,
        progress=show_progress,
        log_info=logger.info,
    )
    for factor_name, row_count in row_counts.items():
        logger.info("market_cap_factor_rows factor={} rows={}", factor_name, row_count)
    logger.info("market_cap_factor_job_finished factors={}", len(row_counts))
```

- [ ] **Step 4: Run CLI smoke test**

Run: `uv run pytest tests/test_main.py::test_compute_market_cap_command_is_registered -q`

Expected: test passes.

- [ ] **Step 5: Commit CLI**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add market cap compute command"
```

## Task 5: Final Verification

**Files:**
- No planned code edits.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_factor_standard.py tests/test_market_cap_factors.py tests/test_main.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run preprocess regression tests**

Run:

```bash
uv run pytest tests/test_preprocess.py -q
```

Expected: all preprocess tests pass.

- [ ] **Step 3: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Run ruff on touched code**

Run:

```bash
uv run ruff check main.py zer0factor/core/__init__.py zer0factor/factors tests/test_factor_standard.py tests/test_market_cap_factors.py tests/test_main.py
```

Expected: no lint errors.

- [ ] **Step 5: Inspect git status**

Run:

```bash
git status --short
```

Expected: only pre-existing unrelated dirty files remain: `notebooks/01_alphalens_pct_chg.ipynb`, `uv.lock`, `.vscode/`.

## Self-Review Notes

- Spec coverage: source data, standard fields, log raw factors, `z_` factors, raw plus z-scored storage, CLI command, and tests are all covered.
- Scope preserved: no neutralization regression is implemented.
- Existing return-factor command remains unchanged except for shared imports.
