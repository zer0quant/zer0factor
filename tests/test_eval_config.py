from pathlib import Path

import pytest

from zer0factor.eval import EvaluationConfig


def test_evaluation_config_defaults_to_open_t1_and_evaluations_dir():
    config = EvaluationConfig(
        factor_names=("z_neu_daily_return",),
        start_date="20240101",
        end_date="20240131",
    )

    assert config.factor_names == ("z_neu_daily_return",)
    assert config.periods == (1, 5, 10)
    assert config.quantiles == 10
    assert config.return_type == "open_t1"
    assert config.max_loss == 0.35
    assert config.universe is None
    assert config.output_dir == Path("data/evaluations")
    assert config.rolling_ic_window == 63
    assert config.transaction_cost_bps == 10.0


def test_evaluation_config_normalizes_periods_and_output_dir():
    config = EvaluationConfig(
        factor_names=["factor_a", "factor_b"],
        start_date="20240101",
        end_date=None,
        periods=[1, 3],
        output_dir="tmp/evals",
    )

    assert config.factor_names == ("factor_a", "factor_b")
    assert config.periods == (1, 3)
    assert config.output_dir == Path("tmp/evals")


@pytest.mark.parametrize("return_type", ["bad", "open", "close"])
def test_evaluation_config_rejects_unknown_return_type(return_type):
    with pytest.raises(ValueError, match="return_type must be one of"):
        EvaluationConfig(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240131",
            return_type=return_type,
        )


def test_evaluation_config_rejects_empty_factor_names():
    with pytest.raises(ValueError, match="factor_names must not be empty"):
        EvaluationConfig(
            factor_names=(),
            start_date="20240101",
            end_date="20240131",
        )


@pytest.mark.parametrize("factor_names", ["abc", b"abc"])
def test_evaluation_config_rejects_scalar_string_factor_names(factor_names):
    with pytest.raises(ValueError, match="factor_names must be a sequence of names"):
        EvaluationConfig(
            factor_names=factor_names,
            start_date="20240101",
            end_date="20240131",
        )


def test_evaluation_config_rejects_non_positive_periods():
    with pytest.raises(ValueError, match="periods must be positive integers"):
        EvaluationConfig(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240131",
            periods=(1, 0),
        )


def test_evaluation_config_rejects_fractional_periods():
    with pytest.raises(ValueError, match="periods must be positive integers"):
        EvaluationConfig(
            factor_names=("factor_a",),
            start_date="20240101",
            end_date="20240131",
            periods=(1.9,),
        )


def test_evaluation_config_accepts_benchmark_index():
    from zer0factor.eval.config import EvaluationConfig
    config = EvaluationConfig(
        factor_names=("f",),
        start_date="20240101",
        end_date="20240131",
        benchmark_index="000300.SH",
    )
    assert config.benchmark_index == "000300.SH"


def test_evaluation_config_benchmark_index_defaults_to_none():
    from zer0factor.eval.config import EvaluationConfig
    config = EvaluationConfig(
        factor_names=("f",),
        start_date="20240101",
        end_date="20240131",
    )
    assert config.benchmark_index is None


def test_evaluation_config_rejects_negative_transaction_cost():
    with pytest.raises(ValueError, match="transaction_cost_bps must be >= 0"):
        EvaluationConfig(
            factor_names=("f",),
            start_date="20240101",
            end_date="20240131",
            transaction_cost_bps=-1.0,
        )
