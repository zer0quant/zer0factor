import warnings

import pandas as pd
import pytest

from zer0factor.eval import EvaluationConfig, evaluate_factor, evaluate_factors
from zer0factor.eval.loaders import load_price_data, load_universe_panel
from zer0factor.eval.pipeline import _calculate_period_sample_counts
from zer0factor.storage import FactorStorage


class FakePro:
    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        assert ts_code is None
        assert start_date == "20240101"
        assert end_date is not None
        return pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102", "20240103", "20240104"],
                "ts_code": ["000001.SZ"] * 4,
                "open": [10.0, 11.0, 12.0, 13.0],
                "close": [10.5, 11.5, 12.5, 13.5],
            }
        )


class RecordingPricePro(FakePro):
    def __init__(self):
        self.end_date = None
        self.ts_code = "not-called"

    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        self.ts_code = ts_code
        self.end_date = end_date
        return super().pro_bar(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            adj=adj,
        )


class UniversePro:
    def __init__(self, rows):
        self.rows = rows

    def universe(self, universe=None, start_date=None, end_date=None, fields=None):
        return pd.DataFrame(self.rows)


def write_factor_a(storage):
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101", "20240102"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )


def patch_clean_factor_data(monkeypatch):
    patch_clean_factor_data_for_periods(monkeypatch, ("1D",))


def patch_clean_factor_data_for_periods(monkeypatch, periods):
    clean = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 2],
            **{period: [0.01, 0.02] for period in periods},
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )

    def fake_clean_factor_and_forward_returns(*args, **kwargs):
        return clean

    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        fake_clean_factor_and_forward_returns,
    )


def patch_empty_clean_factor_data(monkeypatch):
    empty = pd.DataFrame(
        {
            "factor": pd.Series(dtype="float64"),
            "1D": pd.Series(dtype="float64"),
            "factor_quantile": pd.Series(dtype="int64"),
        },
        index=pd.MultiIndex.from_tuples([], names=["date", "asset"]),
    )

    def fake_clean_factor_and_forward_returns(*args, **kwargs):
        return empty

    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        fake_clean_factor_and_forward_returns,
    )


def test_calculate_period_sample_counts_cleans_each_period_independently(monkeypatch):
    index_1d = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "000001.SZ"),
            (pd.Timestamp("2024-01-02"), "000001.SZ"),
            (pd.Timestamp("2024-01-03"), "000001.SZ"),
        ],
        names=["date", "asset"],
    )
    index_5d = index_1d[:2]

    def fake_clean_factor_and_forward_returns(*args, **kwargs):
        periods = kwargs["periods"]
        period = periods[0]
        index = index_1d if period == 1 else index_5d
        return pd.DataFrame(
            {
                "factor": [1.0] * len(index),
                "factor_quantile": [1] * len(index),
                f"{period}D": [0.01] * len(index),
            },
            index=index,
        )

    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        fake_clean_factor_and_forward_returns,
    )

    counts = _calculate_period_sample_counts(
        pd.Series(dtype=float),
        pd.DataFrame(),
        quantiles=2,
        periods=(1, 5),
        max_loss=0.35,
    )

    assert counts == {"1D": 3, "5D": 2}


def make_config(tmp_path, **overrides):
    values = {
        "factor_names": ("factor_a",),
        "start_date": "20240101",
        "end_date": "20240102",
        "periods": (1,),
        "quantiles": 2,
        "output_dir": tmp_path / "evaluations",
    }
    values.update(overrides)
    return EvaluationConfig(
        **values,
    )


def test_evaluate_factors_writes_run_artifacts(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_clean_factor_data(monkeypatch)

    config = make_config(tmp_path)

    result = evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=FakePro(),
        config=config,
        run_id="run_001",
    )

    assert result.run_id == "run_001"
    assert result.summary["factor_name"].tolist() == ["factor_a"]
    assert (result.output_dir / "summary.csv").exists()
    assert (result.output_dir / "metadata.json").exists()
    factor_dir = result.output_dir / "factors" / "factor_a"
    assert (factor_dir / "clean_factor_data.parquet").exists()
    assert (factor_dir / "daily_ic.parquet").exists()
    assert (factor_dir / "quantile_returns.parquet").exists()
    assert (factor_dir / "figures" / "quantile_returns_1D.png").exists()
    assert not (factor_dir / "figures" / "quantile_returns_5D.png").exists()


