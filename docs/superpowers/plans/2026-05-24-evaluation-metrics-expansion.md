# Evaluation Metrics Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 alphalens `clean_factor_data` 基础上扩展四类新指标：IC 分频胜率、分组收益时序指标（年化/回撤/卡玛/夏普）、换手率、季度单调性稳定性，并支持可选指数超额收益。

**Architecture:** 将 `zer0factor/eval/metrics.py` 拆为子包 `metrics/`，各指标类型独立模块，`metrics/__init__.py` 保持对外接口不变。`build_summary` 新增可选参数 `clean_factor_data` 和 `index_returns`，有值时追加扩展列，无值时行为与现在完全一致。

**Tech Stack:** Python 3.11+, pandas, alphalens-reloaded (`alphalens.performance.mean_return_by_quantile`, `factor_information_coefficient`), pytest, numpy

---

## 文件清单

| 操作 | 路径 |
|---|---|
| 创建 | `zer0factor/eval/metrics/__init__.py` |
| 创建 | `zer0factor/eval/metrics/ic.py` |
| 创建 | `zer0factor/eval/metrics/returns.py` |
| 创建 | `zer0factor/eval/metrics/turnover.py` |
| 创建 | `zer0factor/eval/metrics/monotonicity.py` |
| 删除 | `zer0factor/eval/metrics.py` |
| 修改 | `zer0factor/eval/loaders.py` |
| 修改 | `zer0factor/eval/config.py` |
| 修改 | `zer0factor/eval/pipeline.py` |
| 修改 | `zer0factor/eval/report.py` |
| 修改 | `main.py` |
| 修改 | `tests/test_eval_metrics.py` |
| 创建 | `tests/test_eval_metrics_ic.py` |
| 创建 | `tests/test_eval_metrics_returns.py` |
| 创建 | `tests/test_eval_metrics_turnover.py` |
| 创建 | `tests/test_eval_metrics_monotonicity.py` |

---

## Task 1: 将 `metrics.py` 重构为 `metrics/` 子包

**Files:**
- 创建: `zer0factor/eval/metrics/__init__.py`
- 创建: `zer0factor/eval/metrics/ic.py`（空）
- 创建: `zer0factor/eval/metrics/returns.py`（空）
- 创建: `zer0factor/eval/metrics/turnover.py`（空）
- 创建: `zer0factor/eval/metrics/monotonicity.py`（空）
- 删除: `zer0factor/eval/metrics.py`
- 修改: `tests/test_eval_metrics.py`

- [ ] **Step 1: 确认现有测试通过**

```bash
cd /data/zer0factor && uv run pytest tests/test_eval_metrics.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 2: 创建 `metrics/` 目录，将 `metrics.py` 内容复制到 `metrics/__init__.py`**

```bash
mkdir -p zer0factor/eval/metrics
cp zer0factor/eval/metrics.py zer0factor/eval/metrics/__init__.py
```

- [ ] **Step 3: 创建空子模块**

创建 `zer0factor/eval/metrics/ic.py`：
```python
from __future__ import annotations
```

创建 `zer0factor/eval/metrics/returns.py`：
```python
from __future__ import annotations
```

创建 `zer0factor/eval/metrics/turnover.py`：
```python
from __future__ import annotations
```

创建 `zer0factor/eval/metrics/monotonicity.py`：
```python
from __future__ import annotations
```

- [ ] **Step 4: 删除旧的 `metrics.py`**

```bash
rm zer0factor/eval/metrics.py
```

- [ ] **Step 5: 更新 `tests/test_eval_metrics.py` 的列断言为子集检查**

将：
```python
assert result.columns.tolist() == EXPECTED_SUMMARY_COLUMNS
```
改为：
```python
assert all(col in result.columns for col in EXPECTED_SUMMARY_COLUMNS)
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
uv run pytest tests/test_eval_metrics.py tests/test_eval_pipeline.py tests/test_eval_report.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 7: Commit**

```bash
git add zer0factor/eval/metrics/ zer0factor/eval/metrics.py tests/test_eval_metrics.py
git commit -m "refactor: split metrics.py into metrics/ subpackage"
```

---

## Task 2: IC 分频胜率 + 近远期比值

**Files:**
- 创建: `zer0factor/eval/metrics/ic.py`
- 创建: `tests/test_eval_metrics_ic.py`
- 修改: `zer0factor/eval/metrics/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_eval_metrics_ic.py`：

```python
import pandas as pd
import pytest

from zer0factor.eval.metrics.ic import (
    calculate_ic_freq_win_rates,
    calculate_ic_near_far_ratio,
)


def make_daily_ic():
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    return pd.DataFrame(
        {
            "1D": [0.1 if i % 3 != 0 else -0.1 for i in range(60)],
            "5D": [-0.05 if i % 4 == 0 else 0.05 for i in range(60)],
        },
        index=dates,
    )


def test_calculate_ic_freq_win_rates_returns_weekly_and_monthly():
    daily_ic = make_daily_ic()
    result = calculate_ic_freq_win_rates(daily_ic)
    assert "weekly" in result
    assert "monthly" in result
    assert set(result["weekly"].index) == {"1D", "5D"}
    assert set(result["monthly"].index) == {"1D", "5D"}


def test_calculate_ic_freq_win_rates_weekly_between_0_and_100():
    daily_ic = make_daily_ic()
    result = calculate_ic_freq_win_rates(daily_ic)
    assert (result["weekly"] >= 0).all()
    assert (result["weekly"] <= 100).all()


def test_calculate_ic_freq_win_rates_all_positive_ic_gives_100_pct():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    daily_ic = pd.DataFrame({"1D": [0.05] * 20}, index=dates)
    result = calculate_ic_freq_win_rates(daily_ic)
    assert result["weekly"]["1D"] == pytest.approx(100.0)
    assert result["monthly"]["1D"] == pytest.approx(100.0)


def test_calculate_ic_near_far_ratio_returns_series_indexed_by_period():
    daily_ic = make_daily_ic()
    result = calculate_ic_near_far_ratio(daily_ic)
    assert isinstance(result, pd.Series)
    assert set(result.index) == {"1D", "5D"}


def test_calculate_ic_near_far_ratio_is_nan_when_all_ic_is_zero():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    daily_ic = pd.DataFrame({"1D": [0.0] * 20}, index=dates)
    result = calculate_ic_near_far_ratio(daily_ic)
    assert pd.isna(result["1D"])


def test_build_summary_includes_ic_freq_and_ratio_columns():
    from zer0factor.eval.metrics import build_summary

    daily_ic = make_daily_ic()
    quantile_returns = pd.DataFrame(
        {"1D": [0.001, 0.004], "5D": [0.002, 0.006]},
        index=pd.Index([1, 10], name="factor_quantile"),
    )
    result = build_summary(
        factor_name="f",
        return_type="open_t1",
        clean_factor_data_sample_count=100,
        clean_factor_data_start=pd.Timestamp("2024-01-01"),
        clean_factor_data_end=pd.Timestamp("2024-03-31"),
        quantiles=10,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
    )
    for col in ["IC>0 %(W)", "IC>0 %(M)", "IC_near_far_ratio"]:
        assert col in result.columns, f"missing column: {col}"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_metrics_ic.py -v
```

