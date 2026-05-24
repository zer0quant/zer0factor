from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from main import (
    MARKET_CAP_FACTORS,
    RETURN_FACTORS,
    cli,
    compute_and_store_factors,
    compute_and_store_market_cap_factors,
    neutralize_stored_factor,
    preprocess_stored_factor,
    read_universe_panel,
    standardize_stored_factor,
)
from zer0factor.core import FactorFrame
from zer0factor.storage import FactorStorage


class FakeProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["close", "open"]
        assert start_date == "20240101"
        assert end_date == "20240103"
        assert universe == "000001.SZ"
        assert adjust == "hfq"
        if progress is not None:
            progress(0, 1, "")
            progress(1, 1, "000001.SZ")

        index = pd.date_range("2024-01-01", periods=3, freq="D")
        open_ = pd.DataFrame({"000001.SZ": [10.0, 11.0, 12.0]}, index=index)
        close = pd.DataFrame({"000001.SZ": [10.5, 12.0, 12.6]}, index=index)
        return FactorFrame({"open": open_, "close": close})


class FakeMarketCapProvider:
    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        assert fields == ["circ_mv", "total_mv"]
        assert start_date == "20240101"
        assert end_date == "20240102"
        assert universe == "000001.SZ,000002.SZ"
        assert adjust is None

        index = pd.date_range("2024-01-01", periods=2, freq="D")
        total_mv = pd.DataFrame(
            {"000001.SZ": [100.0, 110.0], "000002.SZ": [200.0, 220.0]},
            index=index,
        )
        circ_mv = pd.DataFrame(
            {"000001.SZ": [50.0, 55.0], "000002.SZ": [80.0, 88.0]},
            index=index,
        )
        return FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})


class FakeUniversePro:
    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        assert universe == "univ_trade_base"
        assert fields == "trade_date,universe,ts_code"
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240101", "20240102"],
                "universe": ["univ_trade_base"] * 3,
                "ts_code": ["000001.SZ", "000003.SZ", "000002.SZ"],
            }
        )


def test_compute_and_store_return_factors(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")

    row_counts = compute_and_store_factors(
        factors=RETURN_FACTORS,
        provider=FakeProvider(),
        storage=storage,
        start_date="20240101",
        end_date="20240103",
        universe="000001.SZ",
    )

    assert row_counts == {
        "daily_return": 2,
        "open_return": 2,
        "intraday_return": 3,
        "overnight_return": 2,
    }
    assert storage.list_factors() == [
        "daily_return",
        "intraday_return",
        "open_return",
        "overnight_return",
    ]


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
    assert sorted(storage.list_factors()) == [
        "log_circulating_market_cap",
        "log_total_market_cap",
        "z_log_circulating_market_cap",
        "z_log_total_market_cap",
    ]

    z_total = storage.read("z_log_total_market_cap")
    assert sorted(z_total["trade_date"].astype(str).unique()) == ["20240101", "20240102"]
    assert z_total.groupby("trade_date")["value"].mean().abs().max() < 1e-12


def test_compute_market_cap_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["compute-market-cap", "--help"])

    assert result.exit_code == 0
    assert "Compute built-in market cap factors" in result.output


def test_neutralize_factor_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["neutralize-factor", "--help"])

    assert result.exit_code == 0
    assert "Neutralize a standardized factor and standardize the residual" in result.output
    assert "--size-factor-name" in result.output


def test_evaluate_factor_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["evaluate-factor", "--help"])

    assert result.exit_code == 0
    assert "Evaluate one stored factor" in result.output
    assert "--periods" in result.output
    assert "--return-type" in result.output


def test_evaluate_factors_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["evaluate-factors", "--help"])

    assert result.exit_code == 0
    assert "Evaluate one or more stored factors" in result.output
    assert "--universe" in result.output
    assert "--output-dir" in result.output


