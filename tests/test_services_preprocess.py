import pandas as pd
import pytest

from zer0factor.panel import read_universe_panel
from zer0factor.services.preprocess import FactorPreprocessService
from zer0factor.storage import FactorStorage


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


def test_standardize_writes_z_factor(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "daily_return",
        pd.DataFrame(
            {
                "trade_date": ["20240101"] * 4,
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
                "value": [1.0, 2.0, None, 100.0],
            }
        ),
    )
    service = FactorPreprocessService(storage)

    rows = service.standardize(
        "daily_return",
        start_date="20240101",
        end_date="20240101",
    )

    result = storage.read("z_daily_return")
    assert rows == 4
    assert len(result) == 4
    assert list(result.columns) == ["trade_date", "ts_code", "value"]
    assert result["trade_date"].astype(str).unique().tolist() == ["20240101"]
    assert "z_daily_return" in storage.list_factors()

    values = result.sort_values("ts_code")["value"]
    assert values.isna().sum() == 0
    assert values.mean() == pytest.approx(0.0)
    assert values.std() == pytest.approx(1.0)


def test_standardize_filters_by_process_universe(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    storage.write(
        "daily_return",
        pd.DataFrame(
            {
                "trade_date": ["20240101"] * 4,
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
                "value": [1.0, 2.0, 3.0, 100.0],
            }
        ),
    )
    service = FactorPreprocessService(storage)

    rows = service.standardize(
        "daily_return",
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


def test_neutralize_requires_industry_source(tmp_path):
    storage = FactorStorage(tmp_path / "factors", tmp_path / "factor.duckdb")
    service = FactorPreprocessService(storage)

    with pytest.raises(ValueError, match="industry_source"):
        service.neutralize("demo_factor")


def test_neutralize_reads_z_factor_and_writes_standardized_neutral_factor(tmp_path):
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
    service = FactorPreprocessService(
        storage, industry_source=FakeIndustryNeutralizationPro()
    )

    rows = service.neutralize(
        "demo_factor",
        output_name="z_neu_demo_factor",
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


def test_neutralize_filters_by_process_universe(tmp_path):
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
    service = FactorPreprocessService(
        storage, industry_source=FakeIndustryNeutralizationPro()
    )

    rows = service.neutralize(
        "demo_factor",
        output_name="z_neu_demo_factor",
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