Expected: `ImportError` 或 `ModuleNotFoundError`。

- [ ] **Step 3: 实现 `zer0factor/eval/metrics/ic.py`**

```python
from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_ic_freq_win_rates(daily_ic: pd.DataFrame) -> dict[str, pd.Series]:
    """
    返回按周/月重采样后的 IC 胜率（%）。
    daily_ic: index=date, columns=period labels
    """
    return {
        "weekly": _win_rate_by_freq(daily_ic, "W"),
        "monthly": _win_rate_by_freq(daily_ic, "ME"),
    }


def calculate_ic_near_far_ratio(daily_ic: pd.DataFrame) -> pd.Series:
    """
    近远期比值：每个周期的 IC 序列前半段均值 / 全段均值。
    衡量因子有效性的时间稳定性，> 1 表示近期更有效。
    """
    ratios = {}
    for period in daily_ic.columns:
        series = daily_ic[period].dropna()
        if len(series) < 2:
            ratios[period] = float("nan")
            continue
        full_mean = series.mean()
        if np.isclose(full_mean, 0.0) or pd.isna(full_mean):
            ratios[period] = float("nan")
            continue
        half = len(series) // 2
        near_mean = series.iloc[:half].mean()
        ratios[period] = float(near_mean / full_mean)
    return pd.Series(ratios)


def _win_rate_by_freq(daily_ic: pd.DataFrame, freq: str) -> pd.Series:
    resampled = daily_ic.resample(freq).mean()
    count = resampled.count()
    positive = resampled.gt(0).sum()
    result = (positive / count * 100).where(count > 0, other=float("nan"))
    return result
```

- [ ] **Step 4: 在 `metrics/__init__.py` 的 `build_summary` 中调用 ic 模块并追加新列**

在 `zer0factor/eval/metrics/__init__.py` 中，找到 `build_summary` 函数，在最后将新列合并进每行结果：

```python
# 在文件顶部新增导入
from zer0factor.eval.metrics.ic import (
    calculate_ic_freq_win_rates,
    calculate_ic_near_far_ratio,
)


def build_summary(
    *,
    factor_name: str,
    return_type: str,
    clean_factor_data_sample_count: int,
    clean_factor_data_start: pd.Timestamp,
    clean_factor_data_end: pd.Timestamp,
    quantiles: int,
    daily_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
    clean_factor_data: pd.DataFrame | None = None,
    index_returns: "pd.Series | None" = None,
) -> pd.DataFrame:
    lowest_quantile = quantile_returns.index.min()
    highest_quantile = quantile_returns.index.max()
    long_short_spread = calculate_long_short_spread(quantile_returns)

    ic_freq_win_rates = calculate_ic_freq_win_rates(daily_ic)
    ic_near_far_ratio = calculate_ic_near_far_ratio(daily_ic)

    rows = [
        _build_period_summary(
            factor_name=factor_name,
            return_type=return_type,
            clean_factor_data_sample_count=clean_factor_data_sample_count,
            clean_factor_data_start=clean_factor_data_start,
            clean_factor_data_end=clean_factor_data_end,
            quantiles=quantiles,
            period=period,
            ic_values=daily_ic[period],
            quantile_returns=quantile_returns,
            lowest_quantile=lowest_quantile,
            highest_quantile=highest_quantile,
            long_short_spread=long_short_spread,
            ic_freq_win_rates=ic_freq_win_rates,
            ic_near_far_ratio=ic_near_far_ratio,
        )
        for period in daily_ic.columns
    ]
    return pd.DataFrame(rows)
```

并更新 `_build_period_summary` 接受和追加这两个新参数：

```python
def _build_period_summary(
    *,
    factor_name: str,
    return_type: str,
    clean_factor_data_sample_count: int,
    clean_factor_data_start: pd.Timestamp,
    clean_factor_data_end: pd.Timestamp,
    quantiles: int,
    period,
    ic_values: "pd.Series",
    quantile_returns: "pd.DataFrame",
    lowest_quantile,
    highest_quantile,
    long_short_spread: "pd.Series",
    ic_freq_win_rates: "dict[str, pd.Series]",
    ic_near_far_ratio: "pd.Series",
) -> dict[str, object]:
    # ... existing code unchanged ...
    base = {
        "factor_name": factor_name,
        # ... all existing fields ...
    }
    # 追加新 IC 指标
    base["IC>0 %(W)"] = _get_freq_win_rate(ic_freq_win_rates["weekly"], period)
    base["IC>0 %(M)"] = _get_freq_win_rate(ic_freq_win_rates["monthly"], period)
    base["IC_near_far_ratio"] = (
        float(ic_near_far_ratio[period]) if period in ic_near_far_ratio.index else float("nan")
    )
    return base
```

