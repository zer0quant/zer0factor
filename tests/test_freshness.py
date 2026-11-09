from pathlib import Path

from zer0factor.freshness import check_freshness, format_report


def _touch(table_dir: Path, *dates: str) -> None:
    for d in dates:
        part = table_dir / f"date={d}"
        part.mkdir(parents=True, exist_ok=True)
        (part / "data.parquet").write_bytes(b"")


def _market(share: Path, end: str) -> None:
    for table in ("daily_kline", "daily_basic", "adj_factor"):
        _touch(share / "stock" / table, "20260102", end)


def _universe(share: Path, name: str, end: str) -> None:
    _touch(share / "stock" / "universe" / f"name={name}", "20260102", end)


def test_all_consistent(tmp_path):
    share, factors = tmp_path / "share", tmp_path / "factors"
    _market(share, "20261106")
    _universe(share, "univ_trade_base", "20261106")
    _touch(factors / "daily_return", "20261106")
    _touch(factors / "z_a", "20261106")

    report = check_freshness(
        zer0share_data_dir=share,
        factor_dir=factors,
        universes=["univ_trade_base", "univ_trade_base"],
        factor_groups={"base": ["daily_return"], "fam": ["a", "z_a"]},
        evaluation=("run1", "20261106", ("z_a",), 2),
    )

    assert report.ok, report.issues
    assert report.target_end == "20261106"
    assert list(report.universes) == ["univ_trade_base"]
    assert [g.name for g in report.factor_groups] == ["base", "fam"]
    assert report.factor_groups[1].built == 1  # unbuilt raw "a" is ignored
    assert "全部一致" in format_report(report)


def test_lagging_universe_caps_target_and_alerts(tmp_path):
    share, factors = tmp_path / "share", tmp_path / "factors"
    _market(share, "20261106")
    _universe(share, "univ_trade_base", "20260624")
    _touch(factors / "daily_return", "20260624")

    report = check_freshness(
        zer0share_data_dir=share,
        factor_dir=factors,
        universes=["univ_trade_base"],
        factor_groups={"base": ["daily_return"]},
        evaluation=("run1", "20260624", ("daily_return",), 2),
    )

    assert report.market_end == "20261106"
    assert report.universe_end == "20260624"
    assert report.target_end == "20260624"
    assert not report.ok
    assert len(report.issues) == 1
    assert "股票池落后" in report.issues[0]
    assert "univ_trade_base 截止 20260624" in report.issues[0]
    # factors up to the universe cut-off are not reported as lagging
    assert report.factor_groups[0].lagging == ()


def test_market_end_is_min_of_tables(tmp_path):
    share, factors = tmp_path / "share", tmp_path / "factors"
    _market(share, "20261106")
    _touch(share / "stock" / "adj_factor", "20261105")
    (share / "stock" / "adj_factor" / "date=20261106" / "data.parquet").unlink()
    _universe(share, "u", "20261106")

    report = check_freshness(
        zer0share_data_dir=share, factor_dir=factors, universes=["u"],
        factor_groups={}, evaluation=("r", "20261105", (), 2),
    )
    assert report.market_end == "20261105"
    assert report.target_end == "20261105"


def test_lagging_factors_and_evaluation(tmp_path):
    share, factors = tmp_path / "share", tmp_path / "factors"
    _market(share, "20261106")
    _universe(share, "u", "20261106")
    _touch(factors / "z_a", "20261106")
    _touch(factors / "z_b", "20260515")

    report = check_freshness(
        zer0share_data_dir=share,
        factor_dir=factors,
        universes=["u"],
        factor_groups={"fam": ["z_a", "z_b"]},
        evaluation=("run1", "20260515", ("z_a",), 0),
    )

    group = report.factor_groups[0]
    assert group.first_last_date == "20260515"
    assert group.latest_date == "20261106"
    assert group.lagging == ("z_b",)
    assert any("因子落后" in i and "1/2" in i for i in report.issues)
    assert any("评估落后" in i and "20261106" in i for i in report.issues)


def test_missing_data_and_no_evaluation(tmp_path):
    report = check_freshness(
        zer0share_data_dir=tmp_path / "share",
        factor_dir=tmp_path / "factors",
        universes=["u"],
        factor_groups={},
        evaluation=None,
    )
    assert report.target_end is None
    assert any("行情表没有数据" in i for i in report.issues)
    assert any("股票池没有数据" in i for i in report.issues)
    assert any("没有找到标准口径" in i for i in report.issues)
    assert report.to_dict()["ok"] is False