def test_evaluate_batch_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["evaluate-batch", "--help"])

    assert result.exit_code == 0
    assert "Evaluate factors from a TOML batch file" in result.output
    assert "--file" in result.output


def test_evaluate_summary_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["evaluate-summary", "--help"])

    assert result.exit_code == 0
    assert "Summarize an evaluation run" in result.output
    assert "--min-ic" in result.output
    assert "--min-monotonicity" in result.output
    assert "--run-dir" in result.output


def test_evaluate_summary_command_prints_report_paths(monkeypatch, tmp_path):
    runner = CliRunner()

    class FakeReport:
        run_dir = tmp_path / "evaluations" / "run_001"
        report_path = run_dir / "report.md"
        ranked_summary_path = run_dir / "ranked_summary.csv"
        ranked_summary = pd.DataFrame(
            {
                "factor_name": ["factor_a"],
                "period": ["1D"],
                "score": [3.1],
                "passed": [True],
            }
        )

    def fake_generate_evaluation_report(**kwargs):
        assert kwargs["run_dir"] == tmp_path / "run_001"
        assert kwargs["thresholds"].min_ic == 0.01
        assert kwargs["thresholds"].min_monotonicity == 0.4
        return FakeReport()

    monkeypatch.setattr("main.generate_evaluation_report", fake_generate_evaluation_report)

    result = runner.invoke(
        cli,
        [
            "evaluate-summary",
            "--run-dir",
            str(tmp_path / "run_001"),
            "--min-ic",
            "0.01",
            "--min-monotonicity",
            "0.4",
        ],
    )

    assert result.exit_code == 0
    assert "Report written to" in result.output
    assert "factor_a" in result.output


def test_evaluate_batch_command_runs_evaluation_and_report(monkeypatch, tmp_path):
    runner = CliRunner()
    batch_file = tmp_path / "batch.toml"
    batch_file.write_text(
        """
[evaluation]
factors = ["factor_a", "factor_b"]
start_date = "20240101"
end_date = "20240131"
periods = [1, 5]
quantiles = 5
return_type = "close_t0"
universe = "000001.SZ,000002.SZ"
max_loss = 0.25
output_dir = "batch_evaluations"

[report]
min_ic = 0.01
min_monotonicity = 0.4
""",
        encoding="utf-8",
    )

    def fake_load_config(path):
        return type(
            "Config",
            (),
            {
                "factor_dir": tmp_path / "factors",
                "db_path": tmp_path / "factor.duckdb",
                "log_path": tmp_path / "factor.log",
                "start_date": "20230101",
                "end_date": "20231231",
                "zer0share_data_dir": tmp_path / "zer0share",
            },
        )()

    class FakeLocalPro:
        def __init__(self, data_dir):
            self.data_dir = data_dir

    class FakeRunResult:
        run_id = "run_001"
        output_dir = tmp_path / "batch_evaluations" / "run_001"
        factor_results = (object(), object())

    class FakeReport:
        report_path = FakeRunResult.output_dir / "report.md"
        ranked_summary_path = FakeRunResult.output_dir / "ranked_summary.csv"
        ranked_summary = pd.DataFrame(
            {
                "factor_name": ["factor_a"],
                "period": ["1D"],
                "adjusted_score": [4.2],
                "passed": [True],
            }
        )

    def fake_evaluate_factors(*, factor_names, config, log_info, **kwargs):
        assert factor_names == ("factor_a", "factor_b")
        assert config.factor_names == ("factor_a", "factor_b")
        assert config.start_date == "20240101"
        assert config.end_date == "20240131"
        assert config.periods == (1, 5)
        assert config.quantiles == 5
        assert config.return_type == "close_t0"
        assert config.universe == "000001.SZ,000002.SZ"
        assert config.max_loss == 0.25
        assert config.output_dir == Path("batch_evaluations")
        log_info("batch_eval_progress")
        return FakeRunResult()

    def fake_generate_evaluation_report(**kwargs):
        assert kwargs["run_dir"] == FakeRunResult.output_dir
        assert kwargs["thresholds"].min_ic == 0.01
        assert kwargs["thresholds"].min_monotonicity == 0.4
        return FakeReport()

    monkeypatch.setattr("main.load_config", fake_load_config)
    monkeypatch.setattr("main.evaluate_factors", fake_evaluate_factors)
    monkeypatch.setattr("main.generate_evaluation_report", fake_generate_evaluation_report)
    import zer0share.api

    monkeypatch.setattr(zer0share.api, "LocalPro", FakeLocalPro)

    result = runner.invoke(
        cli,
        [
            "--config",
            str(tmp_path / "settings.toml"),
            "evaluate-batch",
            "--file",
            str(batch_file),
        ],
    )

    assert result.exit_code == 0
    assert "batch_eval_progress" in result.output
    assert "Evaluation run run_001 written to" in result.output
    assert "Report written to" in result.output
    assert "factor_a" in result.output