新增辅助函数：
```python
def _get_freq_win_rate(win_rate_series: "pd.Series", period) -> object:
    if period not in win_rate_series.index:
        return pd.NA
    val = win_rate_series[period]
    return float(val) if not pd.isna(val) else pd.NA
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_eval_metrics_ic.py tests/test_eval_metrics.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add zer0factor/eval/metrics/ tests/test_eval_metrics_ic.py
git commit -m "feat: add IC frequency win rates and near/far ratio metrics"
```

---

## Task 3: 分组收益率时序指标

**Files:**
- 创建: `zer0factor/eval/metrics/returns.py`
- 创建: `tests/test_eval_metrics_returns.py`
- 修改: `zer0factor/eval/metrics/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_eval_metrics_returns.py`：

```python
import math

import numpy as np
import pandas as pd
import pytest

from zer0factor.eval.metrics.returns import (
    annualized_return,
    max_drawdown,
    sharpe_ratio,
    calmar_ratio,
    detect_direction,
    build_group_return_metrics,
)


def make_daily_returns(n=252, seed=42):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.001, 0.01, n))


def test_detect_direction_positive_ic_gives_plus_one():
    daily_ic = pd.DataFrame(
        {"1D": [0.1, 0.2, 0.05]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == 1


def test_detect_direction_negative_ic_gives_minus_one():
    daily_ic = pd.DataFrame(
        {"1D": [-0.1, -0.2, -0.05]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == -1


def test_detect_direction_zero_ic_gives_plus_one():
    daily_ic = pd.DataFrame(
        {"1D": [0.0, 0.0, 0.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    assert detect_direction(daily_ic) == 1


def test_annualized_return_constant_positive_return():
    daily = pd.Series([0.001] * 252)
    result = annualized_return(daily)
    expected = (1.001**252) - 1
    assert result == pytest.approx(expected, rel=1e-6)


def test_annualized_return_empty_series_is_nan():
    assert math.isnan(annualized_return(pd.Series([], dtype=float)))


def test_max_drawdown_no_drawdown_is_zero():
    daily = pd.Series([0.01] * 10)
    assert max_drawdown(daily) == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_single_loss():
    daily = pd.Series([0.1, -0.5, 0.1])
    result = max_drawdown(daily)
    assert result < 0


def test_sharpe_ratio_zero_std_is_nan():
    daily = pd.Series([0.001] * 10)
    assert math.isnan(sharpe_ratio(daily))


def test_sharpe_ratio_positive_returns():
    rng = np.random.default_rng(0)
    daily = pd.Series(abs(rng.normal(0.001, 0.01, 252)))
    result = sharpe_ratio(daily)
    assert result > 0


def test_calmar_ratio_no_drawdown_is_nan():
    daily = pd.Series([0.01] * 252)
    assert math.isnan(calmar_ratio(daily))


def test_build_group_return_metrics_keys_present():
    mean_ret = pd.DataFrame(
        {
            "1D": [0.001, 0.0015, 0.0005],
            "5D": [0.003, 0.004, 0.002],
        },
        index=pd.MultiIndex.from_product(
            [pd.date_range("2024-01-02", periods=1), [1, 5, 10]],
            names=["date", "factor_quantile"],
        ),
    )
    result = build_group_return_metrics(
        mean_ret_by_date=mean_ret,
        mean_ret_by_date_demeaned=mean_ret,
        direction=1,
        period="1D",
        n_quantiles=10,
    )
    expected_keys = [
        "long_ann_ret", "long_max_dd", "long_calmar", "long_sharpe",
        "short_ann_ret", "short_max_dd", "short_calmar", "short_sharpe",
        "ls_ann_ret", "ls_max_dd", "ls_calmar", "ls_sharpe",
        "long_exc_ann_ret", "long_exc_max_dd", "long_exc_calmar", "long_exc_sharpe",
        "ls_ann_ret_ratio",
    ]
    for key in expected_keys:
        assert key in result, f"missing key: {key}"


def test_build_group_return_metrics_direction_minus_one_flips_groups():
    mean_ret = pd.DataFrame(
        {"1D": [0.001, 0.002]},
        index=pd.MultiIndex.from_product(
            [pd.date_range("2024-01-02", periods=1), [1, 2]],
            names=["date", "factor_quantile"],
        ),
    )
    result_pos = build_group_return_metrics(mean_ret, mean_ret, direction=1, period="1D", n_quantiles=2)
    result_neg = build_group_return_metrics(mean_ret, mean_ret, direction=-1, period="1D", n_quantiles=2)
    # direction=-1: long group = lowest quantile (q=1), short = highest (q=2)
    # direction=+1: long group = highest quantile (q=2), short = lowest (q=1)
    assert result_pos["long_ann_ret"] != result_neg["long_ann_ret"]
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_metrics_returns.py -v
```

Expected: `ImportError`。

- [ ] **Step 3: 实现 `zer0factor/eval/metrics/returns.py`**

