import json
import math

import numpy as np
import pandas as pd

from zer0factor.web.jsonsafe import to_jsonable


def test_to_jsonable_converts_nan_and_inf_to_none():
    data = {"a": float("nan"), "b": [math.inf, -np.inf, np.float64(1.5)], "c": pd.NA}
    out = to_jsonable(data)
    assert out == {"a": None, "b": [None, None, 1.5], "c": None}
    json.dumps(out, allow_nan=False)


def test_to_jsonable_converts_numpy_and_timestamps():
    out = to_jsonable(
        {"i": np.int64(3), "t": pd.Timestamp("2024-01-02"), "arr": np.array([1.0, np.nan])}
    )
    assert out == {"i": 3, "t": "2024-01-02", "arr": [1.0, None]}
    assert type(out["i"]) is int


def test_to_jsonable_nat_is_none():
    assert to_jsonable({"d": pd.NaT}) == {"d": None}