def test_evaluate_factor_command_prints_progress(monkeypatch, tmp_path):
    runner = CliRunner()

    def fake_load_config(path):
        return type(
            "Config",
            (),
            {
                "factor_dir": tmp_path / "factors",
                "db_path": tmp_path / "factor.duckdb",
                "log_path": tmp_path / "factor.log",
                "start_date": "20240101",
                "end_date": "20240102",
                "zer0share_data_dir": tmp_path / "zer0share",
            },
        )()

    class FakeLocalPro:
        def __init__(self, data_dir):
            self.data_dir = data_dir

    class FakeRunResult:
        run_id = "run_001"
        output_dir = tmp_path / "evaluations" / "run_001"
        factor_results = (object(),)

    def fake_evaluate_factors(*, log_info, **kwargs):
        log_info("evaluation_run_started factors=1")
        log_info("evaluation_price_load_started start_date=20240101 end_date=20240115")
        return FakeRunResult()

    monkeypatch.setattr("main.load_config", fake_load_config)
    monkeypatch.setattr("main.evaluate_factors", fake_evaluate_factors)
    import zer0share.api

    monkeypatch.setattr(zer0share.api, "LocalPro", FakeLocalPro)

    result = runner.invoke(
        cli,
        [
            "--config",
            str(tmp_path / "settings.toml"),
            "evaluate-factor",
            "factor_a",
            "--output-dir",
            str(tmp_path / "evaluations"),
        ],
    )

    assert result.exit_code == 0
    assert "evaluation_run_started factors=1" in result.output
    assert "evaluation_price_load_started start_date=20240101 end_date=20240115" in result.output
    assert "Evaluation run run_001 written to" in result.output


def test_standardize_factor_command_is_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["standardize-factor", "--help"])

    assert result.exit_code == 0
    assert "Standardize a stored factor" in result.output
    assert "--output-name" in result.output


def test_standardize_stored_factor_writes_z_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    source = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 4,
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
            "value": [1.0, 2.0, None, 100.0],
        }
    )
    storage.write("daily_return", source)

    rows = standardize_stored_factor(
        factor_name="daily_return",
        output_name="z_daily_return",
        storage=storage,
        start_date="20240101",
        end_date="20240101",
    )

    result = storage.read("z_daily_return")
    assert rows == 4
    assert len(result) == 4
    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result["trade_date"].astype(str).unique().tolist() == ["20240101"]
    assert "z_daily_return" in storage.list_factors()

    row = result.sort_values("ts_code")["value"]
    assert row.isna().sum() == 0
    assert row.mean() == pytest.approx(0.0)
    assert row.std() == pytest.approx(1.0)