```python
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def detect_direction(daily_ic: pd.DataFrame) -> int:
    """Returns +1 if overall IC is non-negative, -1 otherwise."""
    overall = daily_ic.mean().mean()
    return 1 if (pd.isna(overall) or overall >= 0) else -1


def annualized_return(daily_returns: pd.Series) -> float:
    n = len(daily_returns.dropna())
    if n == 0:
        return float("nan")
    return float((1 + daily_returns.dropna()).prod() ** (252 / n) - 1)


def max_drawdown(daily_returns: pd.Series) -> float:
    clean = daily_returns.dropna()
    if len(clean) == 0:
        return float("nan")
    cumulative = (1 + clean).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak
    return float(drawdown.min())


def sharpe_ratio(daily_returns: pd.Series) -> float:
    clean = daily_returns.dropna()
    std = clean.std()
    if pd.isna(std) or np.isclose(std, 0.0):
        return float("nan")
    return float(clean.mean() / std * math.sqrt(252))


def calmar_ratio(daily_returns: pd.Series) -> float:
    ann = annualized_return(daily_returns)
    dd = max_drawdown(daily_returns)
    if pd.isna(dd) or np.isclose(dd, 0.0):
        return float("nan")
    return float(ann / abs(dd))


def build_group_return_metrics(
    mean_ret_by_date: pd.DataFrame,
    mean_ret_by_date_demeaned: pd.DataFrame,
    *,
    direction: int,
    period: str,
    n_quantiles: int,
    index_returns: pd.Series | None = None,
) -> dict[str, float]:
    """
    mean_ret_by_date: MultiIndex (date, factor_quantile), columns=periods
    mean_ret_by_date_demeaned: same shape, demeaned (excess vs cross-section mean)
    direction: +1 or -1
    period: e.g. "1D"
    n_quantiles: total number of quantiles
    index_returns: optional Series (DatetimeIndex → daily return) for index excess
    """
    q_long = n_quantiles if direction == 1 else 1
    q_short = 1 if direction == 1 else n_quantiles

    long_daily = _extract_quantile_daily(mean_ret_by_date, q_long, period)
    short_daily = _extract_quantile_daily(mean_ret_by_date, q_short, period)
    ls_daily = long_daily - short_daily

    long_exc_daily = _extract_quantile_daily(mean_ret_by_date_demeaned, q_long, period)
    short_exc_daily = _extract_quantile_daily(mean_ret_by_date_demeaned, q_short, period)

    result: dict[str, float] = {}

    for prefix, series in [
        ("long", long_daily),
        ("short", short_daily),
        ("ls", ls_daily),
        ("long_exc", long_exc_daily),
    ]:
        result[f"{prefix}_ann_ret"] = annualized_return(series)
        result[f"{prefix}_max_dd"] = max_drawdown(series)
        result[f"{prefix}_calmar"] = calmar_ratio(series)
        result[f"{prefix}_sharpe"] = sharpe_ratio(series)

    long_exc_ann = result["long_exc_ann_ret"]
    short_exc_ann = annualized_return(short_exc_daily)
    if not pd.isna(long_exc_ann) and not pd.isna(short_exc_ann) and not np.isclose(short_exc_ann, 0.0):
        result["ls_ann_ret_ratio"] = float(long_exc_ann / abs(short_exc_ann))
    else:
        result["ls_ann_ret_ratio"] = float("nan")

    if index_returns is not None:
        idx_exc_daily = long_daily - index_returns.reindex(long_daily.index).fillna(0)
        result["idx_exc_ann_ret"] = annualized_return(idx_exc_daily)
        result["idx_exc_max_dd"] = max_drawdown(idx_exc_daily)
        result["idx_exc_calmar"] = calmar_ratio(idx_exc_daily)
        result["idx_exc_sharpe"] = sharpe_ratio(idx_exc_daily)

    return result


def _extract_quantile_daily(
    mean_ret_by_date: pd.DataFrame,
    quantile: int,
    period: str,
) -> pd.Series:
    """Extract daily return Series for a single quantile from by-date quantile returns."""
    if period not in mean_ret_by_date.columns:
        return pd.Series(dtype=float)
    try:
        return mean_ret_by_date[period].xs(quantile, level="factor_quantile")
    except KeyError:
        return pd.Series(dtype=float)
```

- [ ] **Step 4: 在 `metrics/__init__.py` 中集成 returns 模块**

在 `build_summary` 内，如果 `clean_factor_data is not None`，调用 `mean_return_by_quantile` 并追加 returns 指标列：

在 `zer0factor/eval/metrics/__init__.py` 顶部新增导入：

```python
from zer0factor.eval.metrics.returns import build_group_return_metrics, detect_direction
```

在 `build_summary` 内，`ic_near_far_ratio = ...` 后追加：

```python
    direction = detect_direction(daily_ic)

    # 预计算分组日收益率（仅当 clean_factor_data 有值时）
    _mean_ret_by_date = None
    _mean_ret_by_date_demeaned = None
    if clean_factor_data is not None:
        from alphalens.performance import mean_return_by_quantile as _mrq
        _mean_ret_by_date, _ = _mrq(clean_factor_data, by_date=True, demeaned=False)
        _mean_ret_by_date_demeaned, _ = _mrq(clean_factor_data, by_date=True, demeaned=True)
```

在 `_build_period_summary` 的调用中新增参数：

```python
        _build_period_summary(
            ...,
            direction=direction,
            n_quantiles=quantiles,
            mean_ret_by_date=_mean_ret_by_date,
            mean_ret_by_date_demeaned=_mean_ret_by_date_demeaned,
            index_returns=index_returns,
        )
```

在 `_build_period_summary` 内，在 `return base` 前追加：

```python
    if mean_ret_by_date is not None:
        ret_metrics = build_group_return_metrics(
            mean_ret_by_date=mean_ret_by_date,
            mean_ret_by_date_demeaned=mean_ret_by_date_demeaned,
            direction=direction,
            period=period,
            n_quantiles=quantiles,
            index_returns=index_returns,
        )
        base.update(ret_metrics)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_eval_metrics_returns.py tests/test_eval_metrics.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add zer0factor/eval/metrics/ tests/test_eval_metrics_returns.py
git commit -m "feat: add group return time-series metrics (annualized, drawdown, calmar, sharpe)"
```

---

## Task 4: 换手率指标

**Files:**
- 创建: `zer0factor/eval/metrics/turnover.py`
- 创建: `tests/test_eval_metrics_turnover.py`
- 修改: `zer0factor/eval/metrics/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_eval_metrics_turnover.py`：

