import pandas as pd

from zer0factor.exposures import build_sw_l1_industry_panel


class FakeIndustryPro:
    def index_member_all(self, fields=None):
        assert fields == "l1_code,l1_name,ts_code,in_date,out_date,is_new"
        return pd.DataFrame(
            {
                "l1_code": ["801010.SI", "801020.SI", "801030.SI", "801040.SI"],
                "l1_name": ["agri", "bank", "tech", "newtech"],
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "000003.SZ"],
                "in_date": ["2020-01-01", "2020-01-01", "2020-01-01", "2024-01-02"],
                "out_date": [None, "2024-01-01", None, None],
                "is_new": ["Y", "N", "N", "Y"],
            }
        )


def test_build_sw_l1_industry_panel_applies_membership_dates_and_latest_overlap():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    ts_codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"]

    result = build_sw_l1_industry_panel(
        FakeIndustryPro(),
        dates=dates,
        ts_codes=ts_codes,
    )

    assert list(result.index) == list(dates)
    assert list(result.columns) == ts_codes
    assert result.loc[pd.Timestamp("2024-01-01"), "000001.SZ"] == "801010.SI"
    assert result.loc[pd.Timestamp("2024-01-01"), "000002.SZ"] == "801020.SI"
    assert pd.isna(result.loc[pd.Timestamp("2024-01-02"), "000002.SZ"])
    assert result.loc[pd.Timestamp("2024-01-01"), "000003.SZ"] == "801030.SI"
    assert result.loc[pd.Timestamp("2024-01-02"), "000003.SZ"] == "801040.SI"
    assert pd.isna(result.loc[pd.Timestamp("2024-01-03"), "000004.SZ"])
