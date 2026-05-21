# Factor Preprocess Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a configurable cross-sectional preprocessing pipeline for zer0factor with winsorization, imputation, standardization, and a guarded neutralization interface.

**Architecture:** Add a focused `zer0factor.preprocess` package. Core functions operate on wide `pandas.DataFrame` panels by trade date, while `FactorPreprocessPipeline` handles long-table conversion and fixed step ordering.

**Tech Stack:** Python 3.11, pandas, pytest, existing zer0factor `trade_date, ts_code, value` schema.

---

## File Structure

- Create `zer0factor/preprocess/__init__.py`: public exports.
- Create `zer0factor/preprocess/winsorize.py`: MAD and quantile clipping.
- Create `zer0factor/preprocess/impute.py`: cross-sectional median filling and industry guard.
- Create `zer0factor/preprocess/standardize.py`: z-score and percentile rank standardization.
- Create `zer0factor/preprocess/neutralize.py`: neutralization guard interface.
- Create `zer0factor/preprocess/pipeline.py`: `PreprocessConfig`, input conversion, fixed-order pipeline.
- Create `tests/test_preprocess.py`: unit tests for functions, pipeline behavior, and errors.

## Task 1: Winsorization

**Files:**
- Create: `tests/test_preprocess.py`
- Create: `zer0factor/preprocess/winsorize.py`
- Create: `zer0factor/preprocess/__init__.py`

- [ ] **Step 1: Write failing winsorization tests**

Create `tests/test_preprocess.py` with:

```python
import numpy as np
import pandas as pd
import pytest


def _panel(values: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        values,
        index=pd.to_datetime(["2024-01-01", "2024-01-02"][: len(values)]),
        columns=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"][
            : len(values[0])
        ],
    )


def test_mad_winsorization_clips_extreme_cross_sectional_value():
    from zer0factor.preprocess.winsorize import winsorize

    factor = _panel([[1.0, 2.0, 3.0, 100.0]])

    result = winsorize(factor, method="mad", n=2.0)

    assert result.loc[pd.Timestamp("2024-01-01"), "000004.SZ"] == 4.5
    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == 1.0


def test_quantile_winsorization_clips_to_configured_quantiles():
    from zer0factor.preprocess.winsorize import winsorize

    factor = _panel([[1.0, 2.0, 3.0, 100.0]])

    result = winsorize(
        factor,
        method="quantile",
        lower_quantile=0.25,
        upper_quantile=0.75,
    )

    row = result.loc[pd.Timestamp("2024-01-01")]
    assert row["000001.SZ"] == 1.75
    assert row["000004.SZ"] == 27.25


def test_mad_winsorization_skips_zero_mad_rows():
    from zer0factor.preprocess.winsorize import winsorize

    factor = _panel([[1.0, 1.0, 1.0, 50.0]])

    result = winsorize(factor, method="mad", n=5.0)

    pd.testing.assert_frame_equal(result, factor)
```

- [ ] **Step 2: Run winsorization tests to verify failure**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'zer0factor.preprocess'`.

- [ ] **Step 3: Implement winsorization**

Create `zer0factor/preprocess/__init__.py`:

```python
from zer0factor.preprocess.winsorize import winsorize

__all__ = ["winsorize"]
```

Create `zer0factor/preprocess/winsorize.py`:

```python
from __future__ import annotations

from typing import Literal

import pandas as pd


WinsorizeMethod = Literal["mad", "quantile", "none"]


def winsorize(
    factor: pd.DataFrame,
    *,
    method: WinsorizeMethod = "mad",
    n: float = 5.0,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
) -> pd.DataFrame:
    if method == "none":
        return factor.copy()
    if method == "mad":
        if n <= 0:
            raise ValueError("n must be positive")
        return factor.apply(lambda row: _winsorize_mad_row(row, n), axis=1)
    if method == "quantile":
        if not 0 <= lower_quantile < upper_quantile <= 1:
            raise ValueError("quantile bounds must satisfy 0 <= lower < upper <= 1")
        return factor.apply(
            lambda row: _winsorize_quantile_row(
                row,
                lower_quantile,
                upper_quantile,
            ),
            axis=1,
        )
    raise ValueError(f"unknown winsorize method: {method}")


def _winsorize_mad_row(row: pd.Series, n: float) -> pd.Series:
    median = row.median(skipna=True)
    mad = (row - median).abs().median(skipna=True)
    if pd.isna(median) or pd.isna(mad) or mad == 0:
        return row
    lower = median - n * mad
    upper = median + n * mad
    return row.clip(lower=lower, upper=upper)