def test_evaluate_factors_reports_stage_progress(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_clean_factor_data(monkeypatch)
    messages = []

    evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=FakePro(),
        config=make_config(tmp_path),
        run_id="run_001",
        log_info=messages.append,
    )

    assert messages == [
        "evaluation_run_started factors=1 start_date=20240101 "
        "end_date=20240102 periods=1 return_type=open_t1",
        "evaluation_price_load_started start_date=20240101 end_date=20240102",
        "evaluation_price_load_finished rows=4",
        "evaluation_factor_started factor=factor_a",
        "evaluation_factor_load_finished factor=factor_a rows=2",
        "evaluation_clean_factor_started factor=factor_a",
        "evaluation_clean_factor_finished factor=factor_a rows=2",
        "evaluation_metrics_finished factor=factor_a periods=1",
        "evaluation_artifacts_written factor=factor_a output_dir="
        + str(tmp_path / "evaluations" / "run_001" / "factors" / "factor_a"),
        "evaluation_run_finished run_id=run_001 output_dir="
        + str(tmp_path / "evaluations" / "run_001")
        + " factors=1",
    ]


def test_evaluate_factor_derives_factor_artifact_dir_from_run_dir(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_clean_factor_data(monkeypatch)

    config = make_config(tmp_path)
    run_dir = tmp_path / "evaluations" / "run_001"

    result = evaluate_factor(
        factor_name="factor_a",
        storage=storage,
        pro=FakePro(),
        config=config,
        run_dir=run_dir,
    )

    factor_dir = run_dir / "factors" / "factor_a"
    assert result.output_dir == factor_dir
    assert (factor_dir / "clean_factor_data.parquet").exists()
    assert (factor_dir / "daily_ic.parquet").exists()
    assert (factor_dir / "quantile_returns.parquet").exists()
    assert (factor_dir / "figures" / "quantile_returns_1D.png").exists()


def test_evaluate_factor_writes_quantile_return_figure_for_each_period(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_clean_factor_data_for_periods(monkeypatch, ("1D", "5D"))

    config = make_config(tmp_path, periods=(1, 5))
    run_dir = tmp_path / "evaluations" / "run_001"

    evaluate_factor(
        factor_name="factor_a",
        storage=storage,
        pro=FakePro(),
        config=config,
        run_dir=run_dir,
    )

    figures_dir = run_dir / "factors" / "factor_a" / "figures"
    assert (figures_dir / "quantile_returns_1D.png").exists()
    assert (figures_dir / "quantile_returns_5D.png").exists()


def test_evaluate_factor_rejects_factor_name_not_in_config(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    config = make_config(tmp_path, factor_names=("other_factor",))

    with pytest.raises(
        ValueError, match="factor_name must be included in config.factor_names"
    ):
        evaluate_factor(
            factor_name="factor_a",
            storage=storage,
            pro=FakePro(),
            config=config,
            run_dir=tmp_path / "evaluations" / "run_001",
        )


def test_evaluate_factor_rejects_empty_stored_factor_data(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": pd.Series(dtype="object"),
                "ts_code": pd.Series(dtype="object"),
                "value": pd.Series(dtype="float64"),
            }
        ),
    )
    patch_clean_factor_data(monkeypatch)
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="factor_a.*no factor data"):
        evaluate_factor(
            factor_name="factor_a",
            storage=storage,
            pro=FakePro(),
            config=config,
            run_dir=tmp_path / "evaluations" / "run_001",
        )


