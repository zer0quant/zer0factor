import json
import sys
import textwrap
import types

import pytest
from click.testing import CliRunner

from zer0factor.discovery import describe, discover_families
from zer0factor.factor_registry import FAMILIES

FAMILY_SRC = '''
import pandas as pd
from zer0factor.families import FactorFamily

class F(FactorFamily):
    name = "{name}"
    base_factors = ("x",)
    windows = (5, 10)

    def raw_name(self, base_factor, window):
        return f"{name}_{{base_factor}}_{{window}}"

    def derive(self, panel, window):
        return panel

FAMILY = F()
'''


@pytest.fixture
def fakepkg(tmp_path, monkeypatch):
    pkg = tmp_path / "fakefam"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "good.py").write_text(
        FAMILY_SRC.format(name="good_fam") + '\nSOURCE = {"paper": "P", "formula": "x"}\n'
    )
    (pkg / "_private.py").write_text(FAMILY_SRC.format(name="private_fam"))
    (pkg / "helper.py").write_text("VALUE = 1\n")
    (pkg / "broken.py").write_text("raise ImportError('boom')\n")
    (pkg / "zdup.py").write_text(FAMILY_SRC.format(name="good_fam"))
    (pkg / "notfam.py").write_text("FAMILY = 42\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "fakefam"
    for mod in [m for m in sys.modules if m == "fakefam" or m.startswith("fakefam.")]:
        del sys.modules[mod]


def test_discover_package_families(fakepkg):
    found = {d.module: d for d in discover_families(FAMILIES, [fakepkg], [])}
    assert found["zer0factor.factors.rolling_returns"].origin == "builtin"
    good = found["fakefam.good"]
    assert good.name == "good_fam" and good.origin == "package" and good.error is None
    assert "boom" in found["fakefam.broken"].error
    assert found["fakefam.broken"].name == "broken"
    assert "duplicate" in found["fakefam.zdup"].error
    assert found["fakefam.zdup"].family is None
    assert "FactorFamily" in found["fakefam.notfam"].error
    assert "fakefam._private" not in found and "fakefam.helper" not in found
    desc = describe(good)
    assert desc["outputs"][:2] == ["good_fam_x_5", "z_good_fam_x_5"]
    assert desc["raw_names"] == ["good_fam_x_5", "good_fam_x_10"]
    assert desc["source"] == {"paper": "P", "formula": "x"}
    assert desc["windows"] == [5, 10]
    assert desc["profiles"][0] == "raw"


def test_missing_package_reported(tmp_path):
    found = discover_families({}, ["no_such_pkg_xyz"], [])
    assert len(found) == 1 and "no_such_pkg_xyz" in found[0].error


def test_family_registry_resolves_package_family(fakepkg):
    from zer0factor.factor_registry import family_registry

    cfg = types.SimpleNamespace(family_packages=(fakepkg,), external_families=())
    registry = family_registry(cfg)
    assert registry.get("good_fam").name == "good_fam"
    assert registry.get("rolling_return") is FAMILIES["rolling_return"]
    assert "good_fam" in registry.known_names()


def test_families_cli_json(fakepkg, tmp_path, monkeypatch):
    from zer0factor.cli import cli

    monkeypatch.setattr(
        "zer0factor.cli.registry_cmds.load_config",
        lambda path: types.SimpleNamespace(family_packages=(fakepkg,), external_families=()),
    )
    result = CliRunner().invoke(cli, ["--config", str(tmp_path / "s.toml"), "families", "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    names = {}
    for f in body["families"]:
        names.setdefault(f["name"], f)
    assert names["good_fam"]["error"] is None
    assert names["broken"]["error"]