```python
import pandas as pd
import pytest

from zer0factor.eval.metrics.turnover import calculate_quantile_turnover


def make_clean_factor_data():
    """3 dates × 4 assets, quantiles 1..4."""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    assets = ["A", "B", "C", "D"]
    index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    return pd.DataFrame(
        {
            "factor": [1.0, 2.0, 3.0, 4.0] * 3,
            "factor_quantile": [1, 2, 3, 4] * 3,
            "1D": [0.01] * 12,
        },
        index=index,
    )


def test_calculate_quantile_turnover_returns_expected_keys():
    cfd = make_clean_factor_data()
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    for key in ["turnover_daily_long", "turnover_annual_long",
                "turnover_daily_short", "turnover_annual_short"]:
        assert key in result, f"missing key: {key}"


def test_calculate_quantile_turnover_zero_when_holdings_unchanged():
    """同一组股票每天不变，换手率为 0。"""
    cfd = make_clean_factor_data()
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    assert result["turnover_daily_long"] == pytest.approx(0.0)
    assert result["turnover_daily_short"] == pytest.approx(0.0)


def test_calculate_quantile_turnover_annual_equals_daily_times_252_over_period():
    cfd = make_clean_factor_data()
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    expected_annual = result["turnover_daily_long"] * 252 / 1
    assert result["turnover_annual_long"] == pytest.approx(expected_annual)


def test_calculate_quantile_turnover_full_turnover_when_all_stocks_change():
    dates = pd.date_range("2024-01-02", periods=2, freq="B")
    # Day 1: A,B in q4; Day 2: C,D in q4 — complete turnover
    index = pd.MultiIndex.from_tuples(
        [(dates[0], "A"), (dates[0], "B"), (dates[0], "C"), (dates[0], "D"),
         (dates[1], "A"), (dates[1], "B"), (dates[1], "C"), (dates[1], "D")],
        names=["date", "asset"],
    )
    cfd = pd.DataFrame(
        {
            "factor": [1.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0],
            "factor_quantile": [1, 2, 3, 4, 4, 3, 2, 1],
            "1D": [0.01] * 8,
        },
        index=index,
    )
    result = calculate_quantile_turnover(cfd, long_quantile=4, short_quantile=1, period="1D")
    assert result["turnover_daily_long"] == pytest.approx(1.0)
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_metrics_turnover.py -v
```

Expected: `ImportError`。

- [ ] **Step 3: 实现 `zer0factor/eval/metrics/turnover.py`**

```python
from __future__ import annotations

import pandas as pd


def calculate_quantile_turnover(
    clean_factor_data: pd.DataFrame,
    *,
    long_quantile: int,
    short_quantile: int,
    period: str,
) -> dict[str, float]:
    """
    计算多头组和空头组的单边日均换手率及年化换手率。

    换手率定义：相邻两日持仓集合的对称差集大小 / 最大持仓集合大小。
    单边（single-side）：仅统计进入或退出的一侧，等于对称差 / (2 × max_size)。
    """
    period_int = _parse_period_int(period)

    long_daily = _quantile_daily_turnover(clean_factor_data, long_quantile)
    short_daily = _quantile_daily_turnover(clean_factor_data, short_quantile)

    long_mean = float(long_daily.mean()) if len(long_daily) > 0 else float("nan")
    short_mean = float(short_daily.mean()) if len(short_daily) > 0 else float("nan")

    import math
    return {
        "turnover_daily_long": long_mean,
        "turnover_annual_long": long_mean * 252 / period_int if not math.isnan(long_mean) else float("nan"),
        "turnover_daily_short": short_mean,
        "turnover_annual_short": short_mean * 252 / period_int if not math.isnan(short_mean) else float("nan"),
    }


def _quantile_daily_turnover(
    clean_factor_data: pd.DataFrame,
    quantile: int,
) -> pd.Series:
    quant_data = clean_factor_data[clean_factor_data["factor_quantile"] == quantile]
    stocks_by_date = (
        quant_data.groupby(level="date")
        .apply(lambda x: set(x.index.get_level_values("asset")))
    )
    dates = stocks_by_date.index.tolist()
    if len(dates) < 2:
        return pd.Series(dtype=float)

    turnovers = []
    for i in range(1, len(dates)):
        prev = stocks_by_date[dates[i - 1]]
        curr = stocks_by_date[dates[i]]
        size = max(len(prev), len(curr), 1)
        sym_diff = len(prev.symmetric_difference(curr))
        turnovers.append(sym_diff / (2 * size))

    return pd.Series(turnovers, index=dates[1:])


def _parse_period_int(period: str) -> int:
    return int(period.rstrip("D").rstrip("d"))
```

- [ ] **Step 4: 在 `metrics/__init__.py` 中集成换手率**

在 `zer0factor/eval/metrics/__init__.py` 顶部新增导入：

```python
from zer0factor.eval.metrics.turnover import calculate_quantile_turnover
```

在 `_build_period_summary` 中，`if mean_ret_by_date is not None:` 块内追加：

```python
    if clean_factor_data is not None:
        to_metrics = calculate_quantile_turnover(
            clean_factor_data,
            long_quantile=n_quantiles if direction == 1 else 1,
            short_quantile=1 if direction == 1 else n_quantiles,
            period=period,
        )
        base.update(to_metrics)
```

注意：需将 `clean_factor_data` 也传入 `_build_period_summary`。在 `build_summary` 中传递 `clean_factor_data=clean_factor_data`，并在 `_build_period_summary` 签名中新增该参数。

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_eval_metrics_turnover.py tests/test_eval_metrics.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add zer0factor/eval/metrics/ tests/test_eval_metrics_turnover.py
git commit -m "feat: add long/short quantile turnover metrics"
```

---

## Task 5: 季度单调性稳定性

**Files:**
- 创建: `zer0factor/eval/metrics/monotonicity.py`
- 创建: `tests/test_eval_metrics_monotonicity.py`
- 修改: `zer0factor/eval/metrics/__init__.py`
- 修改: `zer0factor/eval/report.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_eval_metrics_monotonicity.py`：

```python
import math

