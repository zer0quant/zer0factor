import pytest

from zer0factor.naming import FactorName


@pytest.mark.parametrize(
    "name,raw",
    [
        ("ret20", "ret20"),
        ("z_ret20", "ret20"),
        ("z_neu_ret20", "ret20"),
    ],
)
def test_parse_strips_known_prefixes(name, raw):
    assert FactorName.parse(name).raw == raw


def test_derived_names():
    name = FactorName.parse("z_ret20")
    assert name.standardized == "z_ret20"
    assert name.neutralized == "z_neu_ret20"