def test_standardize_stored_factor_filters_by_process_universe(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    source = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 4,
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
            "value": [1.0, 2.0, 3.0, 100.0],
        }
    )
    storage.write("daily_return", source)

    rows = standardize_stored_factor(
        factor_name="daily_return",
        output_name="z_daily_return",
        storage=storage,
        start_date="20240101",
        end_date="20240101",
        universe=read_universe_panel(
            FakeUniversePro(),
            universe_name="univ_trade_base",
            start_date="20240101",
            end_date="20240101",
        ),
    )

    result = storage.read("z_daily_return")
    assert rows == 2
    assert result["ts_code"].tolist() == ["000001.SZ", "000003.SZ"]
    assert result["value"].mean() == pytest.approx(0.0)
    assert result["value"].std() == pytest.approx(1.0)


def test_preprocess_stored_factor_alias_matches_standardize_stored_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "daily_return",
        pd.DataFrame(
            {
                "trade_date": ["20240101"] * 3,
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "value": [1.0, 2.0, 3.0],
            }
        ),
    )

    rows = preprocess_stored_factor(
        factor_name="daily_return",
        output_name="z_daily_return",
        storage=storage,
    )

    assert rows == 3
    assert "z_daily_return" in storage.list_factors()


class FakeIndustryNeutralizationPro:
    def index_member_all(self, fields=None):
        assert fields == "l1_code,l1_name,ts_code,in_date,out_date,is_new"
        return pd.DataFrame(
            {
                "l1_code": [
                    "801010.SI",
                    "801010.SI",
                    "801020.SI",
                    "801020.SI",
                    "801030.SI",
                    "801030.SI",
                ],
                "l1_name": ["a", "a", "b", "b", "c", "c"],
                "ts_code": [
                    "000001.SZ",
                    "000002.SZ",
                    "000003.SZ",
                    "000004.SZ",
                    "000005.SZ",
                    "000006.SZ",
                ],
                "in_date": ["2020-01-01"] * 6,
                "out_date": [None] * 6,
                "is_new": ["Y"] * 6,
            }
        )


def test_neutralize_stored_factor_reads_z_factor_and_writes_standardized_neutral_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    source = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": [
                "000001.SZ",
                "000002.SZ",
                "000003.SZ",
                "000004.SZ",
                "000005.SZ",
                "000006.SZ",
            ],
            "value": [11.0, 13.0, 17.0, 19.0, 23.0, 29.0],
        }
    )
    size = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": [
                "000001.SZ",
                "000002.SZ",
                "000003.SZ",
                "000004.SZ",
                "000005.SZ",
                "000006.SZ",
            ],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    storage.write("z_demo_factor", source)
    storage.write("z_log_circulating_market_cap", size)

    rows = neutralize_stored_factor(
        factor_name="demo_factor",
        output_name="z_neu_demo_factor",
        storage=storage,
        pro=FakeIndustryNeutralizationPro(),
        start_date="20240101",
        end_date="20240101",
    )

    result = storage.read("z_neu_demo_factor")
    assert rows == 6
    assert len(result) == 6
    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result["trade_date"].astype(str).unique().tolist() == ["20240101"]
    assert "z_neu_demo_factor" in storage.list_factors()

    residuals = result.set_index("ts_code")["value"].sort_index()
    industry = pd.Series(
        {
            "000001.SZ": "801010.SI",
            "000002.SZ": "801010.SI",
            "000003.SZ": "801020.SI",
            "000004.SZ": "801020.SI",
            "000005.SZ": "801030.SI",
            "000006.SZ": "801030.SI",
        }
    ).loc[residuals.index]
    size_values = size.set_index("ts_code")["value"].loc[residuals.index]
    design = pd.DataFrame(
        {"intercept": 1.0, "size": size_values},
        index=residuals.index,
    )
    design = pd.concat(
        [design, pd.get_dummies(industry, drop_first=True, dtype=float)],
        axis=1,
    )
    assert abs(residuals.sum()) < 1e-10
    assert abs(design.T.to_numpy() @ residuals.to_numpy()).max() < 1e-10
    assert residuals.mean() == pytest.approx(0.0)
    assert residuals.std() == pytest.approx(1.0)