import pandas as pd
import pytest

from zer0factor.eval.metrics.monotonicity import (
    calculate_monotonicity,
    calculate_quarterly_monotonicity_stats,
)


def make_quantile_returns(direction: int = 1):
    """Monotonically increasing quantile returns (direction=1 → positive mono)."""
    n = 5
    returns = [i * 0.001 * direction for i in range(1, n + 1)]
    return pd.Series(
        returns,
        index=pd.Index(range(1, n + 1), name="factor_quantile"),
    )


def make_mean_ret_by_date(n_dates=12, n_quantiles=5):
    """Synthetic MultiIndex (date, factor_quantile) daily returns."""
    dates = pd.date_range("2024-01-02", periods=n_dates, freq="B")
    quantiles = list(range(1, n_quantiles + 1))
    index = pd.MultiIndex.from_product([dates, quantiles], names=["date", "factor_quantile"])
    # Each quantile returns its rank × 0.001
    values = [(q * 0.001) for _ in dates for q in quantiles]
    return pd.DataFrame({"1D": values}, index=index)


def test_calculate_monotonicity_perfect_ascending_is_one():
    qr = make_quantile_returns(direction=1)
    result = calculate_monotonicity(qr, direction=1)
    assert result == pytest.approx(1.0)


def test_calculate_monotonicity_perfect_descending_with_direction_minus_one_is_one():
    qr = make_quantile_returns(direction=-1)
    result = calculate_monotonicity(qr, direction=-1)
    assert result == pytest.approx(1.0)


def test_calculate_monotonicity_single_quantile_is_nan():
    qr = pd.Series([0.001], index=pd.Index([1], name="factor_quantile"))
    assert math.isnan(calculate_monotonicity(qr, direction=1))


def test_calculate_quarterly_monotonicity_stats_keys():
    mean_ret = make_mean_ret_by_date(n_dates=60, n_quantiles=5)
    result = calculate_quarterly_monotonicity_stats(mean_ret, direction=1, period="1D")
    for key in ["monotonicity_q_mean", "monotonicity_q_ir", "monotonicity_q_pos_rate"]:
        assert key in result, f"missing key: {key}"


def test_calculate_quarterly_monotonicity_stats_few_quarters_is_nan():
    mean_ret = make_mean_ret_by_date(n_dates=5, n_quantiles=5)
    result = calculate_quarterly_monotonicity_stats(mean_ret, direction=1, period="1D")
    assert math.isnan(result["monotonicity_q_mean"])


def test_calculate_quarterly_monotonicity_pos_rate_between_0_and_100():
    mean_ret = make_mean_ret_by_date(n_dates=60, n_quantiles=5)
    result = calculate_quarterly_monotonicity_stats(mean_ret, direction=1, period="1D")
    if not math.isnan(result["monotonicity_q_pos_rate"]):
        assert 0 <= result["monotonicity_q_pos_rate"] <= 100
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_metrics_monotonicity.py -v
```

Expected: `ImportError`。

- [ ] **Step 3: 实现 `zer0factor/eval/metrics/monotonicity.py`**

```python
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def calculate_monotonicity(
    quantile_returns: pd.Series,
    *,
    direction: int,
) -> float:
    """
    Spearman 相关系数 × direction，衡量分组收益与分位号的单调性。
    quantile_returns: index=factor_quantile, values=period return
    """
    clean = quantile_returns.dropna()
    if len(clean) < 2:
        return float("nan")
    quantile_order = pd.Series(
        range(1, len(clean) + 1),
        index=clean.index,
        dtype="float64",
    )
    raw = float(quantile_order.corr(clean, method="spearman"))
    return raw * direction


def calculate_quarterly_monotonicity_stats(
    mean_ret_by_date: pd.DataFrame,
    *,
    direction: int,
    period: str,
) -> dict[str, float]:
    """
    按季度计算分组单调性并汇总统计。
    mean_ret_by_date: MultiIndex (date, factor_quantile), columns contain period
    """
    if period not in mean_ret_by_date.columns:
        return _nan_stats()

    period_ret = mean_ret_by_date[period].unstack(level="factor_quantile")
    # period_ret: index=date (DatetimeIndex), columns=quantile int

    quarterly_mono = []
    try:
        grouped = period_ret.groupby(pd.Grouper(freq="QE"))
    except ValueError:
        grouped = period_ret.groupby(pd.Grouper(freq="Q"))

    for _quarter, group in grouped:
        if group.empty:
            continue
        cum_ret = (1 + group).prod() - 1
        if len(cum_ret.dropna()) < 2:
            continue
        quantile_order = pd.Series(
            range(1, len(cum_ret) + 1),
            index=cum_ret.index,
            dtype=float,
        )
        mono = float(quantile_order.corr(cum_ret, method="spearman")) * direction
        if not math.isnan(mono):
            quarterly_mono.append(mono)

    if len(quarterly_mono) < 2:
        return _nan_stats()

    s = pd.Series(quarterly_mono)
    mean = float(s.mean())
    std = float(s.std())
    ir = mean / std if not np.isclose(std, 0.0) else float("nan")
    pos_rate = float((s > 0).mean() * 100)

    return {
        "monotonicity_q_mean": mean,
        "monotonicity_q_ir": ir,
        "monotonicity_q_pos_rate": pos_rate,
    }


def _nan_stats() -> dict[str, float]:
    return {
        "monotonicity_q_mean": float("nan"),
        "monotonicity_q_ir": float("nan"),
        "monotonicity_q_pos_rate": float("nan"),
    }
