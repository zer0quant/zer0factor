# Factor Neutralization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement size and SW L1 industry neutralization for stored z-scored factors and write residuals as `neu_z_*` factors.

**Architecture:** Implement OLS neutralization inside `zer0factor.preprocess.neutralize`, keeping the existing `FactorPreprocessPipeline` API. Add a small exposure module for converting zer0share SW industry history into date x stock panels, then add a storage helper and CLI command in `main.py`.

**Tech Stack:** Python 3.11, pandas, numpy, click, pytest, existing `FactorStorage`, `FactorPreprocessPipeline`, and `zer0share.LocalPro`.

---

## File Structure

- Modify `zer0factor/preprocess/neutralize.py`: implement `size_industry` OLS residual neutralization.
- Modify `tests/test_preprocess.py`: add direct neutralization and pipeline coverage.
- Create `zer0factor/exposures.py`: convert SW industry membership history into a wide industry panel.
- Create `tests/test_exposures.py`: cover `in_date/out_date` and overlapping membership resolution.
- Modify `main.py`: add `neutralize_stored_factor` helper and `neutralize-factor` CLI.
- Modify `tests/test_main.py`: cover stored-factor neutralization helper and CLI registration.

## Task 1: OLS Neutralization

**Files:**
- Modify: `zer0factor/preprocess/neutralize.py`
- Modify: `tests/test_preprocess.py`

- [ ] **Step 1: Add failing neutralization tests**

Replace `test_size_industry_neutralization_raises_clear_not_implemented_error` in `tests/test_preprocess.py` with:

```python
def test_size_industry_neutralization_removes_size_and_industry_exposure():
    factor = pd.DataFrame(
        [[11.0, 13.0, 17.0, 19.0, 23.0, 29.0]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"],
    )
    size = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
        index=factor.index,
        columns=factor.columns,
    )
    industry = pd.DataFrame(
        [["bank", "bank", "tech", "tech", "energy", "energy"]],
        index=factor.index,
        columns=factor.columns,
    )

    result = neutralize(
        factor,
        method="size_industry",
        exposures={"size": size, "industry": industry},
    )

    row = result.loc[pd.Timestamp("2024-01-01")]
    valid = row.dropna()
    design = pd.DataFrame(
        {
            "intercept": 1.0,
            "size": size.loc[pd.Timestamp("2024-01-01"), valid.index],
        },
        index=valid.index,
    )
    dummies = pd.get_dummies(
        industry.loc[pd.Timestamp("2024-01-01"), valid.index],
        drop_first=True,
        dtype=float,
    )
    design = pd.concat([design, dummies], axis=1)

    assert abs(valid.sum()) < 1e-10
    assert np.abs(design.T.to_numpy() @ valid.to_numpy()).max() < 1e-10
```

Append:

```python
def test_size_industry_neutralization_requires_exposures():
    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError, match="size_industry neutralization requires size and industry"):
        neutralize(factor, method="size_industry", exposures={"size": factor})


def test_size_industry_neutralization_returns_nan_when_rows_are_insufficient():
    factor = _panel([[1.0, 2.0, 3.0]])
    size = _panel([[1.0, 2.0, 3.0]])
    industry = pd.DataFrame(
        [["bank", "tech", "energy"]],
        index=factor.index,
        columns=factor.columns,
    )

    result = neutralize(
        factor,
        method="size_industry",
        exposures={"size": size, "industry": industry},
    )

    assert result.loc[pd.Timestamp("2024-01-01")].isna().all()


def test_pipeline_size_industry_neutralization_preserves_long_output():
    factor = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"],
            "value": [11.0, 13.0, 17.0, 19.0, 23.0, 29.0],
        }
    )
    columns = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"]
    index = pd.to_datetime(["2024-01-01"])
    size = pd.DataFrame([[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]], index=index, columns=columns)
    industry = pd.DataFrame([["bank", "bank", "tech", "tech", "energy", "energy"]], index=index, columns=columns)
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="none",
            neutralize_method="size_industry",
        )
    )

    result = pipeline.transform(
        factor,
        exposures={"size": size, "industry": industry},
    )

    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result["trade_date"].unique().tolist() == ["20240101"]
    assert len(result) == 6
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_preprocess.py -q
```

Expected: FAIL because `size_industry` still raises the previous not-implemented error.

- [ ] **Step 3: Implement OLS neutralization**

Modify `zer0factor/preprocess/neutralize.py`:

```python
from typing import Literal

import numpy as np
import pandas as pd


def neutralize(
    factor: pd.DataFrame,
    *,
    method: Literal["size_industry", "none"] | None = None,
    exposures: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if method is None or method == "none":
        return factor.copy()
    if method == "size_industry":
        if exposures is None or "size" not in exposures or "industry" not in exposures:
            raise ValueError("size_industry neutralization requires size and industry exposures")
        return _neutralize_size_industry(
            factor,
            size=exposures["size"],
            industry=exposures["industry"],
        )
    raise ValueError(f"unknown neutralization method: {method}")


def _neutralize_size_industry(
    factor: pd.DataFrame,
    *,
    size: pd.DataFrame,
    industry: pd.DataFrame,
) -> pd.DataFrame:
    aligned_index = factor.index.union(size.index).union(industry.index)
    aligned_columns = factor.columns.union(size.columns).union(industry.columns)
    factor = factor.reindex(index=aligned_index, columns=aligned_columns)
    size = size.reindex(index=aligned_index, columns=aligned_columns)
    industry = industry.reindex(index=aligned_index, columns=aligned_columns)

    rows = [
        _neutralize_size_industry_row(
            factor.loc[date],
            size.loc[date],
            industry.loc[date],
        )
        for date in aligned_index
    ]
    return pd.DataFrame(rows, index=aligned_index, columns=aligned_columns).reindex_like(factor)


def _neutralize_size_industry_row(
    factor_row: pd.Series,
    size_row: pd.Series,
    industry_row: pd.Series,
) -> pd.Series:
    result = pd.Series(np.nan, index=factor_row.index, dtype="float64")
    frame = pd.DataFrame(
        {
            "factor": factor_row,
            "size": size_row,
            "industry": industry_row,
        }
    ).replace([np.inf, -np.inf], np.nan)
    valid = frame.dropna()
    if valid.empty:
        return result

    dummies = pd.get_dummies(valid["industry"].astype(str), drop_first=True, dtype=float)
    design = pd.concat(
        [
            pd.Series(1.0, index=valid.index, name="intercept"),
            valid["size"].astype(float).rename("size"),
            dummies,
        ],
        axis=1,
    )
    if len(valid) <= design.shape[1]:
        return result

    beta, *_ = np.linalg.lstsq(design.to_numpy(dtype=float), valid["factor"].to_numpy(dtype=float), rcond=None)
    residual = valid["factor"].to_numpy(dtype=float) - design.to_numpy(dtype=float) @ beta
    result.loc[valid.index] = residual
    return result
```

- [ ] **Step 4: Run neutralization tests**

Run:

```bash
uv run pytest tests/test_preprocess.py -q
```

Expected: all preprocessing tests pass.

- [ ] **Step 5: Commit OLS neutralization**

```bash
git add zer0factor/preprocess/neutralize.py tests/test_preprocess.py
git commit -m "feat: implement size industry neutralization"
```

## Task 2: SW Industry Exposure Builder

**Files:**
- Create: `zer0factor/exposures.py`
- Create: `tests/test_exposures.py`

- [ ] **Step 1: Add failing exposure tests**

Create `tests/test_exposures.py`:

```python
import pandas as pd

from zer0factor.exposures import build_sw_l1_industry_panel


class FakeIndustryPro:
    def index_member_all(self, fields=None):
        assert fields == "l1_code,l1_name,ts_code,in_date,out_date,is_new"
        return pd.DataFrame(
            {
                "l1_code": ["801010.SI", "801020.SI", "801030.SI", "801040.SI"],
                "l1_name": ["agri", "bank", "tech", "newtech"],
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000003.SZ"],
                "in_date": ["2020-01-01", "2020-01-01", "2020-01-01", "2024-01-02"],
                "out_date": [None, "2024-01-01", None, None],
                "is_new": ["Y", "N", "N", "Y"],
            }
        )


def test_build_sw_l1_industry_panel_applies_membership_dates_and_latest_overlap():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    ts_codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"]

    result = build_sw_l1_industry_panel(
        FakeIndustryPro(),
        dates=dates,
        ts_codes=ts_codes,
    )

    assert list(result.index) == list(dates)
    assert list(result.columns) == ts_codes
    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == "801010.SI"
    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == "801020.SI"
    assert pd.isna(result.loc[pd.Timestamp("2024-01-02"), "000002.SZ"])
    assert result.loc[pd.Timestamp("2024-01-01"), "000003.SZ"] == "801030.SI"
    assert result.loc[pd.Timestamp("2024-01-02"), "000003.SZ"] == "801040.SI"
    assert pd.isna(result.loc[pd.Timestamp("2024-01-03"), "000004.SZ"])
```

- [ ] **Step 2: Run exposure test to verify failure**

Run:

```bash
uv run pytest tests/test_exposures.py -q
```

Expected: FAIL because `zer0factor.exposures` does not exist.

- [ ] **Step 3: Implement exposure builder**

Create `zer0factor/exposures.py`:

```python
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def build_sw_l1_industry_panel(
    pro,
    *,
    dates: Iterable[pd.Timestamp | str],
    ts_codes: Iterable[str],
) -> pd.DataFrame:
    date_index = pd.DatetimeIndex(pd.to_datetime(list(dates))).sort_values()
    columns = sorted(str(code) for code in ts_codes)
    members = pro.index_member_all(
        fields="l1_code,l1_name,ts_code,in_date,out_date,is_new"
    )
    panel = pd.DataFrame(index=date_index, columns=columns, dtype="object")
    if members.empty or len(date_index) == 0 or len(columns) == 0:
        return panel

    members = members.loc[:, ["l1_code", "ts_code", "in_date", "out_date"]].copy()
    members["ts_code"] = members["ts_code"].astype(str)
    members = members[members["ts_code"].isin(columns)]
    members["in_date"] = pd.to_datetime(members["in_date"])
    members["out_date"] = pd.to_datetime(members["out_date"])
    members = members.sort_values(["ts_code", "in_date"])

    for date in date_index:
        active = members[
            (members["in_date"] <= date)
            & (members["out_date"].isna() | (date <= members["out_date"]))
        ]
        if active.empty:
            continue
        latest = active.sort_values("in_date").drop_duplicates("ts_code", keep="last")
        panel.loc[date, latest["ts_code"].to_numpy()] = latest["l1_code"].to_numpy()
    return panel
```

- [ ] **Step 4: Run exposure tests**

Run:

```bash
uv run pytest tests/test_exposures.py -q
```

Expected: exposure test passes.

- [ ] **Step 5: Commit exposure builder**

```bash
git add zer0factor/exposures.py tests/test_exposures.py
git commit -m "feat: build sw industry exposure panel"
```

## Task 3: Stored Factor Neutralization Helper

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing stored-helper test**

Modify the import from `main` in `tests/test_main.py` to include:

```python
neutralize_stored_factor
```

Append:

```python
class FakeIndustryNeutralizationPro:
    def index_member_all(self, fields=None):
        assert fields == "l1_code,l1_name,ts_code,in_date,out_date,is_new"
        return pd.DataFrame(
            {
                "l1_code": ["801010.SI", "801010.SI", "801020.SI", "801020.SI", "801030.SI", "801030.SI"],
                "l1_name": ["a", "a", "b", "b", "c", "c"],
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"],
                "in_date": ["2020-01-01"] * 6,
                "out_date": [None] * 6,
                "is_new": ["Y"] * 6,
            }
        )


def test_neutralize_stored_factor_writes_neu_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    source = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"],
            "value": [11.0, 13.0, 17.0, 19.0, 23.0, 29.0],
        }
    )
    size = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    storage.write("z_demo_factor", source)
    storage.write("z_log_circulating_market_cap", size)

    rows = neutralize_stored_factor(
        factor_name="z_demo_factor",
        output_name="neu_z_demo_factor",
        storage=storage,
        pro=FakeIndustryNeutralizationPro(),
        start_date="20240101",
        end_date="20240101",
    )

    result = storage.read("neu_z_demo_factor")
    assert rows == 6
    assert len(result) == 6
    assert "neu_z_demo_factor" in storage.list_factors()
```

- [ ] **Step 2: Run stored-helper test to verify failure**

Run:

```bash
uv run pytest tests/test_main.py::test_neutralize_stored_factor_writes_neu_factor -q
```

Expected: FAIL because `neutralize_stored_factor` does not exist.

- [ ] **Step 3: Implement stored helper**

Modify `main.py` imports:

```python
from zer0factor.exposures import build_sw_l1_industry_panel
```

Add helper functions before CLI commands:

```python
NEUTRALIZATION_SIZE_FACTOR = "z_log_circulating_market_cap"


def neutralize_stored_factor(
    *,
    factor_name: str,
    output_name: str,
    storage: FactorStorage,
    pro,
    start_date: str | None = None,
    end_date: str | None = None,
    size_factor_name: str = NEUTRALIZATION_SIZE_FACTOR,
) -> int:
    source = storage.read(factor_name, start_date=start_date, end_date=end_date)
    size = storage.read(size_factor_name, start_date=start_date, end_date=end_date)
    source_panel = _factor_long_to_wide(source)
    size_panel = _factor_long_to_wide(size)
    dates = source_panel.index.intersection(size_panel.index)
    ts_codes = source_panel.columns.intersection(size_panel.columns)
    source_panel = source_panel.reindex(index=dates, columns=ts_codes)
    size_panel = size_panel.reindex(index=dates, columns=ts_codes)
    industry_panel = build_sw_l1_industry_panel(pro, dates=dates, ts_codes=ts_codes)
    pipeline = FactorPreprocessPipeline(
        PreprocessConfig(
            winsorize_method="none",
            impute_method="none",
            standardize_method="none",
            neutralize_method="size_industry",
        )
    )
    result = pipeline.transform(
        source_panel,
        exposures={"size": size_panel, "industry": industry_panel},
    )
    output = _factor_wide_to_long(result)
    storage.write(output_name, output)
    return len(output)


def _factor_long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.loc[:, ["trade_date", "ts_code", "value"]].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame.pivot(index="trade_date", columns="ts_code", values="value").sort_index().sort_index(axis=1)


def _factor_wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.index = pd.to_datetime(result.index)
    long = result.stack(future_stack=True).dropna().rename("value").reset_index()
    long.columns = ["trade_date", "ts_code", "value"]
    long["trade_date"] = pd.to_datetime(long["trade_date"]).dt.strftime("%Y%m%d")
    return long.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
```

- [ ] **Step 4: Run stored-helper test**

Run:

```bash
uv run pytest tests/test_main.py::test_neutralize_stored_factor_writes_neu_factor -q
```

Expected: stored-helper test passes.

- [ ] **Step 5: Commit stored helper**

```bash
git add main.py tests/test_main.py
git commit -m "feat: neutralize stored factors"
```

## Task 4: Neutralization CLI

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing CLI test**

Append:

```python
def test_neutralize_factor_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["neutralize-factor", "--help"])

    assert result.exit_code == 0
    assert "Neutralize a stored z-scored factor" in result.output
    assert "--size-factor-name" in result.output
```

- [ ] **Step 2: Run CLI test to verify failure**

Run:

```bash
uv run pytest tests/test_main.py::test_neutralize_factor_command_is_registered -q
```

Expected: FAIL because command is not registered.

- [ ] **Step 3: Implement CLI command**

Add after `compute_market_cap` in `main.py`:

```python
@cli.command("neutralize-factor")
@click.argument("factor_name")
@click.option("--output-name", default=None)
@click.option("--size-factor-name", default=NEUTRALIZATION_SIZE_FACTOR, show_default=True)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.pass_context
def neutralize_factor(ctx, factor_name, output_name, size_factor_name, start_date, end_date):
    """Neutralize a stored z-scored factor against size and SW L1 industry."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    resolved_output = output_name or f"neu_{factor_name}"
    logger.info(
        "neutralize_factor_job_started factor={} output={} size_factor={} start_date={} end_date={}",
        factor_name,
        resolved_output,
        size_factor_name,
        resolved_start,
        resolved_end or "latest",
    )
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    rows = neutralize_stored_factor(
        factor_name=factor_name,
        output_name=resolved_output,
        storage=storage,
        pro=LocalPro(cfg.zer0share_data_dir),
        start_date=resolved_start,
        end_date=resolved_end,
        size_factor_name=size_factor_name,
    )
    logger.info("neutralize_factor_job_finished factor={} output={} rows={}", factor_name, resolved_output, rows)
```

- [ ] **Step 4: Run CLI test**

Run:

```bash
uv run pytest tests/test_main.py::test_neutralize_factor_command_is_registered -q
```

Expected: CLI test passes.

- [ ] **Step 5: Commit CLI**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add neutralize factor command"
```

## Task 5: Final Verification

**Files:**
- No planned code edits.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_preprocess.py tests/test_exposures.py tests/test_main.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run storage and market-cap regression tests**

Run:

```bash
uv run pytest tests/test_storage.py tests/test_market_cap_factors.py tests/test_factor_standard.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Run ruff on touched files**

Run:

```bash
uv run ruff check main.py zer0factor/preprocess/neutralize.py zer0factor/exposures.py tests/test_preprocess.py tests/test_exposures.py tests/test_main.py
```

Expected: no lint errors.

- [ ] **Step 5: Inspect git status**

Run:

```bash
git status --short
```

Expected: only pre-existing unrelated dirty files remain.

## Self-Review Notes

- Spec coverage: OLS neutralizer, SW L1 industry panel, stored-factor helper,
  CLI command, naming convention, and error handling are covered.
- Scope preserved: market-cap factors are not automatically neutralized.
- The plan intentionally reuses `FactorPreprocessPipeline` instead of creating
  a second neutralization path.
