import sys
from pathlib import Path

import pytest

from zer0factor.config import Config, WebConfig
from zer0factor.jobs.progress import Progress
from zer0factor.jobs.specs import SpecError, build_spec


@pytest.fixture
def cfg(tmp_path):
    return Config(
        zer0share_data_dir=tmp_path / "zs",
        factor_dir=tmp_path / "factors",
        db_path=tmp_path / "f.duckdb",
        log_path=tmp_path / "f.log",
        universe="all",
        process_universe="univ_trade_base",
        start_date="20160101",
        end_date="",
        web=WebConfig(evaluations_dir=tmp_path / "evals"),
    )


def _spec(cfg, tmp_path, kind, raw, **kw):
    args = dict(
        cfg=cfg,
        config_path=tmp_path / "settings.toml",
        known_factors={"fa", "fb"},
        known_families={"rolling_return"},
        known_runs=set(),
    )
    args.update(kw)
    return build_spec(kind, raw, **args)


def test_evaluate_spec_builds_cli_argv(cfg, tmp_path):
    spec = _spec(cfg, tmp_path, "evaluate", {"factors": ["fa", "fb"]})
    assert spec.queue == "heavy" and spec.kind == "evaluate"
    assert spec.command[0] == sys.executable
    assert spec.command[1].endswith("main.py")
    assert spec.command[2:4] == ["--config", str((tmp_path / "settings.toml").resolve())]
    tail = spec.command[4:]
    assert tail[:3] == ["evaluate-factors", "fa", "fb"]
    expected = [
        "--start-date", "20160101", "--periods", "1,5,10", "--quantiles", "10",
        "--return-type", "open_t1", "--max-loss", "0.35", "--transaction-cost-bps", "10.0",
        "--output-dir", str((tmp_path / "evals").resolve()), "--run-id", spec.run_id,
    ]
    for i in range(0, len(expected), 2):
        j = tail.index(expected[i])
        assert tail[j + 1] == expected[i + 1], expected[i]
    assert "--end-date" not in tail and "--universe" not in tail
    assert spec.progress_total == 2


def test_spec_rejects_unknown_factor_and_bad_date(cfg, tmp_path):
    with pytest.raises(SpecError, match="nope"):
        _spec(cfg, tmp_path, "evaluate", {"factors": ["fa", "nope"]})
    with pytest.raises(SpecError):
        _spec(cfg, tmp_path, "evaluate", {"factors": ["fa"], "start_date": "2016-01-01"})
    with pytest.raises(SpecError):
        _spec(cfg, tmp_path, "evaluate", {"factors": ["fa"], "universe": "a;rm -rf"})
    with pytest.raises(SpecError):
        _spec(cfg, tmp_path, "nonsense", {})


def test_build_spec_requires_known_family(cfg, tmp_path):
    spec = _spec(cfg, tmp_path, "build", {"family": "rolling_return", "stage": "raw",
                                           "update_registry": True, "workers": 4})
    tail = spec.command[4:]
    assert tail[:3] == ["build-factors", "--family", "rolling_return"]
    assert "--update-registry" in tail and tail[tail.index("--stage") + 1] == "raw"
    assert tail[tail.index("--workers") + 1] == "4"
    with pytest.raises(SpecError):
        _spec(cfg, tmp_path, "build", {"family": "unknown"})


def test_base_and_warm_specs(cfg, tmp_path):
    assert _spec(cfg, tmp_path, "base", {"target": "returns"}).command[4:] == ["compute-returns"]
    warm = _spec(cfg, tmp_path, "warm", {"run_id": "r1"}, known_runs={"r1"},
                 run_factor_counts={"r1": 7})
    assert warm.queue == "light"
    assert warm.command[4:] == ["web-warm", "--run", "r1", "--workers", "8"]
    assert warm.progress_total == 7
    with pytest.raises(SpecError):
        _spec(cfg, tmp_path, "warm", {"run_id": "missing"})


def test_run_id_avoids_existing(cfg, tmp_path, monkeypatch):
    import zer0factor.jobs.specs as specs

    monkeypatch.setattr(specs, "_timestamp", lambda: "20260101_000000")
    spec = _spec(cfg, tmp_path, "evaluate", {"factors": ["fa"]},
                 known_runs={"20260101_000000", "20260101_000000_2"})
    assert spec.run_id == "20260101_000000_3"
    (tmp_path / "evals" / "20260101_000000_3").mkdir(parents=True)
    spec = _spec(cfg, tmp_path, "evaluate", {"factors": ["fa"]},
                 known_runs={"20260101_000000", "20260101_000000_2"})
    assert spec.run_id == "20260101_000000_4"


def test_progress_counts_evaluate_lines():
    p = Progress("evaluate", total=2)
    assert p.feed("2026 | INFO | evaluation_run_started factors=2")
    assert p.done == 0
    p.feed("2026 | INFO | evaluation_factor_finished factor=fa")
    p.feed("2026 | INFO | evaluation_factor_finished factor=fb")
    assert (p.done, p.total) == (2, 2)
    w = Progress("warm", total=3)
    w.feed("ok   fa")
    w.feed("fail fb: boom")
    w.feed("done: 1 ok, 1 failed")
    assert w.done == 2
    b = Progress("build", total=None)
    b.feed("hello")
    assert b.last_line == "hello" and b.done == 0