```

- [ ] **Step 4: 在 `metrics/__init__.py` 中迁移现有单调性逻辑并集成季度统计**

在 `metrics/__init__.py` 顶部新增导入：

```python
from zer0factor.eval.metrics.monotonicity import (
    calculate_monotonicity,
    calculate_quarterly_monotonicity_stats,
)
```

在 `_build_period_summary` 中，将 `report.py` 里原来的 spearman 单调性计算（已在 `report.py` 中）保留原样，这里只追加季度统计列：

```python
    if mean_ret_by_date is not None:
        q_stats = calculate_quarterly_monotonicity_stats(
            mean_ret_by_date,
            direction=direction,
            period=period,
        )
        base.update(q_stats)
```

- [ ] **Step 5: 在 `report.py` 中把 `_display_columns` 的 `monotonicity` 后面加上新列**

在 `zer0factor/eval/report.py` 的 `_display_columns` 函数中，在 `"monotonicity"` 后追加：

```python
        "monotonicity_q_mean",
        "monotonicity_q_ir",
        "monotonicity_q_pos_rate",
```

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_eval_metrics_monotonicity.py tests/test_eval_metrics.py tests/test_eval_report.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 7: Commit**

```bash
git add zer0factor/eval/metrics/ zer0factor/eval/report.py tests/test_eval_metrics_monotonicity.py
git commit -m "feat: add quarterly monotonicity stability stats"
```

---

## Task 6: `load_index_daily()` 加载指数日收益率

**Files:**
- 修改: `zer0factor/eval/loaders.py`
- 修改: `tests/test_eval_loaders.py`（若不存在则创建）

- [ ] **Step 1: 写失败测试**

创建（或追加到）`tests/test_eval_loaders.py`：

```python
import pandas as pd
import pytest

from zer0factor.eval.loaders import load_index_daily


class FakeIndexPro:
    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame({
            "ts_code": ["000300.SH"] * 3,
            "trade_date": ["20240102", "20240103", "20240104"],
            "pct_chg": [1.5, -0.8, 0.3],
        })


class EmptyIndexPro:
    def index_daily(self, ts_code=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(columns=["ts_code", "trade_date", "pct_chg"])


def test_load_index_daily_returns_series_with_datetime_index():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert isinstance(result, pd.Series)
    assert pd.api.types.is_datetime64_any_dtype(result.index)


def test_load_index_daily_values_are_pct_chg_divided_by_100():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert result.iloc[0] == pytest.approx(0.015)
    assert result.iloc[1] == pytest.approx(-0.008)


def test_load_index_daily_empty_returns_empty_series():
    pro = EmptyIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert isinstance(result, pd.Series)
    assert len(result) == 0


def test_load_index_daily_index_is_sorted():
    pro = FakeIndexPro()
    result = load_index_daily(pro, ts_code="000300.SH", start_date="20240101", end_date="20240105")
    assert result.index.is_monotonic_increasing
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_loaders.py -v
```

Expected: `ImportError` 或 `AttributeError`。

- [ ] **Step 3: 在 `zer0factor/eval/loaders.py` 中添加 `load_index_daily`**

```python
def load_index_daily(
    pro,
    *,
    ts_code: str,
    start_date: str,
    end_date: str | None,
) -> pd.Series:
    """
    返回指数日收益率 Series。
    index: DatetimeIndex (按日期升序)
    values: pct_chg / 100（小数形式）
    """
    df = pro.index_daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,pct_chg",
    )
    if df.empty:
        return pd.Series(dtype=float)

    df = df[["trade_date", "pct_chg"]].dropna()
    df["date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    result = df.set_index("date")["pct_chg"] / 100
    return result.sort_index()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_eval_loaders.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add zer0factor/eval/loaders.py tests/test_eval_loaders.py
git commit -m "feat: add load_index_daily() to loaders"
```

---

## Task 7: `EvaluationConfig.benchmark_index` + `pipeline.py` 串联

**Files:**
- 修改: `zer0factor/eval/config.py`
- 修改: `zer0factor/eval/pipeline.py`
- 修改: `tests/test_eval_config.py`
- 修改: `tests/test_eval_pipeline.py`

- [ ] **Step 1: 写失败测试（config）**

在 `tests/test_eval_config.py` 中追加：

```python
def test_evaluation_config_accepts_benchmark_index():
    from zer0factor.eval.config import EvaluationConfig
    config = EvaluationConfig(
        factor_names=("f",),
        start_date="20240101",
        end_date="20240131",
        benchmark_index="000300.SH",
    )
    assert config.benchmark_index == "000300.SH"


def test_evaluation_config_benchmark_index_defaults_to_none():
    from zer0factor.eval.config import EvaluationConfig
    config = EvaluationConfig(
        factor_names=("f",),
        start_date="20240101",
        end_date="20240131",
    )
    assert config.benchmark_index is None
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_config.py -v -k "benchmark"
```

Expected: FAIL（`EvaluationConfig` 无 `benchmark_index`）。

- [ ] **Step 3: 在 `config.py` 中添加 `benchmark_index` 字段**

在 `EvaluationConfig` 的 `rolling_ic_window: int = 63` 后追加：

```python
    benchmark_index: str | None = None
```

- [ ] **Step 4: 写 pipeline 集成测试（新列出现在 summary 中）**

在 `tests/test_eval_pipeline.py` 中追加：

```python
def test_evaluate_factors_summary_contains_ic_freq_columns(tmp_path, monkeypatch):
    from zer0factor.eval import EvaluationConfig, evaluate_factors
    from zer0factor.storage import FactorStorage

    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)

    # patch clean_factor_data with 60 rows across 30 dates × 2 assets
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    assets = ["000001.SZ", "000002.SZ"]
    index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    clean = pd.DataFrame(
        {
            "factor": [float(i % 5 + 1) for i in range(60)],
            "factor_quantile": [(i % 2) + 1 for i in range(60)],
            "1D": [0.001 * (i % 10 - 5) for i in range(60)],
        },
        index=index,
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        lambda *a, **kw: clean,
    )

    config = make_config(tmp_path, periods=(1,), quantiles=2)
    result = evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=FakePro(),
        config=config,
        run_id="run_ext",
    )

    for col in ["IC>0 %(W)", "IC>0 %(M)", "IC_near_far_ratio"]:
        assert col in result.summary.columns, f"missing: {col}"
