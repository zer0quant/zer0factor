#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STANDARD_FIELDS = {"open", "high", "low", "close", "volume", "amount", "return_"}
OUTPUT_SCHEMA = ["trade_date", "ts_code", "value"]
ADJUSTMENTS = {"hfq", "qfq", "none", None}
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*[a-z0-9]$")


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def validate_factor(index: int, factor: dict) -> None:
    name = factor.get("name", f"<index {index}>")
    spec = factor.get("spec")
    if not isinstance(spec, dict):
        fail(f"{name}: missing spec object")

    spec_name = spec.get("name")
    if not isinstance(spec_name, str) or not SNAKE_CASE.match(spec_name):
        fail(f"{name}: spec.name must be snake_case")

    inputs = spec.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        fail(f"{name}: spec.inputs must be a non-empty list")
    unknown = sorted(set(inputs) - STANDARD_FIELDS)
    if unknown:
        fail(f"{name}: unknown input field(s): {unknown}")

    min_window = spec.get("min_window")
    recommended_window = spec.get("recommended_window", min_window)
    if not isinstance(min_window, int) or min_window < 1:
        fail(f"{name}: spec.min_window must be an integer >= 1")
    if not isinstance(recommended_window, int) or recommended_window < min_window:
        fail(f"{name}: spec.recommended_window must be >= min_window")

    if spec.get("frequency", "1d") != "1d":
        fail(f"{name}: only daily frequency '1d' is supported")
    if spec.get("adjust", "hfq") not in ADJUSTMENTS:
        fail(f"{name}: spec.adjust must be hfq, qfq, none, or null")
    if spec.get("output_schema", OUTPUT_SCHEMA) != OUTPUT_SCHEMA:
        fail(f"{name}: spec.output_schema must be {OUTPUT_SCHEMA}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate zer0factor factors.json contracts.")
    parser.add_argument("factors_json", type=Path)
    args = parser.parse_args()

    try:
        factors = json.loads(args.factors_json.read_text())
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    if not isinstance(factors, list):
        fail("factors.json must be a JSON array")

    for index, factor in enumerate(factors):
        if not isinstance(factor, dict):
            fail(f"factor at index {index} must be an object")
        validate_factor(index, factor)

    print(f"{len(factors)} factor(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

