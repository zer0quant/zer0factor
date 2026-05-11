import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1] / "docs" / "skills" / "factor-research"


def test_init_factor_research_workspace_creates_expected_files(tmp_path):
    work_dir = tmp_path / "research_round"

    subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "init_factor_research_workspace.py"),
            str(work_dir),
            "--target-factor-count",
            "3",
            "--selection-mode",
            "top_representative",
        ],
        check=True,
    )

    assert (work_dir / "inputs" / "reports").is_dir()
    assert (work_dir / "code").is_dir()
    assert json.loads((work_dir / "factors.json").read_text()) == []

    status = json.loads((work_dir / "status.json").read_text())
    assert status["step"] == "initialized"
    assert status["config"]["target_factor_count"] == 3
    assert status["config"]["selection_mode"] == "top_representative"


def test_validate_factors_json_accepts_standard_factor(tmp_path):
    factors_path = tmp_path / "factors.json"
    factors_path.write_text(
        json.dumps(
            [
                {
                    "name": "Volume_Adjusted_Momentum_20D",
                    "description": "20-day momentum adjusted by volume expansion.",
                    "spec": {
                        "name": "volume_adjusted_momentum_20d",
                        "inputs": ["close", "volume"],
                        "min_window": 20,
                        "recommended_window": 60,
                        "frequency": "1d",
                        "adjust": "hfq",
                        "output_schema": ["trade_date", "ts_code", "value"],
                    },
                    "implementation_plan": [
                        "Compute 20-day close return.",
                        "Compute volume expansion.",
                    ],
                    "keep": True,
                    "relevant": True,
                    "viable": True,
                }
            ]
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "validate_factors_json.py"),
            str(factors_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "1 factor(s) valid" in result.stdout


def test_validate_factors_json_rejects_non_standard_inputs(tmp_path):
    factors_path = tmp_path / "factors.json"
    factors_path.write_text(
        json.dumps(
            [
                {
                    "name": "BadFactor",
                    "spec": {
                        "name": "bad_factor",
                        "inputs": ["close", "st_status"],
                        "min_window": 5,
                        "recommended_window": 5,
                        "frequency": "1d",
                        "adjust": "hfq",
                        "output_schema": ["trade_date", "ts_code", "value"],
                    },
                }
            ]
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "validate_factors_json.py"),
            str(factors_path),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "unknown input" in result.stderr
