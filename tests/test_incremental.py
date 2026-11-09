import pandas as pd
import pytest

from zer0factor.core import FactorFrame
from zer0factor.factors.builtin import MARKET_CAP_FACTORS, RETURN_FACTORS
from zer0factor.services.compute import (
    FactorComputeService,
    ZScorePostProcess,
    incremental_write_start,
    resolve_load_start,
)
from zer0factor.storage import FactorStorage


def _write(storage, name, dates):
    storage.write(name, pd.DataFrame({
        "trade_date": list(dates), "ts_code": ["A"] * len(dates), "value": [1.0] * len(dates),
    }))


def test_incremental_write_start_rebuilds_tail_of_oldest_output(tmp_path):
    storage = FactorStorage(tmp_path / "f", tmp_path / "m.duckdb")
    _write(storage, "a", ["20240102", "20240103", "20240104"])
    _write(storage, "b", ["20240102", "20240103"])

    assert incremental_write_start(storage, ["a", "b"], rebuild_tail=1) == "20240103"
    assert incremental_write_start(storage, ["a", "b"], rebuild_tail=2) == "20240102"
    assert incremental_write_start(storage, ["a", "b"], rebuild_tail=9) == "20240102"
    assert incremental_write_start(storage, ["a", "b"], rebuild_tail=0) == "20240104"


def test_incremental_write_start_none_when_any_output_never_built(tmp_path):
    storage = FactorStorage(tmp_path / "f", tmp_path / "m.duckdb")
    _write(storage, "a", ["20240102"])
    assert incremental_write_start(storage, ["a", "missing"], rebuild_tail=1) is None
    assert incremental_write_start(storage, [], rebuild_tail=1) is None


class PanelProvider:
    """Serves fixed open/close/mv panels, sliced like zer0share would."""

    def __init__(self, panels):
        self._panels = panels

    def history(self, fields, start_date, end_date, universe, adjust, progress=None):
        out = {}
        for f in fields:
            p = self._panels[f]
            mask = p.index >= pd.Timestamp(start_date)
            if end_date:
                mask &= p.index <= pd.Timestamp(end_date)
            out[f] = p.loc[mask]
        return FactorFrame(out)


def _panels():
    index = pd.bdate_range("2024-01-01", periods=30)
    rng = pd.Series(range(30), index=index, dtype=float)
    codes = ["A", "B", "C"]
    frame = lambda scale: pd.DataFrame({c: 10 + scale * (rng + i) ** 1.1 for i, c in enumerate(codes)})
    return {
        "open": frame(0.3), "close": frame(0.31),
        "total_mv": frame(5.0), "circ_mv": frame(3.0),
    }


def _calendar(index):
    days = [d.strftime("%Y%m%d") for d in index]

    def before(date, n):
        prior = [d for d in days if d < date]
        return prior[-n] if len(prior) >= n else prior[0]

    return before


@pytest.mark.parametrize(
    "factors, lookback, postprocess",
    [(RETURN_FACTORS, 1, False), (MARKET_CAP_FACTORS, 0, True)],
)
def test_incremental_build_equals_full_build(tmp_path, factors, lookback, postprocess):
    panels = _panels()
    provider = PanelProvider(panels)
    cutoff = panels["open"].index[19]

    def build(storage, start, end, load_start=None):
        return FactorComputeService(provider, storage).compute_and_store(
            factors, start_date=start, end_date=end, universe="all",
            load_start_date=load_start,
            postprocess=ZScorePostProcess(storage) if postprocess else None,
        )

    full = FactorStorage(tmp_path / "full", tmp_path / "full.duckdb")
    build(full, "20240101", None)

    inc = FactorStorage(tmp_path / "inc", tmp_path / "inc.duckdb")
    build(inc, "20240101", cutoff.strftime("%Y%m%d"))  # yesterday's state
    names = full.list_factors()
    write_start = incremental_write_start(inc, names, rebuild_tail=1)
    assert write_start == cutoff.strftime("%Y%m%d")
    load_start = resolve_load_start(
        lookback, write_start=write_start, history_start="20240101",
        trading_days_before=_calendar(panels["open"].index),
    )
    build(inc, write_start, None, load_start)

    for name in names:
        pd.testing.assert_frame_equal(inc.read(name), full.read(name), check_exact=False)


