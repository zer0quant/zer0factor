from __future__ import annotations

import pytest

from zer0factor.config import BoardSetting
from zer0factor.web.bases import base_versions, parse_factor_name, summarize_bases

BOARD = BoardSetting()
P = "z_size_industry_neu_"


def row(name, icir=None, direction=None, evaluated=None):
    if evaluated is None:
        evaluated = icir is not None
    return {
        "name": name,
        "evaluated": evaluated,
        "icir": icir,
        "direction": direction,
        "run_id": "r1" if evaluated else None,
    }


def one(rows, base):
    return next(b for b in summarize_bases(rows, BOARD) if b["base"] == base)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("z_size_industry_neu_daily_return_ma5", ("z_size_industry_neu", "daily_return", 5)),
        ("z_neu_daily_return", ("z_neu", "daily_return", None)),
        ("rank_industry_neu_x_ma10", ("rank_industry_neu", "x", 10)),
        ("daily_return", ("raw", "daily_return", None)),
        ("foo_ma", ("raw", "foo_ma", None)),
        ("z_", ("raw", "z_", None)),
        ("intraday_rtn_var_up_ma40", ("raw", "intraday_rtn_var_up", 40)),
        ("z_daily_return_ma20", ("z", "daily_return", 20)),
    ],
)
def test_parse_matches_frontend_rules(name, expected):
    p = parse_factor_name(name)
    assert (p.prep, p.base, p.window) == expected
    assert p.name == name


def test_ok_median_and_direction():
    rows = [
        row(f"{P}daily_return_ma5", 0.2, -1),
        row(f"{P}daily_return_ma10", 0.9, -1),
        row(f"{P}daily_return_ma20", 0.4, -1),
    ]
    b = one(rows, "daily_return")
    assert b["status"] == "ok"
    assert b["direction"] == -1
    assert b["icir_median"] == pytest.approx(0.4)
    assert b["primary_prep"] == "z_size_industry_neu"
    assert [w["window"] for w in b["windows"]] == [5, 10, 20]


def test_even_count_median_is_mean_of_middle():
    rows = [row(f"{P}a_ma5", 0.2, 1), row(f"{P}a_ma10", 0.4, 1)]
    assert one(rows, "a")["icir_median"] == pytest.approx(0.3)


def test_mixed_direction():
    rows = [row(f"{P}a_ma5", 0.2, 1), row(f"{P}a_ma10", 0.4, -1)]
    b = one(rows, "a")
    assert b["status"] == "mixed"
    assert b["icir_median"] is None
    assert b["direction"] is None


def test_unevaluated_and_missing():
    unevaluated = one([row(f"{P}a_ma5"), row(f"{P}a_ma10")], "a")
    assert unevaluated["status"] == "unevaluated"
    assert unevaluated["icir_median"] is None
    missing = one([row("a_ma5"), row("z_a_ma5", 0.5, 1)], "a")
    assert missing["status"] == "missing"
    assert missing["icir_median"] is None
    assert missing["windows"] == []


def test_other_preps_never_substitute():
    b = one([row(f"{P}a_ma5"), row("z_a_ma5", 0.5, 1)], "a")
    assert b["status"] == "unevaluated"
    assert b["icir_median"] is None
    assert b["direction"] is None


def test_industry_only_base_uses_industry_prep():
    rows = [row("z_industry_neu_log_total_market_cap", 0.3, -1), row("log_total_market_cap")]
    b = one(rows, "log_total_market_cap")
    assert b["primary_prep"] == "z_industry_neu"
    assert b["status"] == "ok"


def test_single_unwindowed_version():
    b = one([row("z_industry_neu_log_total_market_cap", 0.3, -1)], "log_total_market_cap")
    assert [w["window"] for w in b["windows"]] == [None]
    assert b["icir_median"] == pytest.approx(0.3)


def test_evaluated_without_icir_is_ignored():
    rows = [row(f"{P}a_ma5", None, None, evaluated=True), row(f"{P}a_ma10", 0.5, 1)]
    b = one(rows, "a")
    assert (b["status"], b["icir_median"], b["direction"]) == ("ok", 0.5, 1)
    only = one([row(f"{P}a_ma5", None, None, evaluated=True)], "a")
    assert only["status"] == "unevaluated"


def test_windows_sorted_with_unwindowed_first():
    rows = [row(f"{P}a_ma20", 0.1, 1), row(f"{P}a", 0.1, 1), row(f"{P}a_ma5", 0.1, 1)]
    assert [w["window"] for w in one(rows, "a")["windows"]] == [None, 5, 20]


