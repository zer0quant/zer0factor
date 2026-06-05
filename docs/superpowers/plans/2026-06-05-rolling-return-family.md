# Rolling Return Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `rolling_return` factor family that derives 32 rolling mean return factors from stored base return factors and expands them through four migrated `zer0alpha` preprocessing profiles.

**Architecture:** Add a focused `zer0factor.factors.rolling_returns` module for rolling return names and raw derivation from `FactorStorage`. Add `zer0factor.pipeline` for `FactorFamily`, `PreprocessProfile`, raw/preprocess orchestration, and registry entry generation. Wire a new `main.py build-factors` CLI to the pipeline while keeping existing single-factor preprocessing and evaluation commands unchanged.

**Tech Stack:** Python 3.11, pandas, Click, pytest, existing `zer0factor` storage/preprocess/exposure/registry utilities, local `zer0share` for universe and industry panels.

---

## File Structure

- Create `zer0factor/factors/rolling_returns.py`
  - Owns base return factor names, rolling windows, raw rolling factor metadata, parsing, and raw factor derivation from stored base factor panels.
- Create `zer0factor/pipeline.py`
  - Owns `PreprocessProfile`, `FactorFamily`, `FAMILIES`, `get_family`, raw/preprocess build functions, registry append helpers, and small long/wide conversion helpers.
- Modify `zer0factor/factors/__init__.py`
  - Re-export rolling return helpers that are useful to tests and future callers.
- Modify `main.py`
  - Add the `build-factors` Click command and route it to `zer0factor.pipeline.run_build_stage`.
- Modify `config/factors.example.toml`
  - Add representative rolling return registry entries that document raw and profile naming.
- Create `tests/test_rolling_return_family.py`
  - Tests family metadata, profile expansion, and name parsing.
- Create `tests/test_build_rolling_return_factors.py`
  - Tests raw rolling derivation from stored base factors and profile preprocessing.
- Modify `tests/test_main.py`
  - Tests CLI dispatch and registry update behavior.

## Task 1: Rolling Return Metadata

**Files:**
- Create: `zer0factor/factors/rolling_returns.py`
- Test: `tests/test_rolling_return_family.py`
- Modify: `zer0factor/factors/__init__.py`

- [ ] **Step 1: Write failing metadata tests**

Create `tests/test_rolling_return_family.py`:

```python
from __future__ import annotations

import pytest

from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    parse_rolling_return_name,
    raw_factor_names,
)
from zer0factor.pipeline import get_family


def test_rolling_return_constants_match_design() -> None:
    assert WINDOWS == (5, 10, 20, 30, 60, 90, 120, 180)
    assert BASE_RETURN_FACTORS == (
        "daily_return",
        "open_return",
        "intraday_return",
        "overnight_return",
    )


def test_raw_factor_names_expand_to_32_in_stable_order() -> None:
    names = raw_factor_names()

    assert len(names) == 32
    assert len(set(names)) == 32
    assert names[0] == "daily_return_ma5"
    assert names[7] == "daily_return_ma180"
    assert names[8] == "open_return_ma5"
    assert names[-1] == "overnight_return_ma180"


def test_rolling_return_family_expands_profiles() -> None:
    family = get_family("rolling_return")

    assert family.raw_names() == raw_factor_names()
    assert len(family.preprocess_output_names()) == 128
    assert len(family.all_factor_names()) == 160
    assert family.all_factor_names()[0] == "daily_return_ma5"
    assert "z_daily_return_ma5" in family.all_factor_names()
    assert "z_size_neu_daily_return_ma5" in family.all_factor_names()
    assert "z_industry_neu_daily_return_ma5" in family.all_factor_names()
    assert "z_size_industry_neu_overnight_return_ma180" in family.all_factor_names()


def test_parse_rolling_return_name_handles_profiles() -> None:
    assert parse_rolling_return_name("daily_return_ma20") == {
        "base_factor": "daily_return",
        "preprocess": "raw",
        "window": 20,
    }
    assert parse_rolling_return_name("z_size_industry_neu_overnight_return_ma180") == {
        "base_factor": "overnight_return",
        "preprocess": "z_size_industry_neu",
        "window": 180,
    }


def test_parse_rolling_return_name_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown rolling return factor name"):
        parse_rolling_return_name("ma_bias_20d")
    with pytest.raises(ValueError, match="factor name does not end with _ma<window>"):
        parse_rolling_return_name("daily_return_mean20")
```

- [ ] **Step 2: Run metadata tests and verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_rolling_return_family.py -q
```

Expected: FAIL because `zer0factor.factors.rolling_returns` and `zer0factor.pipeline` do not exist.

- [ ] **Step 3: Implement rolling return metadata**

Create `zer0factor/factors/rolling_returns.py`:

```python
from __future__ import annotations

import pandas as pd

from zer0factor.core import to_factor_output