# --- CLI -------------------------------------------------------------------

from click.testing import CliRunner  # noqa: E402

from zer0factor.cli import cli  # noqa: E402


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
""".lstrip(),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def fake_service(monkeypatch):
    calls = []

    class FakeService:
        def __init__(self, provider, storage, *, log_info=None):
            pass

        def compute_and_store(self, factors, **kwargs):
            calls.append({"factors": tuple(f.spec.name for f in factors), **kwargs})
            return {}

    monkeypatch.setattr("zer0factor.cli.compute_cmds.FactorComputeService", FakeService)
    monkeypatch.setattr("zer0factor.context.AppContext.pro", None)
    calendar_calls = []

    def fake_calendar(pro, date, n):
        calendar_calls.append((date, n))
        return "20261104"

    monkeypatch.setattr("zer0factor.cli.compute_cmds.trading_days_before", fake_calendar)
    return calls, calendar_calls


def _storage(tmp_path):
    return FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")


def test_compute_returns_incremental_continues_from_last_date(tmp_path, fake_service):
    calls, calendar_calls = fake_service
    storage = _storage(tmp_path)
    for f in RETURN_FACTORS:
        _write(storage, f.spec.name, ["20261104", "20261105", "20261106"])

    result = CliRunner().invoke(cli, ["--config", _settings(tmp_path), "compute-returns", "--incremental"])

    assert result.exit_code == 0, result.output
    assert calls[0]["start_date"] == "20261106"  # last date rebuilt (rebuild-tail 1)
    assert calendar_calls == [("20261106", 1)]
    assert calls[0]["load_start_date"] == "20261104"
    assert calls[0]["end_date"] is None


def test_compute_returns_full_by_default_and_explicit_range(tmp_path, fake_service):
    calls, calendar_calls = fake_service
    config = _settings(tmp_path)

    assert CliRunner().invoke(cli, ["--config", config, "compute-returns"]).exit_code == 0
    assert calls[-1]["start_date"] == "20160101"
    assert calls[-1]["load_start_date"] == "20160101"
    assert calendar_calls == []

    result = CliRunner().invoke(
        cli, ["--config", config, "compute-returns", "--start-date", "20261101", "--end-date", "20261106"]
    )
    assert result.exit_code == 0, result.output
    assert calls[-1]["start_date"] == "20261101"
    assert calls[-1]["end_date"] == "20261106"
    assert calendar_calls == [("20261101", 1)]


def test_incremental_rejects_start_date(tmp_path, fake_service):
    result = CliRunner().invoke(
        cli,
        ["--config", _settings(tmp_path), "compute-returns", "--incremental", "--start-date", "20261101"],
    )
    assert result.exit_code == 2
    assert "--incremental" in result.output


def test_compute_market_cap_incremental_covers_zscored_outputs(tmp_path, fake_service):
    calls, calendar_calls = fake_service
    storage = _storage(tmp_path)
    for name in ("log_total_market_cap", "log_circulating_market_cap", "z_log_total_market_cap"):
        _write(storage, name, ["20261105", "20261106"])
    _write(storage, "z_log_circulating_market_cap", ["20261104", "20261105"])

    result = CliRunner().invoke(
        cli, ["--config", _settings(tmp_path), "compute-market-cap", "--incremental", "--rebuild-tail", "0"]
    )

    assert result.exit_code == 0, result.output
    assert calls[0]["start_date"] == "20261106"  # day after the oldest output's last date
    assert calls[0]["load_start_date"] == "20261106"  # lookback 0: no calendar lookup
    assert calendar_calls == []


def test_compute_returns_incremental_never_built_falls_back_to_full(tmp_path, fake_service):
    calls, _ = fake_service
    result = CliRunner().invoke(cli, ["--config", _settings(tmp_path), "compute-returns", "--incremental"])
    assert result.exit_code == 0, result.output
    assert calls[0]["start_date"] == "20160101"


def test_build_factors_incremental_derived_family(tmp_path, monkeypatch):
    from zer0factor.factor_registry import get_family

    family = get_family("rolling_return")
    storage = _storage(tmp_path)
    names = [*family.raw_names(), *family.preprocess_output_names()]
    for name in names[:-1]:
        _write(storage, name, ["20261105", "20261106"])
    _write(storage, names[-1], ["20260514", "20260515"])  # one preprocess output lags
    calls = []

    def fake_run_build_stage(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr("zer0factor.cli.compute_cmds.run_build_stage", fake_run_build_stage)
    monkeypatch.setattr("zer0factor.context.AppContext.pro", None)

    result = CliRunner().invoke(
        cli,
        ["--config", _settings(tmp_path), "build-factors", "--family", "rolling_return", "--incremental"],
    )
    assert result.exit_code == 0, result.output
    assert calls[0]["start_date"] == "20260515"

    # raw stage only looks at raw outputs
    result = CliRunner().invoke(
        cli,
        [
            "--config", _settings(tmp_path), "build-factors", "--family", "rolling_return",
            "--stage", "raw", "--incremental",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls[1]["start_date"] == "20261106"


def test_build_factors_incremental_rejects_qfq_family(tmp_path, monkeypatch):
    import sys
    import types

    from zer0factor.core import FactorSpec
    from zer0factor.families import FactorFamily

    class QfqFactor:
        spec = FactorSpec(name="qfq_x", inputs=["close"], min_window=1, adjust="qfq")

    class QfqFamily(FactorFamily):
        name = "qfq_family"
        base_factors = ("x",)
        windows = (1,)
        uses_data_provider = True
        profiles = ()

        def raw_name(self, base_factor, window):
            return "qfq_x"

        def derive(self, panel, window):
            raise NotImplementedError

        def factors(self):
            return (QfqFactor(),)

    module = types.ModuleType("fake_qfq_family")
    module.FAMILY = QfqFamily()
    monkeypatch.setitem(sys.modules, "fake_qfq_family", module)
    config = tmp_path / "settings.toml"
    config.write_text(
        open(_settings(tmp_path), encoding="utf-8").read()
        + '\n[external_families]\nqfq_family = "fake_qfq_family:FAMILY"\n',
        encoding="utf-8",
    )
    _write(_storage(tmp_path), "qfq_x", ["20261106"])
    monkeypatch.setattr("zer0factor.context.AppContext.pro", None)

    result = CliRunner().invoke(
        cli,
        ["--config", str(config), "build-factors", "--family", "qfq_family", "--stage", "raw", "--incremental"],
    )
    assert result.exit_code == 2
    assert "qfq" in result.output


def test_derived_family_incremental_raw_equals_full(tmp_path):
    from zer0factor.factor_registry import get_family
    from zer0factor.pipeline import compute_raw_family_factors

    family = get_family("rolling_return")
    panels = _panels()

    def seeded(path):
        storage = FactorStorage(tmp_path / path, tmp_path / f"{path}.duckdb")
        FactorComputeService(PanelProvider(panels), storage).compute_and_store(
            RETURN_FACTORS, start_date="20240101", end_date=None, universe="all"
        )
        return storage

    full = seeded("full")
    compute_raw_family_factors(family, storage=full, start_date=None, end_date=None, windows=(5, 10))

    inc = seeded("inc")
    cutoff = panels["open"].index[19].strftime("%Y%m%d")
    compute_raw_family_factors(family, storage=inc, start_date=None, end_date=cutoff, windows=(5, 10))
    start = incremental_write_start(
        inc, [family.raw_name(b, w) for b in family.base_factors for w in (5, 10)], rebuild_tail=1
    )
    assert start == cutoff
    compute_raw_family_factors(family, storage=inc, start_date=start, end_date=None, windows=(5, 10))

    for base in family.base_factors:
        for window in (5, 10):
            name = family.raw_name(base, window)
            pd.testing.assert_frame_equal(inc.read(name), full.read(name))