def test_evaluate_factor_rejects_empty_data_after_universe_filtering(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_clean_factor_data(monkeypatch)
    config = make_config(tmp_path)
    universe_panel = pd.DataFrame(
        False,
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        columns=["000001.SZ"],
    )

    with pytest.raises(
        ValueError, match="factor_a.*no factor data after universe filtering"
    ):
        evaluate_factor(
            factor_name="factor_a",
            storage=storage,
            pro=FakePro(),
            config=config,
            run_dir=tmp_path / "evaluations" / "run_001",
            universe_panel=universe_panel,
        )


def test_evaluate_factor_rejects_empty_clean_factor_data(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_empty_clean_factor_data(monkeypatch)
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="factor_a.*no clean factor data"):
        evaluate_factor(
            factor_name="factor_a",
            storage=storage,
            pro=FakePro(),
            config=config,
            run_dir=tmp_path / "evaluations" / "run_001",
        )


def test_evaluate_factor_filters_alphalens_pct_change_future_warning(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    clean = pd.DataFrame(
        {
            "factor": [1.0, 2.0],
            "factor_quantile": [1, 2],
            "1D": [0.01, 0.02],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), "000001.SZ"),
                (pd.Timestamp("2024-01-02"), "000001.SZ"),
            ],
            names=["date", "asset"],
        ),
    )

    def fake_clean_factor_and_forward_returns(*args, **kwargs):
        warnings.warn(
            "The default fill_method='pad' in DataFrame.pct_change is deprecated "
            "and will be removed in a future version.",
            FutureWarning,
            stacklevel=2,
        )
        return clean

    monkeypatch.setattr(
        "zer0factor.eval.pipeline.get_clean_factor_and_forward_returns",
        fake_clean_factor_and_forward_returns,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        evaluate_factor(
            factor_name="factor_a",
            storage=storage,
            pro=FakePro(),
            config=make_config(tmp_path),
            run_dir=tmp_path / "evaluations" / "run_001",
        )

    assert not [
        warning
        for warning in caught
        if warning.category is FutureWarning
        and "DataFrame.pct_change is deprecated" in str(warning.message)
    ]


def test_evaluate_factor_rejects_quantile_returns_without_periods(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)
    patch_clean_factor_data(monkeypatch)
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.calculate_quantile_returns",
        lambda clean_factor_data: pd.DataFrame(index=[1, 2]),
    )
    monkeypatch.setattr(
        "zer0factor.eval.pipeline.build_summary",
        lambda **kwargs: pd.DataFrame({"factor_name": ["factor_a"]}),
    )
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="factor_a.*no quantile return periods"):
        evaluate_factor(
            factor_name="factor_a",
            storage=storage,
            pro=FakePro(),
            config=config,
            run_dir=tmp_path / "evaluations" / "run_001",
        )


def test_load_price_data_extends_end_date_with_conservative_buffer():
    pro = RecordingPricePro()

    load_price_data(
        pro,
        start_date="20240101",
        end_date="20240102",
        periods=(5,),
    )

    assert pro.ts_code is None
    assert pro.end_date == "20240127"


def test_evaluate_factors_open_ended_price_window_uses_factor_max_date(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101", "20240220"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    patch_clean_factor_data(monkeypatch)
    pro = RecordingPricePro()
    config = make_config(tmp_path, end_date=None)

    evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=pro,
        config=config,
        run_id="run_001",
    )

    assert pro.end_date == "20240304"


def test_evaluate_factors_open_ended_price_window_accepts_float_trade_dates(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": [20240101.0, 20240220.0],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    patch_clean_factor_data(monkeypatch)
    pro = RecordingPricePro()
    config = make_config(tmp_path, end_date=None)

    evaluate_factors(
        factor_names=("factor_a",),
        storage=storage,
        pro=pro,
        config=config,
        run_id="run_001",
    )

    assert pro.end_date == "20240304"


def test_evaluate_factor_open_ended_price_window_uses_factor_max_date(
    tmp_path, monkeypatch
):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "factor_a",
        pd.DataFrame(
            {
                "trade_date": ["20240101", "20240220"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "value": [1.0, 2.0],
            }
        ),
    )
    patch_clean_factor_data(monkeypatch)
    pro = RecordingPricePro()
    config = make_config(tmp_path, end_date=None)

    evaluate_factor(
        factor_name="factor_a",
        storage=storage,
        pro=pro,
        config=config,
        run_dir=tmp_path / "evaluations" / "run_001",
    )

    assert pro.end_date == "20240304"


def test_load_universe_panel_rejects_missing_required_columns():
    pro = UniversePro([{"trade_date": "20240101", "symbol": "000001.SZ"}])

    with pytest.raises(ValueError, match="universe data must contain"):
        load_universe_panel(
            pro,
            universe_name="demo",
            start_date="20240101",
            end_date="20240102",
        )


def test_load_universe_panel_drops_null_trade_date_and_ts_code_rows():
    pro = UniversePro(
        [
            {"trade_date": "20240101", "universe": "demo", "ts_code": None},
            {"trade_date": None, "universe": "demo", "ts_code": "000002.SZ"},
            {"trade_date": "20240102", "universe": "demo", "ts_code": "000001.SZ"},
        ]
    )

    result = load_universe_panel(
        pro,
        universe_name="demo",
        start_date="20240101",
        end_date="20240102",
    )

    assert result.index.tolist() == [pd.Timestamp("2024-01-02")]
    assert result.columns.tolist() == ["000001.SZ"]
    assert result.loc[pd.Timestamp("2024-01-02"), "000001.SZ"]


def test_load_universe_panel_returns_empty_bool_frame_when_all_rows_drop():
    pro = UniversePro(
        [
            {"trade_date": "20240101", "universe": "demo", "ts_code": None},
            {"trade_date": None, "universe": "demo", "ts_code": "000002.SZ"},
        ]
    )

    result = load_universe_panel(
        pro,
        universe_name="demo",
        start_date="20240101",
        end_date="20240102",
    )

    assert result.empty
    assert result.dtypes.tolist() == []


def test_evaluate_factors_summary_contains_ic_freq_columns(tmp_path, monkeypatch):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)

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

    for col in ["directional_IC>0 %(W)", "directional_IC>0 %(M)", "IC_near_far_ratio"]:
        assert col in result.summary.columns, f"missing: {col}"
    assert "IC>0 %(W)" not in result.summary.columns
    assert "IC>0 %(M)" not in result.summary.columns