WINDOWS = (5, 10, 20, 30, 60, 90, 120, 180)
BASE_RETURN_FACTORS = (
    "daily_return",
    "open_return",
    "intraday_return",
    "overnight_return",
)

PROFILE_PREFIXES = (
    ("z_size_industry_neu_", "z_size_industry_neu"),
    ("z_industry_neu_", "z_industry_neu"),
    ("z_size_neu_", "z_size_neu"),
    ("z_", "z"),
)


def raw_factor_names() -> tuple[str, ...]:
    return tuple(
        f"{base_factor}_ma{window}"
        for base_factor in BASE_RETURN_FACTORS
        for window in WINDOWS
    )


def parse_rolling_return_name(factor_name: str) -> dict[str, int | str]:
    preprocess = "raw"
    raw_name = factor_name
    for prefix, profile in PROFILE_PREFIXES:
        if factor_name.startswith(prefix):
            preprocess = profile
            raw_name = factor_name[len(prefix):]
            break

    base_factor = next(
        (name for name in BASE_RETURN_FACTORS if raw_name.startswith(f"{name}_ma")),
        None,
    )
    if base_factor is None:
        raise ValueError(f"unknown rolling return factor name: {factor_name}")

    suffix = raw_name.removeprefix(f"{base_factor}_ma")
    if not suffix.isdigit():
        raise ValueError(f"factor name does not end with _ma<window>: {factor_name}")

    return {
        "base_factor": base_factor,
        "preprocess": preprocess,
        "window": int(suffix),
    }


