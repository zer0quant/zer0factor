"""Convert analysis results into strict-JSON-safe Python values."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping

import numpy as np
import pandas as pd


def to_jsonable(obj: object) -> object:
    if obj is None or obj is pd.NaT or isinstance(obj, (bool, str)):
        return None if obj is pd.NaT else obj
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
    if obj is pd.NA or obj is pd.NaT:
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)