def _write_settings(tmp_path: Path) -> Path:
    config = tmp_path / "settings.toml"
    config.write_text(
        f"""
[zer0share]
data_dir = "{tmp_path / 'share'}"

[paths]
factor_dir = "{tmp_path / 'factors'}"
db_path = "{tmp_path / 'meta.duckdb'}"
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
    return config


def _write_standard_run(tmp_path: Path, run_id: str, end_date: str, factors: list[str]) -> None:
    import json

    import pandas as pd

    run = tmp_path / "evaluations" / run_id
    for f in factors:
        (run / "factors" / f).mkdir(parents=True, exist_ok=True)
    (run / "metadata.json").write_text(json.dumps({
        "run_id": run_id, "factor_names": factors, "start_date": "20160101",
        "end_date": None, "periods": [1], "quantiles": 10, "return_type": "open_t1",
        "universe": "univ_trade_base",
    }))
    pd.DataFrame({
        "factor_name": factors, "period": ["1D"] * len(factors), "end_date": [end_date] * len(factors),
    }).to_parquet(run / "summary.parquet")


def test_cli_ok_exit_zero(tmp_path):
    from click.testing import CliRunner

    from zer0factor.cli import cli

    _market(tmp_path / "share", "20261106")
    _universe(tmp_path / "share", "univ_trade_base", "20261106")
    _touch(tmp_path / "factors" / "daily_return", "20261106")
    _touch(tmp_path / "factors" / "z_daily_return_ma5", "20261106")
    _write_standard_run(tmp_path, "20261107_000000", "20261106", ["z_daily_return_ma5"])

    result = CliRunner().invoke(cli, ["--config", str(_write_settings(tmp_path)), "check-freshness"])
    assert result.exit_code == 0, result.output
    assert "全部一致" in result.output
    assert "rolling_return" in result.output


def test_cli_lagging_universe_exit_one_and_notifies(tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    from zer0factor.cli import cli

    _market(tmp_path / "share", "20261106")
    _universe(tmp_path / "share", "univ_trade_base", "20260624")
    _write_standard_run(tmp_path, "20261107_000000", "20260515", ["z_daily_return_ma5"])
    _touch(tmp_path / "factors" / "z_daily_return_ma5", "20260515")
    sent = []

    class FakeNotifier:
        def notify_warning(self, stage, issues):
            sent.append((stage, issues))

    monkeypatch.setattr("zer0factor.cli.freshness_cmds.load_notifier", lambda cfg: FakeNotifier())
    config = str(_write_settings(tmp_path))

    result = CliRunner().invoke(cli, ["--config", config, "check-freshness", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["target_end"] == "20260624"
    assert payload["ok"] is False
    assert sent == []

    result = CliRunner().invoke(cli, ["--config", config, "check-freshness", "--notify"])
    assert result.exit_code == 1
    assert "股票池落后" in result.output
    assert sent and sent[0][0] == "check-freshness"
    assert any("因子落后" in i for i in sent[0][1])


def test_evaluation_trailing_by_horizon_is_not_lagging(tmp_path):
    share, factors = tmp_path / "share", tmp_path / "factors"
    _market(share, "20261106")
    _universe(share, "u", "20261106")
    _touch(factors / "z_a", "20261103", "20261104", "20261105", "20261106")

    def run(data_end, horizon):
        return check_freshness(
            zer0share_data_dir=share, factor_dir=factors, universes=["u"],
            factor_groups={}, evaluation=("r", data_end, ("z_a",), horizon),
        )

    # open_t1 1D: the newest factor date has no forward return yet
    assert run("20261105", 2).ok
    assert run("20261104", 2).ok
    report = run("20261103", 2)
    assert not report.ok
    assert report.evaluation.expected_end_date == "20261104"
    assert any("评估落后" in i for i in report.issues)


def test_evaluation_horizon():
    from zer0factor.freshness import evaluation_horizon

    assert evaluation_horizon(["1D"], "open_t1") == 2
    assert evaluation_horizon(["1D", "5D", "10D"], "open_t1") == 11
    assert evaluation_horizon(["5D"], "close_t0") == 5