def test_preps_counts():
    rows = [
        row(f"{P}a_ma5", 0.1, 1),
        row(f"{P}a_ma10"),
        row("a_ma5"),
        row("z_a_ma5", 0.2, 1),
        row("z_a_ma10", 0.2, 1),
    ]
    assert one(rows, "a")["preps"] == [
        {"prep": "raw", "n_versions": 1, "n_evaluated": 0},
        {"prep": "z", "n_versions": 2, "n_evaluated": 2},
        {"prep": "z_size_industry_neu", "n_versions": 2, "n_evaluated": 1},
    ]


def test_bases_sorted_by_name():
    rows = [row("b_ma5"), row("a_ma5")]
    assert [b["base"] for b in summarize_bases(rows, BOARD)] == ["a", "b"]


def test_base_versions_default_prep():
    rows = [row(f"{P}a_ma5"), row("z_a_ma5", 0.5, 1), row("b"), row("z_b_ma10"), row("z_b_ma5")]
    a = base_versions(rows, "a", BOARD)
    assert a["primary_prep"] == a["default_prep"] == "z_size_industry_neu"
    assert [v["prep"] for v in a["versions"]] == ["z", "z_size_industry_neu"]
    b = base_versions(rows, "b", BOARD)
    assert b["default_prep"] == "z"
    assert [(v["prep"], v["window"]) for v in b["versions"]] == [
        ("raw", None),
        ("z", 5),
        ("z", 10),
    ]
    assert set(b["versions"][0]) == {"name", "prep", "window", "evaluated", "icir", "direction", "run_id"}
    assert base_versions(rows, "nope", BOARD) is None


def test_custom_board_setting():
    board = BoardSetting(primary_prep="z", industry_only_bases=())
    b = next(x for x in summarize_bases([row("z_a_ma5", 0.5, 1)], board) if x["base"] == "a")
    assert (b["primary_prep"], b["status"]) == ("z", "ok")


def test_default_prep_fallback_prefers_spec_order_over_legacy_and_rank():
    rows = [row("z_industry_neu_c_ma5"), row("z_neu_c_ma5"), row("rank_c_ma5")]
    assert base_versions(rows, "c", BOARD)["default_prep"] == "z_industry_neu"
    only_legacy = [row("z_neu_d"), row("rank_size_neu_d")]
    # Neither spec prep exists: fall back along the full order (Rank after legacy z_neu).
    assert base_versions(only_legacy, "d", BOARD)["default_prep"] == "rank_size_neu"


def test_metrics_are_medians_over_primary_windows():
    rows = [
        {**row(f"{P}a_ma5", 0.2, -1), "ic_adj": 0.01, "long_ann_ret": 0.10, "start_date": "20160104", "end_date": "20260101"},
        {**row(f"{P}a_ma10", 0.4, -1), "ic_adj": 0.03, "long_ann_ret": None, "start_date": "20160105", "end_date": "20260102"},
        {**row(f"{P}a_ma20", 0.6, -1), "ic_adj": 0.02, "long_ann_ret": 0.30, "start_date": "20160106", "end_date": "20260102"},
        {**row("z_a_ma5", 9.9, -1), "ic_adj": 9.9, "long_ann_ret": 9.9},
    ]
    b = one(rows, "a")
    assert b["metrics"]["icir"] == pytest.approx(0.4)
    assert b["metrics"]["ic_adj"] == pytest.approx(0.02)
    assert b["metrics"]["long_ann_ret"] == pytest.approx(0.20)  # None skipped
    assert b["metrics"]["t_stat"] is None  # absent everywhere
    assert set(b["metrics"]) == {
        "ic_adj", "icir", "t_stat", "ic_win_rate",
        "long_ann_ret", "long_max_dd", "long_sharpe", "long_exc_ann_ret", "monotonicity",
        "turnover_long",
    }
    assert (b["start_date"], b["end_date"], b["run_ids"]) == ("20160104", "20260102", ["r1"])


def test_metrics_empty_without_number():
    for rows in ([row(f"{P}a_ma5")], [row(f"{P}a_ma5", 0.2, 1), row(f"{P}a_ma10", 0.2, -1)]):
        b = one(rows, "a")
        assert all(v is None for v in b["metrics"].values())
        assert (b["start_date"], b["end_date"], b["run_ids"]) == (None, None, [])