def _winsorize_quantile_row(
    row: pd.Series,
    lower_quantile: float,
    upper_quantile: float,
) -> pd.Series:
    lower = row.quantile(lower_quantile)
    upper = row.quantile(upper_quantile)
    if pd.isna(lower) or pd.isna(upper):
        return row
    return row.clip(lower=lower, upper=upper)
```

- [ ] **Step 4: Run winsorization tests**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: PASS for the three winsorization tests.

- [ ] **Step 5: Commit winsorization**

```bash
git add tests/test_preprocess.py zer0factor/preprocess/__init__.py zer0factor/preprocess/winsorize.py
git commit -m "feat: add factor winsorization"
```

## Task 2: Missing Value Imputation

**Files:**
- Modify: `tests/test_preprocess.py`
- Create: `zer0factor/preprocess/impute.py`
- Modify: `zer0factor/preprocess/__init__.py`

- [ ] **Step 1: Add failing imputation tests**

Append to `tests/test_preprocess.py`:

```python
def test_cross_section_median_imputation_fills_per_date():
    from zer0factor.preprocess.impute import impute_missing

    factor = _panel([[1.0, np.nan, 3.0], [np.nan, 10.0, 14.0]])

    result = impute_missing(factor, method="cross_section_median")

    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 2.0
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"] == 12.0


def test_imputation_treats_infinite_values_as_missing():
    from zer0factor.preprocess.impute import impute_missing

    factor = _panel([[1.0, np.inf, 3.0]])

    result = impute_missing(factor, method="cross_section_median")

    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == 2.0


def test_entirely_missing_rows_remain_missing_after_imputation():
    from zer0factor.preprocess.impute import impute_missing

    factor = _panel([[np.nan, np.nan, np.nan]])

    result = impute_missing(factor, method="cross_section_median")

    assert result.loc[pd.Timestamp("2024-01-01")].isna().all()


def test_industry_median_imputation_without_industry_data_raises():
    from zer0factor.preprocess.impute import impute_missing

    factor = _panel([[1.0, np.nan, 3.0]])

    with pytest.raises(ValueError, match="industry_median imputation requires industry data"):
        impute_missing(factor, method="industry_median")
```

- [ ] **Step 2: Run imputation tests to verify failure**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'zer0factor.preprocess.impute'`.

- [ ] **Step 3: Implement imputation**

Create `zer0factor/preprocess/impute.py`:

```python
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


ImputeMethod = Literal["cross_section_median", "industry_median", "none"]


def impute_missing(
    factor: pd.DataFrame,
    *,
    method: ImputeMethod = "cross_section_median",
    industry: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cleaned = factor.replace([np.inf, -np.inf], np.nan)
    if method == "none":
        return cleaned.copy()
    if method == "cross_section_median":
        medians = cleaned.median(axis=1, skipna=True)
        return cleaned.T.fillna(medians).T
    if method == "industry_median":
        if industry is None:
            raise ValueError("industry_median imputation requires industry data")
        raise ValueError("industry_median imputation is not implemented")
    raise ValueError(f"unknown impute method: {method}")
```

Modify `zer0factor/preprocess/__init__.py`:

```python
from zer0factor.preprocess.impute import impute_missing
from zer0factor.preprocess.winsorize import winsorize

__all__ = ["impute_missing", "winsorize"]
```

- [ ] **Step 4: Run imputation tests**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: PASS for winsorization and imputation tests.

- [ ] **Step 5: Commit imputation**

```bash
git add tests/test_preprocess.py zer0factor/preprocess/__init__.py zer0factor/preprocess/impute.py
git commit -m "feat: add factor missing value imputation"
```

## Task 3: Standardization

**Files:**
- Modify: `tests/test_preprocess.py`
- Create: `zer0factor/preprocess/standardize.py`
- Modify: `zer0factor/preprocess/__init__.py`

- [ ] **Step 1: Add failing standardization tests**

Append to `tests/test_preprocess.py`:

```python
def test_zscore_standardization_has_cross_sectional_mean_zero_and_std_one():
    from zer0factor.preprocess.standardize import standardize

    factor = _panel([[1.0, 2.0, 3.0]])

    result = standardize(factor, method="zscore")
    row = result.loc[pd.Timestamp("2024-01-01")]

    assert row.mean() == pytest.approx(0.0)
    assert row.std() == pytest.approx(1.0)


def test_zscore_standardization_returns_nan_for_zero_std_rows():
    from zer0factor.preprocess.standardize import standardize

    factor = _panel([[1.0, 1.0, 1.0]])

    result = standardize(factor, method="zscore")

    assert result.loc[pd.Timestamp("2024-01-01")].isna().all()


def test_rank_standardization_outputs_percentile_ranks():
    from zer0factor.preprocess.standardize import standardize

    factor = _panel([[10.0, 30.0, 20.0]])

    result = standardize(factor, method="rank_pct")

    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == pytest.approx(1 / 3)
    assert result.loc[pd.Timestamp("2024-01-01"), "000003.SZ"] == pytest.approx(2 / 3)
    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run standardization tests to verify failure**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'zer0factor.preprocess.standardize'`.

- [ ] **Step 3: Implement standardization**

Create `zer0factor/preprocess/standardize.py`:

```python
from __future__ import annotations

from typing import Literal

import pandas as pd


StandardizeMethod = Literal["zscore", "rank_pct", "none"]


def standardize(
    factor: pd.DataFrame,
    *,
    method: StandardizeMethod = "zscore",
) -> pd.DataFrame:
    if method == "none":
        return factor.copy()
    if method == "zscore":
        return factor.apply(_zscore_row, axis=1)
    if method == "rank_pct":
        return factor.rank(axis=1, pct=True)
    raise ValueError(f"unknown standardize method: {method}")


def _zscore_row(row: pd.Series) -> pd.Series:
    valid = row.dropna()
    if len(valid) < 2:
        return row * pd.NA
    std = valid.std()
    if pd.isna(std) or std == 0:
        return row * pd.NA
    return (row - valid.mean()) / std
```

Modify `zer0factor/preprocess/__init__.py`:

```python
from zer0factor.preprocess.impute import impute_missing
from zer0factor.preprocess.standardize import standardize
from zer0factor.preprocess.winsorize import winsorize

__all__ = ["impute_missing", "standardize", "winsorize"]
```

- [ ] **Step 4: Run standardization tests**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: PASS for winsorization, imputation, and standardization tests.

- [ ] **Step 5: Commit standardization**

```bash
git add tests/test_preprocess.py zer0factor/preprocess/__init__.py zer0factor/preprocess/standardize.py
git commit -m "feat: add factor standardization"
```

## Task 4: Neutralization Guard

**Files:**
- Modify: `tests/test_preprocess.py`
- Create: `zer0factor/preprocess/neutralize.py`
- Modify: `zer0factor/preprocess/__init__.py`

- [ ] **Step 1: Add failing neutralization tests**

Append to `tests/test_preprocess.py`:

```python
def test_size_industry_neutralization_raises_clear_not_implemented_error():
    from zer0factor.preprocess.neutralize import neutralize

    factor = _panel([[1.0, 2.0, 3.0]])

    with pytest.raises(
        ValueError,
        match="neutralization requires implemented exposure regression support",
    ):
        neutralize(factor, method="size_industry")


def test_neutralization_none_returns_copy():
    from zer0factor.preprocess.neutralize import neutralize

    factor = _panel([[1.0, 2.0, 3.0]])

    result = neutralize(factor, method="none")

    assert result is not factor
    pd.testing.assert_frame_equal(result, factor)
```

- [ ] **Step 2: Run neutralization tests to verify failure**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'zer0factor.preprocess.neutralize'`.

- [ ] **Step 3: Implement neutralization guard**

Create `zer0factor/preprocess/neutralize.py`:

```python
from __future__ import annotations

from typing import Literal

import pandas as pd


NeutralizeMethod = Literal["size_industry", "none"]


