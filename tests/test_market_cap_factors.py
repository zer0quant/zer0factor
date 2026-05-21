from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from zer0factor.core import FactorFrame, run_factor
from zer0factor.factors import LogCirculatingMarketCap, LogTotalMarketCap


def _market_cap_frame() -> FactorFrame:
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    total_mv = pd.DataFrame(
        {"000001.SZ": [100.0, 0.0], "000002.SZ": [np.e**2, -1.0]},
        index=index,
    )
    circ_mv = pd.DataFrame(
        {"000001.SZ": [np.e, 50.0], "000002.SZ": [0.0, np.e**3]},
        index=index,
    )
    return FactorFrame({"total_mv": total_mv, "circ_mv": circ_mv})


def test_log_total_market_cap_computes_natural_log_and_drops_non_positive_values():
    result = run_factor(LogTotalMarketCap(), _market_cap_frame())

    assert result.to_dict("records") == [
        {
            "trade_date": "20240101",
            "ts_code": "000001.SZ",
            "value": pytest.approx(np.log(100.0)),
        },
        {
            "trade_date": "20240101",
            "ts_code": "000002.SZ",
            "value": pytest.approx(2.0),
        },
    ]


def test_log_circulating_market_cap_computes_natural_log_and_drops_non_positive_values():
    result = run_factor(LogCirculatingMarketCap(), _market_cap_frame())

    assert result.to_dict("records") == [
        {
            "trade_date": "20240101",
            "ts_code": "000001.SZ",
            "value": pytest.approx(1.0),
        },
        {
            "trade_date": "20240102",
            "ts_code": "000001.SZ",
            "value": pytest.approx(np.log(50.0)),
        },
        {
            "trade_date": "20240102",
            "ts_code": "000002.SZ",
            "value": pytest.approx(3.0),
        },
    ]