def derive_rolling_mean_panel(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    return panel.rolling(window=window, min_periods=window // 2).mean()


def derive_rolling_mean_output(
    panel: pd.DataFrame,
    *,
    base_factor: str,
    window: int,
) -> pd.DataFrame:
    return to_factor_output(
        derive_rolling_mean_panel(panel, window),
        f"{base_factor}_ma{window}",
    )


__all__ = [
    "BASE_RETURN_FACTORS",
    "PROFILE_PREFIXES",
    "WINDOWS",
    "derive_rolling_mean_output",
    "derive_rolling_mean_panel",
    "parse_rolling_return_name",
    "raw_factor_names",
]
```

- [ ] **Step 4: Implement minimal family registry**

Create `zer0factor/pipeline.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from zer0factor.factors.rolling_returns import raw_factor_names


@dataclass(frozen=True)
class PreprocessProfile:
    key: str
    prefix: str
    neutralize_method: str | None

    def output_name(self, raw_factor_name: str) -> str:
        return f"{self.prefix}{raw_factor_name}"


PROFILES = (
    PreprocessProfile("z", "z_", None),
    PreprocessProfile("z_size_neu", "z_size_neu_", "size"),
    PreprocessProfile("z_industry_neu", "z_industry_neu_", "industry"),
    PreprocessProfile("z_size_industry_neu", "z_size_industry_neu_", "size_industry"),
)


@dataclass(frozen=True)
class FactorFamily:
    name: str
    raw_names: Callable[[], tuple[str, ...]]
    profiles: tuple[PreprocessProfile, ...] = PROFILES

    def preprocess_output_names(self) -> list[str]:
        return [
            profile.output_name(raw_name)
            for raw_name in self.raw_names()
            for profile in self.profiles
        ]

    def all_factor_names(self) -> list[str]:
        return [*self.raw_names(), *self.preprocess_output_names()]


FAMILIES = {
    "rolling_return": FactorFamily(
        name="rolling_return",
        raw_names=raw_factor_names,
    ),
}


def get_family(family_name: str) -> FactorFamily:
    if family_name not in FAMILIES:
        raise ValueError(
            f"unknown factor family: {family_name!r}. Known: {sorted(FAMILIES)}"
        )
    return FAMILIES[family_name]


__all__ = [
    "FAMILIES",
    "PROFILES",
    "FactorFamily",
    "PreprocessProfile",
    "get_family",
]
```

- [ ] **Step 5: Export rolling return helpers**

Modify `zer0factor/factors/__init__.py` by adding:

```python
from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    parse_rolling_return_name,
    raw_factor_names,
)
```

Add these names to `__all__`:

```python
"BASE_RETURN_FACTORS",
"WINDOWS",
"parse_rolling_return_name",
"raw_factor_names",
```

- [ ] **Step 6: Run metadata tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_rolling_return_family.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit metadata task**

Run:

```bash
git add zer0factor/factors/rolling_returns.py zer0factor/pipeline.py zer0factor/factors/__init__.py tests/test_rolling_return_family.py
git commit -m "feat: add rolling return family metadata"
```

## Task 2: Raw Rolling Derivation From Stored Base Factors

**Files:**
- Modify: `zer0factor/pipeline.py`
- Test: `tests/test_build_rolling_return_factors.py`

- [ ] **Step 1: Write failing raw derivation tests**

Create `tests/test_build_rolling_return_factors.py`:

```python
from __future__ import annotations

import pandas as pd
import pytest

from zer0factor.pipeline import (
    _long_to_wide,
    compute_raw_rolling_return_factors,
)


class FakeStorage:
    def __init__(self, frames: dict[str, pd.DataFrame] | None = None) -> None:
        self.frames = frames or {}
        self.writes: dict[str, pd.DataFrame] = {}

    def read(
        self,
        factor_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        if factor_name not in self.frames:
            raise FileNotFoundError(f"Factor '{factor_name}' not found")
        frame = self.frames[factor_name].copy()
        if start_date is not None:
            frame = frame[frame["trade_date"] >= start_date]
        if end_date is not None:
            frame = frame[frame["trade_date"] <= end_date]
        return frame.reset_index(drop=True)

    def write(self, factor_name: str, df: pd.DataFrame) -> None:
        self.writes[factor_name] = df.copy()


def _base_factor(values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(values), freq="D")
    rows = []
    for date, value in zip(dates, values, strict=True):
        rows.append({
            "trade_date": date.strftime("%Y%m%d"),
            "ts_code": "000001.SZ",
            "value": value,
        })
    return pd.DataFrame(rows)


def test_compute_raw_rolling_return_factors_derives_from_stored_base_factors() -> None:
    storage = FakeStorage({
        "daily_return": _base_factor([1.0, 2.0, 3.0, 4.0, 5.0]),
        "open_return": _base_factor([10.0, 20.0, 30.0, 40.0, 50.0]),
        "intraday_return": _base_factor([2.0, 4.0, 6.0, 8.0, 10.0]),
        "overnight_return": _base_factor([5.0, 4.0, 3.0, 2.0, 1.0]),
    })

    rows = compute_raw_rolling_return_factors(
        storage=storage,
        start_date="20240101",
        end_date="20240105",
        windows=(5,),
    )

    assert set(rows) == {
        "daily_return_ma5",
        "open_return_ma5",
        "intraday_return_ma5",
        "overnight_return_ma5",
    }
    daily = storage.writes["daily_return_ma5"]
    assert list(daily.columns) == ["trade_date", "ts_code", "value"]
    assert daily["trade_date"].tolist() == ["20240103", "20240104", "20240105"]
    assert daily["value"].tolist() == [2.0, 2.5, 3.0]


def test_compute_raw_rolling_return_factors_fails_when_base_factor_missing() -> None:
    storage = FakeStorage({
        "daily_return": _base_factor([1.0, 2.0, 3.0]),
    })

    with pytest.raises(FileNotFoundError, match="required factor missing: open_return"):
        compute_raw_rolling_return_factors(
            storage=storage,
            start_date=None,
            end_date=None,
            windows=(5,),
        )


def test_long_to_wide_rejects_duplicate_trade_date_code_pairs() -> None:
    frame = pd.DataFrame({
        "trade_date": ["20240101", "20240101"],
        "ts_code": ["000001.SZ", "000001.SZ"],
        "value": [1.0, 2.0],
    })

    with pytest.raises(ValueError, match="factor data contains duplicate trade_date/ts_code"):
        _long_to_wide(frame)
```

- [ ] **Step 2: Run raw derivation tests and verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: FAIL because `compute_raw_rolling_return_factors` and `_long_to_wide` are not implemented.

- [ ] **Step 3: Add conversion and raw derivation helpers**

Modify `zer0factor/pipeline.py` by adding imports:

```python
import logging
from typing import Any

import pandas as pd

from zer0factor.core import to_factor_output
from zer0factor.factors.rolling_returns import (
    BASE_RETURN_FACTORS,
    WINDOWS,
    derive_rolling_mean_panel,
)
```

Add this module constant:

```python
LOGGER = logging.getLogger(__name__)
```

Add these functions:

```python
def compute_raw_rolling_return_factors(
    *,
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    windows: tuple[int, ...] = WINDOWS,
) -> dict[str, int]:
    rows: dict[str, int] = {}
    for base_factor in BASE_RETURN_FACTORS:
        source = _read_required_factor(storage, base_factor, start_date, end_date)
        panel = _long_to_wide(source)
        for window in windows:
            output_name = f"{base_factor}_ma{window}"
            output_panel = derive_rolling_mean_panel(panel, window)
            output = to_factor_output(output_panel, output_name)
            if output.empty:
                LOGGER.warning("rolling factor output is empty: %s", output_name)
            storage.write(output_name, output)
            rows[output_name] = len(output)
    return rows


def _read_required_factor(
    storage: Any,
    factor_name: str,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    try:
        return storage.read(factor_name, start_date=start_date, end_date=end_date)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required factor missing: {factor_name}") from exc


def _long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "ts_code", "value"}
    if not required.issubset(df.columns):
        raise ValueError(f"factor data must contain columns: {sorted(required)}")
    frame = df.loc[:, ["trade_date", "ts_code", "value"]].copy()
    frame["trade_date"] = _parse_trade_dates(frame["trade_date"])
    if frame.duplicated(["trade_date", "ts_code"]).any():
        raise ValueError("factor data contains duplicate trade_date/ts_code")
    return (
        frame.pivot(index="trade_date", columns="ts_code", values="value")
        .sort_index()
        .sort_index(axis=1)
    )


def _wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    return to_factor_output(df)


def _parse_trade_dates(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d")
    return pd.to_datetime(values)
```

Add `compute_raw_rolling_return_factors` to `__all__`.

- [ ] **Step 4: Run raw derivation tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: PASS.

- [ ] **Step 5: Run metadata regression**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_rolling_return_family.py tests/test_build_rolling_return_factors.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit raw derivation task**

Run:

```bash
git add zer0factor/pipeline.py tests/test_build_rolling_return_factors.py
git commit -m "feat: derive rolling return factors from storage"
```

## Task 3: Four-Profile Preprocessing Pipeline

**Files:**
- Modify: `zer0factor/pipeline.py`
- Test: `tests/test_build_rolling_return_factors.py`

- [ ] **Step 1: Add failing preprocessing tests**

Append to `tests/test_build_rolling_return_factors.py`:

```python
from zer0factor.pipeline import SIZE_FACTOR_NAME, preprocess_one_factor


def _cross_section_factor() -> pd.DataFrame:
    codes = [
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
        "000004.SZ",
        "000005.SZ",
        "000006.SZ",
    ]
    return pd.DataFrame({
        "trade_date": ["20240101"] * 6,
        "ts_code": codes,
        "value": [1.0, 2.0, 4.0, 6.0, 8.0, 10.0],
    })


def _size_factor() -> pd.DataFrame:
    codes = [
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
        "000004.SZ",
        "000005.SZ",
        "000006.SZ",
    ]
    return pd.DataFrame({
        "trade_date": ["20240101"] * 6,
        "ts_code": codes,
        "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    })


def _industry_panel() -> pd.DataFrame:
    return pd.DataFrame(
        [["bank", "bank", "tech", "tech", "energy", "energy"]],
        index=pd.to_datetime(["2024-01-01"]),
        columns=[
            "000001.SZ",
            "000002.SZ",
            "000003.SZ",
            "000004.SZ",
            "000005.SZ",
            "000006.SZ",
        ],
    )


def test_preprocess_one_factor_writes_four_profiles() -> None:
    storage = FakeStorage({
        "daily_return_ma5": _cross_section_factor(),
        SIZE_FACTOR_NAME: _size_factor(),
    })

    rows = preprocess_one_factor(
        "daily_return_ma5",
        storage=storage,
        industry_panel=_industry_panel(),
    )

    assert set(rows) == {
        "z_daily_return_ma5",
        "z_size_neu_daily_return_ma5",
        "z_industry_neu_daily_return_ma5",
        "z_size_industry_neu_daily_return_ma5",
    }
    assert set(storage.writes) == set(rows)
    assert all(
        list(frame.columns) == ["trade_date", "ts_code", "value"]
        for frame in storage.writes.values()
    )
    assert all(not frame.empty for frame in storage.writes.values())


def test_preprocess_one_factor_fails_when_raw_factor_missing() -> None:
    storage = FakeStorage({SIZE_FACTOR_NAME: _size_factor()})

    with pytest.raises(FileNotFoundError, match="required factor missing: daily_return_ma5"):
        preprocess_one_factor(
            "daily_return_ma5",
            storage=storage,
            industry_panel=_industry_panel(),
        )
```

- [ ] **Step 2: Run preprocessing tests and verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: FAIL because `preprocess_one_factor` and `SIZE_FACTOR_NAME` are not implemented.

- [ ] **Step 3: Implement profile preprocessing**

Modify `zer0factor/pipeline.py` imports:

```python
from zer0factor.preprocess import impute_missing, neutralize, standardize, winsorize
```

Add constant:

```python
SIZE_FACTOR_NAME = "z_log_circulating_market_cap"
```

Add functions:

```python
def preprocess_one_factor(
    raw_factor_name: str,
    *,
    storage: Any,
    industry_panel: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
    universe: pd.DataFrame | None = None,
    profiles: tuple[PreprocessProfile, ...] = PROFILES,
) -> dict[str, int]:
    raw = _read_required_factor(storage, raw_factor_name, start_date, end_date)
    size = _read_required_factor(storage, SIZE_FACTOR_NAME, start_date, end_date)

    raw_panel = _filter_panel_by_universe(_long_to_wide(raw), universe)
    size_panel = _long_to_wide(size).reindex(index=raw_panel.index, columns=raw_panel.columns)
    aligned_industry = industry_panel.reindex(index=raw_panel.index, columns=raw_panel.columns)

    base = _winsorize_impute_zscore(raw_panel)
    rows: dict[str, int] = {}
    for profile in profiles:
        output_name = profile.output_name(raw_factor_name)
        if profile.neutralize_method is None:
            output_panel = base
        else:
            output_panel = _neutralize_then_zscore(
                base,
                method=profile.neutralize_method,
                size=size_panel,
                industry=aligned_industry,
            )
        output = _wide_to_long(output_panel)
        storage.write(output_name, output)
        rows[output_name] = len(output)
    return rows


def _winsorize_impute_zscore(panel: pd.DataFrame) -> pd.DataFrame:
    processed = winsorize(panel, method="mad", n=5.0)
    processed = impute_missing(processed, method="cross_section_median")
    return standardize(processed, method="zscore")


def _neutralize_then_zscore(
    panel: pd.DataFrame,
    *,
    method: str,
    size: pd.DataFrame,
    industry: pd.DataFrame,
) -> pd.DataFrame:
    exposures = {"size": size, "industry": industry}
    neutralized = neutralize(panel, method=method, exposures=exposures)
    return standardize(neutralized, method="zscore")


def _filter_panel_by_universe(
    panel: pd.DataFrame,
    universe: pd.DataFrame | None,
) -> pd.DataFrame:
    if universe is None:
        return panel
    aligned = universe.reindex(index=panel.index, columns=panel.columns, fill_value=False)
    return panel.where(aligned.astype(bool)).dropna(axis=1, how="all")
```

Add `SIZE_FACTOR_NAME` and `preprocess_one_factor` to `__all__`.

- [ ] **Step 4: Run preprocessing tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: PASS.

- [ ] **Step 5: Run focused preprocessing regressions**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py tests/test_preprocess.py tests/test_exposures.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit preprocessing task**

Run:

```bash
git add zer0factor/pipeline.py tests/test_build_rolling_return_factors.py
git commit -m "feat: preprocess rolling return profiles"
```

## Task 4: Build Stage Orchestration

**Files:**
- Modify: `zer0factor/pipeline.py`
- Test: `tests/test_build_rolling_return_factors.py`

- [ ] **Step 1: Add failing orchestration tests**

Append to `tests/test_build_rolling_return_factors.py`:

```python
from zer0factor.pipeline import run_build_stage


def test_run_build_stage_raw_dispatches_raw_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_raw(**kwargs):
        calls.append("raw")
        return {"daily_return_ma5": 3}

    monkeypatch.setattr("zer0factor.pipeline.compute_raw_rolling_return_factors", fake_raw)

    rows = run_build_stage(
        "rolling_return",
        "raw",
        storage=FakeStorage(),
        start_date="20240101",
        end_date="20240105",
    )

    assert calls == ["raw"]
    assert rows == {"daily_return_ma5": 3}


def test_run_build_stage_all_runs_raw_then_preprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_raw(**kwargs):
        calls.append("raw")
        return {"daily_return_ma5": 3}

    def fake_preprocess_all(**kwargs):
        calls.append("preprocess")
        return {"z_daily_return_ma5": 3}

    monkeypatch.setattr("zer0factor.pipeline.compute_raw_rolling_return_factors", fake_raw)
    monkeypatch.setattr("zer0factor.pipeline.preprocess_all_factors", fake_preprocess_all)

    rows = run_build_stage(
        "rolling_return",
        "all",
        storage=FakeStorage(),
        pro=object(),
        start_date="20240101",
        end_date="20240105",
        process_universe="univ_trade_base",
    )

    assert calls == ["raw", "preprocess"]
    assert rows == {"daily_return_ma5": 3, "z_daily_return_ma5": 3}


def test_run_build_stage_rejects_unknown_family() -> None:
    with pytest.raises(ValueError, match="unknown factor family"):
        run_build_stage(
            "unknown",
            "raw",
            storage=FakeStorage(),
            start_date=None,
            end_date=None,
        )
```

- [ ] **Step 2: Run orchestration tests and verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: FAIL because `run_build_stage` and `preprocess_all_factors` are not implemented.

- [ ] **Step 3: Implement all-factor preprocessing and build stage**

Modify `zer0factor/pipeline.py` imports:

```python
from zer0factor.exposures import build_sw_l1_industry_panel
```

Add functions:

```python
def preprocess_all_factors(
    raw_names: list[str],
    *,
    storage: Any,
    pro: Any,
    start_date: str | None,
    end_date: str | None,
    process_universe: str,
    profiles: tuple[PreprocessProfile, ...] = PROFILES,
) -> dict[str, int]:
    universe = _read_universe_panel(
        pro,
        universe_name=process_universe,
        start_date=start_date,
        end_date=end_date,
    )
    if universe.empty:
        raise ValueError("process universe returned no rows")

    raw_panels = [
        _filter_panel_by_universe(
            _long_to_wide(_read_required_factor(storage, name, start_date, end_date)),
            universe,
        )
        for name in raw_names
    ]
    raw_dates = raw_panels[0].index
    raw_codes = raw_panels[0].columns
    for panel in raw_panels[1:]:
        raw_dates = raw_dates.union(panel.index)
        raw_codes = raw_codes.union(panel.columns)

    industry_panel = build_sw_l1_industry_panel(pro, dates=raw_dates, ts_codes=raw_codes)
    rows: dict[str, int] = {}
    for raw_name in raw_names:
        rows.update(
            preprocess_one_factor(
                raw_name,
                storage=storage,
                industry_panel=industry_panel,
                start_date=start_date,
                end_date=end_date,
                universe=universe,
                profiles=profiles,
            )
        )
    return rows


def run_build_stage(
    family_name: str,
    stage: str,
    *,
    storage: Any,
    pro: Any | None = None,
    start_date: str | None,
    end_date: str | None,
    process_universe: str | None = None,
) -> dict[str, int]:
    family = get_family(family_name)
    if stage not in {"raw", "preprocess", "all"}:
        raise ValueError(f"unknown build stage: {stage}")

    rows: dict[str, int] = {}
    if stage in {"raw", "all"}:
        rows.update(
            compute_raw_rolling_return_factors(
                storage=storage,
                start_date=start_date,
                end_date=end_date,
            )
        )
    if stage in {"preprocess", "all"}:
        if pro is None:
            raise ValueError("pro is required for preprocess stage")
        if process_universe is None:
            raise ValueError("process_universe is required for preprocess stage")
        rows.update(
            preprocess_all_factors(
                list(family.raw_names()),
                storage=storage,
                pro=pro,
                start_date=start_date,
                end_date=end_date,
                process_universe=process_universe,
                profiles=family.profiles,
            )
        )
    return rows
```

Add `_read_universe_panel`:

```python
def _read_universe_panel(
    pro: Any,
    *,
    universe_name: str,
    start_date: str | None,
    end_date: str | None,
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
    frame["trade_date"] = _parse_trade_dates(frame["trade_date"])
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

Add `preprocess_all_factors` and `run_build_stage` to `__all__`.

- [ ] **Step 4: Run orchestration tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: PASS.

- [ ] **Step 5: Run pipeline-focused suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_rolling_return_family.py tests/test_build_rolling_return_factors.py tests/test_preprocess.py tests/test_exposures.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit orchestration task**

Run:

```bash
git add zer0factor/pipeline.py tests/test_build_rolling_return_factors.py
git commit -m "feat: orchestrate rolling return build stages"
```

## Task 5: Registry Entry Generation and Append

**Files:**
- Modify: `zer0factor/pipeline.py`
- Modify: `config/factors.example.toml`
- Test: `tests/test_build_rolling_return_factors.py`

- [ ] **Step 1: Add failing registry tests**

Append to `tests/test_build_rolling_return_factors.py`:

```python
from pathlib import Path

from zer0factor.pipeline import update_factor_registry


def test_update_factor_registry_appends_missing_entries_without_overwriting(tmp_path: Path) -> None:
    registry = tmp_path / "factors.toml"
    registry.write_text(
        """
[registry]
version = "1"

[[factors]]
name = "z_daily_return_ma5"
category = "custom"
source_type = "derived"
source_factor = "daily_return_ma5"
enabled = false
tags = ["custom"]
description = "User customized entry"
""".lstrip(),
        encoding="utf-8",
    )

    added = update_factor_registry(registry, family_name="rolling_return")
    content = registry.read_text(encoding="utf-8")

    assert "User customized entry" in content
    assert content.count('name = "z_daily_return_ma5"') == 1
    assert "daily_return_ma5" in added
    assert "z_size_industry_neu_overnight_return_ma180" in added
    assert 'name = "z_size_industry_neu_overnight_return_ma180"' in content


def test_update_factor_registry_creates_registry_header(tmp_path: Path) -> None:
    registry = tmp_path / "factors.toml"

    update_factor_registry(registry, family_name="rolling_return")
    content = registry.read_text(encoding="utf-8")

    assert '[registry]' in content
    assert 'version = "1"' in content
    assert 'name = "daily_return_ma5"' in content
    assert 'enabled = false' in content
    assert 'name = "z_daily_return_ma5"' in content
    assert 'enabled = true' in content
```

- [ ] **Step 2: Run registry tests and verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py -q
```

Expected: FAIL because `update_factor_registry` is not implemented.

- [ ] **Step 3: Implement registry append helpers**

Modify `zer0factor/pipeline.py` imports:

```python
import tomllib
from pathlib import Path
```

Add functions:

```python
def update_factor_registry(registry_path: Path, *, family_name: str) -> list[str]:
    family = get_family(family_name)
    existing = _read_registry_names(registry_path)
    entries = _registry_entries_for_family(family)
    missing = [entry for entry in entries if entry["name"] not in existing]
    if not missing:
        return []

    if registry_path.exists():
        prefix = registry_path.read_text(encoding="utf-8").rstrip() + "\n\n"
    else:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = '# Factor Registry\n\n[registry]\nversion = "1"\n\n'

    body = "\n\n".join(_format_registry_entry(entry) for entry in missing)
    registry_path.write_text(prefix + body + "\n", encoding="utf-8")
    return [entry["name"] for entry in missing]


def _read_registry_names(registry_path: Path) -> set[str]:
    if not registry_path.exists():
        return set()
    with open(registry_path, "rb") as f:
        raw = tomllib.load(f)
    return {str(entry["name"]) for entry in raw.get("factors", [])}


def _registry_entries_for_family(family: FactorFamily) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for raw_name in family.raw_names():
        parsed = _parse_raw_name_for_registry(raw_name)
        entries.append({
            "name": raw_name,
            "category": "price",
            "source_type": "derived",
            "source_factor": parsed["base_factor"],
            "enabled": False,
            "tags": [
                "rolling_return",
                parsed["base_factor"],
                "ma",
                f"ma{parsed['window']}",
                "raw",
            ],
            "description": f"Rolling mean of {parsed['base_factor']} over {parsed['window']} trading days",
            "evaluate_default": False,
        })
        for profile in family.profiles:
            profile_name = profile.output_name(raw_name)
            entries.append({
                "name": profile_name,
                "category": "price",
                "source_type": "derived" if profile.neutralize_method is None else "neutralized",
                "source_factor": raw_name,
                "enabled": True,
                "tags": [
                    "rolling_return",
                    parsed["base_factor"],
                    "ma",
                    f"ma{parsed['window']}",
                    profile.key,
                ],
                "description": f"{profile.key} profile for {raw_name}",
                "evaluate_default": True,
            })
    return entries


def _parse_raw_name_for_registry(raw_name: str) -> dict[str, int | str]:
    for base_factor in BASE_RETURN_FACTORS:
        prefix = f"{base_factor}_ma"
        if raw_name.startswith(prefix):
            suffix = raw_name.removeprefix(prefix)
            if suffix.isdigit():
                return {"base_factor": base_factor, "window": int(suffix)}
    raise ValueError(f"unknown rolling return raw factor name: {raw_name}")


def _format_registry_entry(entry: dict[str, object]) -> str:
    lines = [
        "[[factors]]",
        f'name = "{entry["name"]}"',
        f'category = "{entry["category"]}"',
        f'source_type = "{entry["source_type"]}"',
        f'source_factor = "{entry["source_factor"]}"',
        f'enabled = {str(entry["enabled"]).lower()}',
        "tags = [" + ", ".join(f'"{tag}"' for tag in entry["tags"]) + "]",
        f'description = "{entry["description"]}"',
        "",
        "[factors.evaluate]",
        f'default = {str(entry["evaluate_default"]).lower()}',
        "quantiles = 5",
        "periods = [1, 5, 10]",
        'return_type = "open_t1"',
    ]
    return "\n".join(lines)
```

Add `update_factor_registry` to `__all__`.

- [ ] **Step 4: Update `config/factors.example.toml`**

Append these representative entries to `config/factors.example.toml`:

```toml
[[factors]]
name = "daily_return_ma5"
category = "price"
source_type = "derived"
source_factor = "daily_return"
enabled = false
tags = ["rolling_return", "daily_return", "ma", "ma5", "raw"]
description = "Rolling mean of daily_return over 5 trading days"

[factors.evaluate]
default = false
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"

[[factors]]
name = "z_size_industry_neu_daily_return_ma5"
category = "price"
source_type = "neutralized"
source_factor = "daily_return_ma5"
enabled = true
tags = ["rolling_return", "daily_return", "ma", "ma5", "z_size_industry_neu"]
description = "z_size_industry_neu profile for daily_return_ma5"

[factors.evaluate]
default = true
quantiles = 5
periods = [1, 5, 10]
return_type = "open_t1"
```

- [ ] **Step 5: Run registry tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_build_rolling_return_factors.py tests/test_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit registry task**

Run:

```bash
git add zer0factor/pipeline.py config/factors.example.toml tests/test_build_rolling_return_factors.py
git commit -m "feat: add rolling return registry updates"
```

## Task 6: CLI Integration

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing CLI tests**

Append to `tests/test_main.py`:

```python
def test_build_factors_command_runs_stage_and_prints_rows(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from main import cli

    config_path = tmp_path / "settings.toml"
    config_path.write_text(
        f"""
[zer0share]
data_dir = "{tmp_path / 'share'}"

[paths]
factor_dir = "{tmp_path / 'factors'}"
db_path = "{tmp_path / 'factor.duckdb'}"
log_path = "{tmp_path / 'factor.log'}"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20240101"
end_date = ""
""".lstrip(),
        encoding="utf-8",
    )
    calls = []

    def fake_run_build_stage(**kwargs):
        calls.append(kwargs)
        return {"daily_return_ma5": 3, "z_daily_return_ma5": 3}

    monkeypatch.setattr("main.run_build_stage", fake_run_build_stage)

    result = CliRunner().invoke(
        cli,
        [
            "--config",
            str(config_path),
            "build-factors",
            "--family",
            "rolling_return",
            "--stage",
            "all",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["family_name"] == "rolling_return"
    assert calls[0]["stage"] == "all"
    assert calls[0]["start_date"] == "20240101"
    assert calls[0]["end_date"] is None
    assert "daily_return_ma5: 3" in result.output
    assert "z_daily_return_ma5: 3" in result.output


def test_build_factors_command_updates_registry_when_requested(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from main import cli

    config_path = tmp_path / "settings.toml"
    registry_path = tmp_path / "factors.toml"
    config_path.write_text(
        f"""
[zer0share]
data_dir = "{tmp_path / 'share'}"

[paths]
factor_dir = "{tmp_path / 'factors'}"
db_path = "{tmp_path / 'factor.duckdb'}"
log_path = "{tmp_path / 'factor.log'}"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20240101"
end_date = ""
""".lstrip(),
        encoding="utf-8",
    )
    registry_calls = []

    monkeypatch.setattr("main.run_build_stage", lambda **kwargs: {"daily_return_ma5": 3})
    monkeypatch.setattr(
        "main.update_factor_registry",
        lambda path, family_name: registry_calls.append((path, family_name)) or ["daily_return_ma5"],
    )

    result = CliRunner().invoke(
        cli,
        [
            "--config",
            str(config_path),
            "build-factors",
            "--family",
            "rolling_return",
            "--stage",
            "raw",
            "--registry",
            str(registry_path),
            "--update-registry",
        ],
    )

    assert result.exit_code == 0
    assert registry_calls == [(registry_path, "rolling_return")]
    assert "registry entries added: 1" in result.output
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_main.py::test_build_factors_command_runs_stage_and_prints_rows tests/test_main.py::test_build_factors_command_updates_registry_when_requested -q
```

Expected: FAIL because `build-factors` command and `main.run_build_stage` imports are missing.

- [ ] **Step 3: Add imports to `main.py`**

Add near existing imports:

```python
from zer0factor.pipeline import run_build_stage, update_factor_registry
```

- [ ] **Step 4: Add `build-factors` command to `main.py`**

Add after `compute_market_cap` or before single-factor preprocessing commands:

```python
@cli.command("build-factors")
@click.option("--family", "family_name", required=True, help="Factor family to build")
@click.option(
    "--stage",
    type=click.Choice(["raw", "preprocess", "all"]),
    default="all",
    show_default=True,
)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--registry", "registry_path", default="config/factors.toml", show_default=True)
@click.option("--update-registry", is_flag=True, default=False)
@click.pass_context
def build_factors_command(
    ctx,
    family_name,
    stage,
    start_date,
    end_date,
    registry_path,
    update_registry,
):
    """Build a registered factor family."""
    from zer0share.api import LocalPro

    cfg = load_config(ctx.obj["config_path"])
    configure_logging(cfg.log_path)
    resolved_start = start_date or cfg.start_date
    resolved_end = end_date if end_date is not None else (cfg.end_date or None)
    storage = FactorStorage(cfg.factor_dir, cfg.db_path)
    pro = LocalPro(cfg.zer0share_data_dir) if stage in {"preprocess", "all"} else None

    rows = run_build_stage(
        family_name=family_name,
        stage=stage,
        storage=storage,
        pro=pro,
        start_date=resolved_start,
        end_date=resolved_end,
        process_universe=cfg.process_universe,
    )
    for factor_name, row_count in rows.items():
        click.echo(f"{factor_name}: {row_count}")

    if update_registry:
        added = update_factor_registry(Path(registry_path), family_name=family_name)
        click.echo(f"registry entries added: {len(added)}")
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_main.py::test_build_factors_command_runs_stage_and_prints_rows tests/test_main.py::test_build_factors_command_updates_registry_when_requested -q
```

Expected: PASS.

- [ ] **Step 6: Run full focused suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/test_rolling_return_family.py tests/test_build_rolling_return_factors.py tests/test_main.py tests/test_registry.py tests/test_preprocess.py tests/test_exposures.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit CLI task**

Run:

```bash
git add main.py tests/test_main.py
git commit -m "feat: add factor family build command"
```

## Task 7: Final Verification

**Files:**
- No new files
- Verify all modified files

- [ ] **Step 1: Run lint**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run ruff check zer0factor tests main.py
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests -q
```

Expected: PASS.

- [ ] **Step 3: Check build command help**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python main.py build-factors --help
```

Expected: help output includes `--family`, `--stage`, `--registry`, and `--update-registry`.

- [ ] **Step 4: Inspect git status**

Run:

```bash
git status --short
```

Expected: no unstaged changes except intentionally uncommitted verification artifacts. If there are source changes, commit them with a specific message.