```

- [ ] **Step 5: 运行确认当前失败**

```bash
uv run pytest tests/test_eval_pipeline.py::test_evaluate_factors_summary_contains_ic_freq_columns -v
```

Expected: FAIL（列不存在）。

- [ ] **Step 6: 更新 `pipeline.py` 中 `evaluate_factor` 传入 `clean_factor_data` 给 `build_summary`**

在 `zer0factor/eval/pipeline.py` 的 `evaluate_factor` 函数中，找到 `build_summary(...)` 调用，新增参数：

```python
    # 若配置了 benchmark_index，加载指数日收益
    from zer0factor.eval.loaders import load_index_daily
    index_returns = None
    if config.benchmark_index:
        index_returns = load_index_daily(
            pro,
            ts_code=config.benchmark_index,
            start_date=config.start_date,
            end_date=config.end_date or _max_factor_trade_date(factor_data),
        )

    summary = build_summary(
        factor_name=factor_name,
        return_type=config.return_type,
        clean_factor_data_sample_count=len(clean_factor_data),
        clean_factor_data_start=clean_factor_data.index.get_level_values("date").min(),
        clean_factor_data_end=clean_factor_data.index.get_level_values("date").max(),
        quantiles=config.quantiles,
        daily_ic=daily_ic,
        quantile_returns=quantile_returns,
        clean_factor_data=clean_factor_data,   # 新增
        index_returns=index_returns,            # 新增
    )
```

同时在 `evaluate_factors` 中，将 `benchmark_index` 从 `resolved_config` 传到 `evaluate_factor` 调用（已通过 `config` 对象传递，无需额外改动）。

- [ ] **Step 7: 运行所有相关测试**

```bash
uv run pytest tests/test_eval_config.py tests/test_eval_pipeline.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 8: Commit**

```bash
git add zer0factor/eval/config.py zer0factor/eval/pipeline.py tests/test_eval_config.py tests/test_eval_pipeline.py
git commit -m "feat: wire extended metrics into pipeline, add benchmark_index config"
```

---

## Task 8: `report.py` 新列展示 + `main.py` CLI 参数

**Files:**
- 修改: `zer0factor/eval/report.py`
- 修改: `main.py`
- 修改: `tests/test_eval_report.py`

- [ ] **Step 1: 写失败测试（report 展示列）**

在 `tests/test_eval_report.py` 中追加：

```python
def test_build_ranked_summary_includes_return_columns_when_present():
    from zer0factor.eval.report import build_ranked_summary, ReportThresholds

    summary = pd.DataFrame({
        "factor_name": ["f"],
        "period": ["1D"],
        "sample_count": [1000],
        "IC Mean": [0.05],
        "ICIR": [0.5],
        "IC>0 %": [55.0],
        "long_short_spread_bps": [10.0],
        "long_sharpe": [1.2],
        "ls_calmar": [0.8],
        "turnover_annual_long": [24.0],
        "monotonicity_q_mean": [0.7],
    })
    result = build_ranked_summary(summary, ReportThresholds())
    # 新列存在时应出现在 ranked_summary 中
    assert "long_sharpe" in result.columns
    assert "ls_calmar" in result.columns
    assert "turnover_annual_long" in result.columns
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_eval_report.py::test_build_ranked_summary_includes_return_columns_when_present -v
```

Expected: FAIL（新列被丢弃）。

- [ ] **Step 3: 更新 `report.py` 的 `_display_columns`**

在 `zer0factor/eval/report.py` 的 `_display_columns` 函数中，在 `"monotonicity"` 后追加：

```python
        "monotonicity_q_mean",
        "monotonicity_q_ir",
        "monotonicity_q_pos_rate",
        "long_sharpe",
        "long_calmar",
        "long_ann_ret",
        "ls_sharpe",
        "ls_calmar",
        "ls_ann_ret",
        "long_exc_sharpe",
        "long_exc_calmar",
        "idx_exc_sharpe",
        "idx_exc_calmar",
        "turnover_daily_long",
        "turnover_annual_long",
        "IC>0 %(W)",
        "IC>0 %(M)",
        "IC_near_far_ratio",
        "ls_ann_ret_ratio",
```

同时在 `build_ranked_summary` 中，`ranked = summary.copy()` 后确保新列被保留（`copy()` 已会保留所有列，无需额外操作）。

- [ ] **Step 4: 更新 `main.py` 中的 `--benchmark-index` 参数**

在 `main.py` 的 `evaluate-factor`、`evaluate-factors`、`evaluate-batch` 三个命令中新增选项：

```python
@click.option("--benchmark-index", default=None, help="指数代码，如 000300.SH，用于计算多头指数超额收益")
```

并在 `_run_evaluation_job` 签名中新增 `benchmark_index: str | None = None`，传入 `EvaluationConfig`：

```python
    config = EvaluationConfig(
        ...
        benchmark_index=benchmark_index,
    )
```

在 `evaluate-batch` 命令中，`batch` 对象暂不支持 `benchmark_index`（`load_batch_evaluation_config` 不读取该字段），保持默认 None。

- [ ] **Step 5: 运行完整测试套件**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 所有测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add zer0factor/eval/report.py main.py tests/test_eval_report.py
git commit -m "feat: add extended metric columns to report display and --benchmark-index CLI flag"
```

---

## 验收检查

全部任务完成后运行：

```bash
uv run pytest tests/ -v
```

并手动验证 CLI 新参数：

```bash
uv run python main.py factor-list
uv run python main.py evaluate-factor --help
```

确认 `--benchmark-index` 选项出现在帮助信息中。
