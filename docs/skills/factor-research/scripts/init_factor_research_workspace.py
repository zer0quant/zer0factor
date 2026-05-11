#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def write_json_if_missing(path: Path, value) -> None:
    if not path.exists():
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a factor research work directory.")
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--target-factor-count", type=int, default=None)
    parser.add_argument(
        "--selection-mode",
        choices=["all", "top_representative", "formula_only", "backtested_only", "user_named"],
        default="all",
    )
    parser.add_argument("--max-extract-rounds", type=int, default=3)
    parser.add_argument("--max-code-attempts", type=int, default=3)
    args = parser.parse_args()

    work_dir = args.work_dir
    for relative in [
        "inputs/reports",
        "code",
        "specs",
        "results",
        "feedback",
    ]:
        (work_dir / relative).mkdir(parents=True, exist_ok=True)

    write_json_if_missing(work_dir / "factors.json", [])
    write_json_if_missing(work_dir / "approved.json", [])
    write_json_if_missing(
        work_dir / "status.json",
        {
            "step": "initialized",
            "config": {
                "target_factor_count": args.target_factor_count,
                "selection_mode": args.selection_mode,
                "max_extract_rounds": args.max_extract_rounds,
                "max_code_attempts": args.max_code_attempts,
            },
            "factors": {},
        },
    )
    (work_dir / "prompt_trace.jsonl").touch(exist_ok=True)
    print(f"initialized factor research workspace: {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