class ParallelFakePro:
    """Module-level so spawn workers can unpickle it."""

    def __init__(self, price_rows):
        self.price_rows = price_rows

    def pro_bar(self, ts_code=None, start_date=None, end_date=None, adj=None):
        return pd.DataFrame(self.price_rows)


def _parallel_eval_inputs(tmp_path):
    codes = [f"00000{i}.SZ" for i in range(1, 7)]
    dates = pd.bdate_range("2024-01-01", periods=30).strftime("%Y%m%d").tolist()

    price_rows = {
        "trade_date": [],
        "ts_code": [],
        "open": [],
        "close": [],
    }
    factor_x_rows = {"trade_date": [], "ts_code": [], "value": []}
    factor_y_rows = {"trade_date": [], "ts_code": [], "value": []}
    for day_index, date in enumerate(dates):
        for code_index, code in enumerate(codes):
            price = 10.0 + code_index + 0.1 * day_index + 0.05 * ((day_index + code_index) % 3)
            price_rows["trade_date"].append(date)
            price_rows["ts_code"].append(code)
            price_rows["open"].append(price)
            price_rows["close"].append(price + 0.2)
            factor_x_rows["trade_date"].append(date)
            factor_x_rows["ts_code"].append(code)
            factor_x_rows["value"].append(float(code_index + day_index % 5))
            factor_y_rows["trade_date"].append(date)
            factor_y_rows["ts_code"].append(code)
            factor_y_rows["value"].append(float(-code_index + day_index % 7))

    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write("factor_x", pd.DataFrame(factor_x_rows))
    storage.write("factor_y", pd.DataFrame(factor_y_rows))
    return storage, ParallelFakePro(price_rows), dates


def test_evaluate_factors_parallel_matches_serial(tmp_path):
    storage, pro, dates = _parallel_eval_inputs(tmp_path)
    config = make_config(
        tmp_path,
        factor_names=("factor_x", "factor_y"),
        end_date=dates[-1],
    )

    serial = evaluate_factors(
        factor_names=("factor_x", "factor_y"),
        storage=storage, pro=pro, config=config, run_id="serial",
    )
    parallel = evaluate_factors(
        factor_names=("factor_x", "factor_y"),
        storage=storage, pro=pro, config=config, run_id="parallel",
        workers=2,
    )

    pd.testing.assert_frame_equal(
        parallel.summary.reset_index(drop=True),
        serial.summary.reset_index(drop=True),
    )
    artifacts = ("clean_factor_data.parquet", "daily_ic.parquet", "quantile_returns.parquet")
    for factor_name in ("factor_x", "factor_y"):
        serial_dir = serial.output_dir / "factors" / factor_name
        parallel_dir = parallel.output_dir / "factors" / factor_name
        for artifact in artifacts:
            pd.testing.assert_frame_equal(
                pd.read_parquet(parallel_dir / artifact),
                pd.read_parquet(serial_dir / artifact),
            )
        assert (parallel_dir / "figures" / "quantile_returns_1D.png").exists()


def test_evaluate_factors_rejects_bad_workers(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    write_factor_a(storage)

    with pytest.raises(ValueError, match="workers must be >= 1"):
        evaluate_factors(
            factor_names=("factor_a",),
            storage=storage, pro=FakePro(), config=make_config(tmp_path),
            workers=0,
        )