def test_neutralize_stored_factor_filters_by_process_universe(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    source = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": [
                "000001.SZ",
                "000002.SZ",
                "000003.SZ",
                "000004.SZ",
                "000005.SZ",
                "000006.SZ",
            ],
            "value": [11.0, 13.0, 17.0, 19.0, 23.0, 29.0],
        }
    )
    size = pd.DataFrame(
        {
            "trade_date": ["20240101"] * 6,
            "ts_code": [
                "000001.SZ",
                "000002.SZ",
                "000003.SZ",
                "000004.SZ",
                "000005.SZ",
                "000006.SZ",
            ],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    storage.write("z_demo_factor", source)
    storage.write("z_log_circulating_market_cap", size)

    rows = neutralize_stored_factor(
        factor_name="demo_factor",
        output_name="z_neu_demo_factor",
        storage=storage,
        pro=FakeIndustryNeutralizationPro(),
        start_date="20240101",
        end_date="20240101",
        universe=pd.DataFrame(
            True,
            index=pd.to_datetime(["2024-01-01"]),
            columns=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
        ),
    )

    result = storage.read("z_neu_demo_factor")
    assert rows == 4
    assert result["ts_code"].tolist() == [
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
        "000004.SZ",
    ]


def _write_settings(tmp_path, factor_dir, db_path):
    p = tmp_path / "settings.toml"
    p.write_text(f"""
[zer0share]
data_dir = "."

[paths]
factor_dir = "{factor_dir}"
db_path = "{db_path}"
log_path = "{tmp_path / 'factor.log'}"

[factor]
universe = "all"
process_universe = "univ_trade_base"
start_date = "20240101"
end_date = ""
""")
    return p


def _write_registry_toml(tmp_path, content: str):
    p = tmp_path / "factors.toml"
    p.write_text(content)
    return p


def test_factor_list_command_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["factor-list", "--help"])
    assert result.exit_code == 0
    assert "factor-list" in result.output or "List" in result.output


def test_factor_list_shows_registered_and_orphan(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry_toml(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""

[[factors]]
name = "z_neu_open_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240103"],
        "ts_code": ["000001.SZ", "000001.SZ"],
        "value": [0.1, 0.2],
    })
    storage.write("z_neu_daily_return", df)
    storage.write("z_orphan_factor", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-list",
        "--registry", str(registry_toml),
    ])
    assert result.exit_code == 0
    assert "z_neu_daily_return" in result.output
    assert "z_neu_open_return" in result.output
    assert "z_orphan_factor" in result.output
    assert "registered but missing" in result.output
    assert "stored but unregistered" in result.output


def test_factor_list_registered_flag_hides_orphans(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry_toml(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240103"],
        "ts_code": ["000001.SZ", "000001.SZ"],
        "value": [0.1, 0.2],
    })
    storage.write("z_neu_daily_return", df)
    storage.write("z_orphan", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-list",
        "--registry", str(registry_toml),
        "--registered",
    ])
    assert result.exit_code == 0
    assert "z_orphan" not in result.output


def test_factor_list_orphan_flag_shows_only_orphans(tmp_path):
    factor_dir = tmp_path / "factors"
    db_path = tmp_path / "meta.duckdb"
    settings = _write_settings(tmp_path, factor_dir, db_path)

    registry_toml = _write_registry_toml(tmp_path, """
[[factors]]
name = "z_neu_daily_return"
category = "price"
source_type = "neutralized"
enabled = true
description = ""
""")

    storage = FactorStorage(factor_dir, db_path)
    df = pd.DataFrame({
        "trade_date": ["20240102", "20240103"],
        "ts_code": ["000001.SZ", "000001.SZ"],
        "value": [0.1, 0.2],
    })
    storage.write("z_orphan", df)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "--config", str(settings),
        "factor-list",
        "--registry", str(registry_toml),
        "--orphan",
    ])
    assert result.exit_code == 0
    assert "z_orphan" in result.output
    assert "z_neu_daily_return" not in result.output
