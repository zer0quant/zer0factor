import types

import pytest
from click.testing import CliRunner

from zer0factor.cli import cli
from zer0factor.daily import Step, run_steps
from zer0factor.freshness import FreshnessReport


def test_run_steps_stops_at_first_failure():
    calls = []

    def ok(name):
        return lambda: calls.append(name)

    def boom():
        raise RuntimeError("bad data")

    def click_exit(code):
        def run():
            raise SystemExit(code)
        return run

    outcomes = run_steps([
        Step("a", ok("a")),
        Step("exit0", click_exit(0)),
        Step("b", boom),
        Step("c", ok("c")),
    ])
    assert calls == ["a"]
    assert [o.status for o in outcomes] == ["ok", "ok", "failed", "skipped"]
    assert "RuntimeError: bad data" in outcomes[2].describe()
    assert "未执行" in outcomes[3].describe()

    outcomes = run_steps([Step("x", click_exit(2)), Step("y", ok("y"))])
    assert [o.status for o in outcomes] == ["failed", "skipped"]
    assert outcomes[0].error == "exit 2"


def _report(target="20261106", universe_end=None, issues=()):
    return FreshnessReport(
        market={"daily_kline": "20261106"},
        universes={"univ_trade_base": universe_end or target},
        factor_groups=(),
        evaluation=None,
        market_end="20261106" if target else None,
        universe_end=universe_end or target,
        target_end=target,
        issues=tuple(issues),
    )


def _settings(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(
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
start_date = "20160101"
end_date = ""

[web]
evaluations_dir = "{tmp_path / 'evaluations'}"
""".lstrip(),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def daily(monkeypatch, tmp_path):
    state = types.SimpleNamespace(calls=[], reports=[_report()], warnings=[], successes=[])

    def record(name):
        def fn(**kwargs):
            state.calls.append((name, kwargs))
        return fn

    monkeypatch.setattr("zer0factor.cli.daily_cmds.compute_returns", record("returns"))
    monkeypatch.setattr("zer0factor.cli.daily_cmds.compute_market_cap", record("market_cap"))
    monkeypatch.setattr("zer0factor.cli.daily_cmds.build_factors_command", record("build"))

    def fake_eval(ctx, **kwargs):
        state.calls.append(("evaluate", kwargs))

    monkeypatch.setattr("zer0factor.cli.daily_cmds._run_evaluation_job", fake_eval)

    def fake_collect(cfg):
        report = state.reports[0] if len(state.reports) == 1 else state.reports.pop(0)
        return report, []

    monkeypatch.setattr("zer0factor.cli.daily_cmds.collect_report", fake_collect)
    monkeypatch.setattr(
        "zer0factor.cli.daily_cmds.latest_standard_evaluation",
        lambda d, std: ("20261109_154727", "20261105", ("z_a", "z_b"), 2),
    )

    class FakeNotifier:
        def notify_warning(self, stage, issues):
            state.warnings.append(issues)

        def notify_success(self, stage, lines):
            state.successes.append(lines)

    monkeypatch.setattr("zer0factor.cli.daily_cmds.load_notifier", lambda cfg: FakeNotifier())
    state.config = _settings(tmp_path)
    return state


def _invoke(state, *args):
    return CliRunner().invoke(cli, ["--config", state.config, "update-daily", *args])


def test_dry_run_lists_steps_without_running(daily):
    result = _invoke(daily, "--dry-run")
    assert result.exit_code == 0, result.output
    assert daily.calls == []
    assert "目标截止日 20261106" in result.output
    for name in ("compute-returns", "compute-market-cap", "build-factors rolling_return",
                 "evaluate-factors（2 个因子，--incremental，基准 20261109_154727）"):
        assert name in result.output


def test_runs_all_steps_up_to_target_and_notifies_success(daily):
    result = _invoke(daily, "--family", "rolling_return", "--family", "ma_bias", "--workers", "4", "--notify")
    assert result.exit_code == 0, result.output
    names = [name for name, _ in daily.calls]
    assert names == ["returns", "market_cap", "build", "build", "evaluate"]
    returns = daily.calls[0][1]
    assert returns["incremental"] is True and returns["end_date"] == "20261106"
    assert [k["family_name"] for n, k in daily.calls if n == "build"] == ["rolling_return", "ma_bias"]
    assert all(k["end_date"] == "20261106" and k["workers"] == 4 for n, k in daily.calls if n == "build")
    evaluate = daily.calls[-1][1]
    assert evaluate["incremental"] is True
    assert evaluate["factor_names"] == ("z_a", "z_b")
    assert evaluate["periods"] == (1,) and evaluate["end_date"] is None
    assert daily.successes and not daily.warnings


def test_lagging_universe_updates_to_universe_end_and_alerts(daily):
    lag = "股票池落后于行情（行情截止 20261106）：univ_trade_base 截止 20261030。"
    daily.reports = [_report(target="20261030", universe_end="20261030", issues=[lag])]
    result = _invoke(daily, "--skip-eval", "--notify")
    assert result.exit_code == 0, result.output
    assert [n for n, _ in daily.calls] == ["returns", "market_cap", "build"]
    assert all(k["end_date"] == "20261030" for _, k in daily.calls)
    assert daily.warnings and lag in daily.warnings[0]


def test_failure_stops_and_exits_one(daily, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("zer0share unavailable")

    monkeypatch.setattr("zer0factor.cli.daily_cmds.compute_market_cap", broken)
    result = _invoke(daily, "--notify")
    assert result.exit_code == 1
    assert [n for n, _ in daily.calls] == ["returns"]
    assert any("zer0share unavailable" in line for line in daily.warnings[0])


def test_no_target_date_exits_one(daily):
    daily.reports = [_report(target=None, issues=["行情表没有数据：daily_kline"])]
    result = _invoke(daily, "--notify")
    assert result.exit_code == 1
    assert daily.calls == []
    assert daily.warnings == [["行情表没有数据：daily_kline"]]


def test_skips_evaluation_without_standard_run(daily, monkeypatch):
    monkeypatch.setattr("zer0factor.cli.daily_cmds.latest_standard_evaluation", lambda d, std: None)
    result = _invoke(daily)
    assert result.exit_code == 0, result.output
    assert "evaluate" not in [n for n, _ in daily.calls]


def test_full_eval_for_monthly_reconciliation(daily):
    result = _invoke(daily, "--full-eval")
    assert result.exit_code == 0, result.output
    assert daily.calls[-1][0] == "evaluate"
    assert daily.calls[-1][1]["incremental"] is False
    assert "全量" in result.output
