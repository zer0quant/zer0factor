import os
import time

from zer0factor.config import StandardSetting
from zer0factor.web.runs import (
    SummaryCache,
    is_standard,
    latest_data_end,
    scan_runs,
    standard_rows,
)

STD = StandardSetting(quantiles=5)


def test_scan_skips_dir_without_metadata(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], write_metadata=False)
    make_run("20260102_000000", ["fa"])
    runs = scan_runs(evaluations_dir)
    assert [r.run_id for r in runs] == ["20260102_000000"]


def test_scan_marks_missing_summary(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], write_summary=False)
    (run,) = scan_runs(evaluations_dir)
    assert run.has_summary is False


def test_scan_converts_int_periods(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], periods=("1D", "5D"))
    (run,) = scan_runs(evaluations_dir)
    assert run.periods == ("1D", "5D")
    assert run.factor_names == ("fa",)


def test_scan_skips_corrupt_metadata(make_run, evaluations_dir):
    run_dir = make_run("20260101_000000", ["fa"])
    (run_dir / "metadata.json").write_text("{not json")
    assert scan_runs(evaluations_dir) == []


def test_is_standard_true_for_matching_metadata(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"])
    (run,) = scan_runs(evaluations_dir)
    assert is_standard(run, STD)


def test_is_standard_false_when_end_date_set(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], metadata={"end_date": "20250101"})
    (run,) = scan_runs(evaluations_dir)
    assert not is_standard(run, STD)


def test_is_standard_false_when_universe_none(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], metadata={"universe": None})
    (run,) = scan_runs(evaluations_dir)
    assert not is_standard(run, STD)


def test_standard_rows_picks_latest_run(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa", "fb"])
    make_run("20260201_000000", ["fa"])
    rows = standard_rows(scan_runs(evaluations_dir), STD, SummaryCache())
    assert rows["fa"][0].run_id == "20260201_000000"
    assert rows["fb"][0].run_id == "20260101_000000"
    assert rows["fa"][1]["period"] == "1D"


def test_standard_rows_ignores_run_without_1D_row(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], periods=("5D",), metadata={"periods": [1, 5]})
    rows = standard_rows(scan_runs(evaluations_dir), STD, SummaryCache())
    assert rows == {}


def test_summary_cache_reloads_on_mtime_change(make_run, evaluations_dir):
    run_dir = make_run("20260101_000000", ["fa"])
    (run,) = scan_runs(evaluations_dir)
    cache = SummaryCache()
    first = cache.get(run)
    assert first is not None and len(first) == 1
    summary = run_dir / "summary.parquet"
    df = first.copy()
    df["factor_name"] = "changed"
    df.to_parquet(summary, index=False)
    future = time.time() + 5
    os.utime(summary, (future, future))
    assert cache.get(run)["factor_name"].tolist() == ["changed"]


def test_scan_runs_skips_cancelled_and_excluded(make_run, evaluations_dir):
    make_run("r1", ["fa"])
    make_run("r2", ["fa"])
    make_run("r3", ["fa"])
    (evaluations_dir / "r2" / ".cancelled").write_text("x")
    assert [r.run_id for r in scan_runs(evaluations_dir, exclude={"r3"})] == ["r1"]


def test_is_standard_true_when_end_date_is_latest_data_date(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"])
    latest = latest_data_end(scan_runs(evaluations_dir), SummaryCache())
    assert latest is not None and len(latest) == 8
    make_run("20260201_000000", ["fa"], metadata={"end_date": latest})
    runs = scan_runs(evaluations_dir)
    newer = next(r for r in runs if r.run_id == "20260201_000000")
    assert is_standard(newer, STD, latest)
    rows = standard_rows(runs, STD, SummaryCache())
    assert rows["fa"][0].run_id == "20260201_000000"


def test_is_standard_false_when_end_date_before_latest(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"])
    make_run("20260201_000000", ["fa"], metadata={"end_date": "20200101"})
    runs = scan_runs(evaluations_dir)
    latest = latest_data_end(runs, SummaryCache())
    older_end = next(r for r in runs if r.run_id == "20260201_000000")
    assert not is_standard(older_end, STD, latest)
    assert standard_rows(runs, STD, SummaryCache())["fa"][0].run_id == "20260101_000000"


def test_latest_data_end_none_without_summaries(make_run, evaluations_dir):
    make_run("20260101_000000", ["fa"], write_summary=False, metadata={"end_date": "20250101"})
    runs = scan_runs(evaluations_dir)
    latest = latest_data_end(runs, SummaryCache())
    assert latest is None
    assert not is_standard(runs[0], STD, latest)