def neutralize(
    factor: pd.DataFrame,
    *,
    method: NeutralizeMethod | None = None,
    exposures: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if method in {None, "none"}:
        return factor.copy()
    if method == "size_industry":
        raise ValueError("neutralization requires implemented exposure regression support")
    raise ValueError(f"unknown neutralize method: {method}")
```

Modify `zer0factor/preprocess/__init__.py`:

```python
from zer0factor.preprocess.impute import impute_missing
from zer0factor.preprocess.neutralize import neutralize
from zer0factor.preprocess.standardize import standardize
from zer0factor.preprocess.winsorize import winsorize

__all__ = ["impute_missing", "neutralize", "standardize", "winsorize"]
```

- [ ] **Step 4: Run neutralization tests**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: PASS for current preprocessing tests.

- [ ] **Step 5: Commit neutralization guard**

```bash
git add tests/test_preprocess.py zer0factor/preprocess/__init__.py zer0factor/preprocess/neutralize.py
git commit -m "feat: add neutralization guard"
```

## Task 5: Pipeline and Config

**Files:**
- Modify: `tests/test_preprocess.py`
- Create: `zer0factor/preprocess/pipeline.py`
- Modify: `zer0factor/preprocess/__init__.py`

- [ ] **Step 1: Add failing pipeline tests**

Append to `tests/test_preprocess.py`:

```python
def test_pipeline_applies_winsorize_impute_standardize_in_fixed_order():
    from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig

    factor = _panel([[1.0, 2.0, np.nan, 100.0]])
    config = PreprocessConfig(
        winsorize_method="mad",
        winsorize_n=2.0,
        impute_method="cross_section_median",
        standardize_method="zscore",
        neutralize_method=None,
    )

    result = FactorPreprocessPipeline(config).transform(factor)

    row = result.loc[pd.Timestamp("2024-01-01")]
    assert row.mean() == pytest.approx(0.0)
    assert row.std() == pytest.approx(1.0)
    assert not row.isna().any()


def test_pipeline_long_input_returns_standard_long_output():
    from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig

    factor = pd.DataFrame(
        {
            "trade_date": ["20240101", "20240101", "20240101"],
            "ts_code": ["000002.SZ", "000001.SZ", "000003.SZ"],
            "value": [2.0, 1.0, 3.0],
        }
    )
    config = PreprocessConfig(
        winsorize_method="none",
        impute_method="none",
        standardize_method="rank_pct",
        neutralize_method=None,
    )

    result = FactorPreprocessPipeline(config).transform(factor)

    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result.to_dict("records") == [
        {"trade_date": "20240101", "ts_code": "000001.SZ", "value": pytest.approx(1 / 3)},
        {"trade_date": "20240101", "ts_code": "000002.SZ", "value": pytest.approx(2 / 3)},
        {"trade_date": "20240101", "ts_code": "000003.SZ", "value": pytest.approx(1.0)},
    ]


def test_pipeline_rejects_long_input_missing_required_columns():
    from zer0factor.preprocess import FactorPreprocessPipeline, PreprocessConfig

    factor = pd.DataFrame({"trade_date": ["20240101"], "value": [1.0]})

    with pytest.raises(ValueError, match="long factor input must contain columns"):
        FactorPreprocessPipeline(PreprocessConfig()).transform(factor)


def test_preprocess_config_rejects_invalid_quantile_bounds():
    from zer0factor.preprocess import PreprocessConfig

    with pytest.raises(ValueError, match="quantile bounds must satisfy"):
        PreprocessConfig(
            winsorize_method="quantile",
            winsorize_lower_quantile=0.9,
            winsorize_upper_quantile=0.1,
        )
```

- [ ] **Step 2: Run pipeline tests to verify failure**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: FAIL with `ImportError` for `FactorPreprocessPipeline` or `PreprocessConfig`.

- [ ] **Step 3: Implement pipeline and config**

Create `zer0factor/preprocess/pipeline.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from zer0factor.core import to_factor_output
from zer0factor.preprocess.impute import impute_missing
from zer0factor.preprocess.neutralize import neutralize
from zer0factor.preprocess.standardize import standardize
from zer0factor.preprocess.winsorize import winsorize


@dataclass(frozen=True)
class PreprocessConfig:
    winsorize_method: Literal["mad", "quantile", "none"] = "mad"
    winsorize_n: float = 5.0
    winsorize_lower_quantile: float = 0.01
    winsorize_upper_quantile: float = 0.99
    impute_method: Literal["cross_section_median", "industry_median", "none"] = (
        "cross_section_median"
    )
    standardize_method: Literal["zscore", "rank_pct", "none"] = "zscore"
    neutralize_method: Literal["size_industry", "none"] | None = None

    def __post_init__(self) -> None:
        if self.winsorize_method not in {"mad", "quantile", "none"}:
            raise ValueError(f"unknown winsorize method: {self.winsorize_method}")
        if self.winsorize_n <= 0:
            raise ValueError("winsorize_n must be positive")
        if not 0 <= self.winsorize_lower_quantile < self.winsorize_upper_quantile <= 1:
            raise ValueError("quantile bounds must satisfy 0 <= lower < upper <= 1")
        if self.impute_method not in {"cross_section_median", "industry_median", "none"}:
            raise ValueError(f"unknown impute method: {self.impute_method}")
        if self.standardize_method not in {"zscore", "rank_pct", "none"}:
            raise ValueError(f"unknown standardize method: {self.standardize_method}")
        if self.neutralize_method not in {None, "size_industry", "none"}:
            raise ValueError(f"unknown neutralize method: {self.neutralize_method}")


class FactorPreprocessPipeline:
    def __init__(self, config: PreprocessConfig | None = None):
        self.config = config or PreprocessConfig()

    def transform(
        self,
        factor: pd.DataFrame,
        *,
        industry: pd.DataFrame | None = None,
        exposures: dict[str, pd.DataFrame] | None = None,
    ) -> pd.DataFrame:
        wide, input_kind = _to_wide(factor)
        processed = winsorize(
            wide,
            method=self.config.winsorize_method,
            n=self.config.winsorize_n,
            lower_quantile=self.config.winsorize_lower_quantile,
            upper_quantile=self.config.winsorize_upper_quantile,
        )
        processed = impute_missing(
            processed,
            method=self.config.impute_method,
            industry=industry,
        )
        processed = standardize(processed, method=self.config.standardize_method)
        processed = neutralize(
            processed,
            method=self.config.neutralize_method,
            exposures=exposures,
        )
        if input_kind == "long":
            return to_factor_output(processed)
        return processed


def _to_wide(factor: pd.DataFrame) -> tuple[pd.DataFrame, Literal["wide", "long"]]:
    if not isinstance(factor, pd.DataFrame):
        raise TypeError("factor input must be a pandas DataFrame")
    required = {"trade_date", "ts_code", "value"}
    if required.intersection(factor.columns):
        if not required.issubset(factor.columns):
            raise ValueError("long factor input must contain columns: trade_date, ts_code, value")
        long = factor.loc[:, ["trade_date", "ts_code", "value"]].copy()
        long["trade_date"] = pd.to_datetime(long["trade_date"])
        wide = long.pivot(index="trade_date", columns="ts_code", values="value")
        return wide.sort_index().sort_index(axis=1), "long"
    wide = factor.copy()
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index().sort_index(axis=1), "wide"
```

Modify `zer0factor/preprocess/__init__.py`:

```python
from zer0factor.preprocess.impute import impute_missing
from zer0factor.preprocess.neutralize import neutralize
from zer0factor.preprocess.pipeline import FactorPreprocessPipeline, PreprocessConfig
from zer0factor.preprocess.standardize import standardize
from zer0factor.preprocess.winsorize import winsorize

__all__ = [
    "FactorPreprocessPipeline",
    "PreprocessConfig",
    "impute_missing",
    "neutralize",
    "standardize",
    "winsorize",
]
```

- [ ] **Step 4: Run pipeline tests**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: PASS for all preprocessing tests.

- [ ] **Step 5: Commit pipeline**

```bash
git add tests/test_preprocess.py zer0factor/preprocess/__init__.py zer0factor/preprocess/pipeline.py
git commit -m "feat: add factor preprocessing pipeline"
```

## Task 6: Final Verification

**Files:**
- No new files unless verification exposes a defect.

- [ ] **Step 1: Run preprocessing test suite**

Run: `uv run pytest tests/test_preprocess.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run existing relevant tests**

Run: `uv run pytest tests/test_factor_standard.py tests/test_daily_return_factors.py tests/test_storage.py -q`

Expected: all tests pass.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 4: Inspect git status**

Run: `git status --short`

Expected: only intentional preprocessing files are changed, plus any pre-existing user changes that were already present before implementation.

- [ ] **Step 5: Commit final fixes if needed**

If verification required small fixes, commit them:

```bash
git add tests/test_preprocess.py zer0factor/preprocess
git commit -m "test: verify factor preprocessing pipeline"
```

If no fixes were needed, do not create an empty commit.

## Self-Review Notes

- Spec coverage: winsorization, imputation, standardization, long/wide conversion, public exports, config validation, and neutralization guard are covered.
- Non-goals preserved: no changes to `Factor.compute()`, `run_factor()`, or storage layout.
- Neutralization does not produce values before exposure regression support exists.
- Implementation uses small focused files matching the approved module layout.
