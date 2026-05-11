# zer0factor

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Status](https://img.shields.io/badge/status-early--stage-orange)
![License](https://img.shields.io/badge/license-MIT-green)

AI-assisted factor research workspace for local A-share data.

`zer0factor` turns research ideas and quant reports into reviewable, executable factor code:

```text
report / idea -> FactorSpec -> Python compute() -> Parquet factor values
```

It is built to work with [zer0share](https://github.com/zer0quant/zer0share):

- `zer0share`: local A-share data collection and query layer
- `zer0factor`: factor specification, generation, computation, and storage layer

The project is still early. Treat it as a research workbench, not a production factor platform.

## Features

- Standard factor contract: `FactorSpec + FactorFrame + compute()`
- `zer0share` provider that maps local market data into wide factor panels
- Factor output schema: `trade_date, ts_code, value`
- Parquet factor storage with a DuckDB registry
- `factor-research` Codex skill for report-to-factor workflows
- Example momentum-report run with generated factor modules

## Layout

```text
zer0factor/
├── zer0factor/
│   ├── config.py              # config loader
│   ├── storage.py             # Parquet + DuckDB factor storage
│   └── factor/__init__.py     # factor contract and zer0share provider
├── docs/skills/factor-research/
├── workspaces/                # research run artifacts
├── notebooks/
├── tests/
└── config/settings.example.toml
```

## Install

```bash
git clone <your-repo-url>
cd zer0factor
uv sync
```

By default, `zer0factor` expects `zer0share` next to this repo:

```text
work/
├── zer0factor/
└── zer0share/
```

This is configured in `pyproject.toml`:

```toml
[tool.uv.sources]
zer0share = { path = "../zer0share" }
```

Change the path if your local `zer0share` checkout lives elsewhere.

## Configure

```bash
cp config/settings.example.toml config/settings.toml
```

```toml
[zer0share]
data_dir = "../zer0share/data"

[paths]
factor_dir = "data/factors"
db_path    = "db/factor_meta.duckdb"
log_path   = "logs/factor.log"

[factor]
universe   = "all"
start_date = "20160101"
end_date   = ""
```

## Quick Start

Run the focused test suite:

```bash
uv run pytest tests/test_config.py tests/test_storage.py tests/test_factor_standard.py tests/test_factor_research_skill_scripts.py
```

Check factor storage status:

```bash
uv run python main.py --config config/settings.toml status
```

Lint the core runtime and skill files:

```bash
uv run ruff check zer0factor/factor/__init__.py docs/skills/factor-research tests/test_factor_standard.py tests/test_factor_research_skill_scripts.py
```

## CLI

| Command | Description |
|---|---|
| `uv run python main.py status` | List computed factors in the configured storage |

More factor execution commands will be added as the runtime matures.

## Factor Contract

```python
import pandas as pd

from zer0factor.factor import Factor, FactorFrame, FactorSpec, to_factor_output


class Ret20_0(Factor):
    spec = FactorSpec(
        name="ret20_0",
        inputs=["close"],
        min_window=20,
        recommended_window=60,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.close / data.close.shift(20) - 1
        return to_factor_output(value, self.spec.name)
```

Factor code should only read data from `FactorFrame`. It should not read files, query DuckDB, or
call `zer0share` directly.

## Standard Fields

| zer0factor field | zer0share source | Notes |
|---|---|---|
| `open` | `open` | adjusted by provider |
| `high` | `high` | adjusted by provider |
| `low` | `low` | adjusted by provider |
| `close` | `close` | adjusted by provider |
| `volume` | `vol` | renamed for factor code |
| `amount` | `amount` | turnover amount |
| `return_` | `pct_chg` or computed return | reserved word-safe name |

Default adjustment is `hfq`.

## Storage

Factor values are written as date-partitioned Parquet:

```text
data/factors/
└── ret20_0/
    ├── date=20240102/data.parquet
    └── date=20240103/data.parquet

db/
└── factor_meta.duckdb
```

Each factor dataframe must contain:

```text
trade_date, ts_code, value
```

## factor-research Skill

The Codex skill lives in:

```text
docs/skills/factor-research/
```

Workflow:

```text
PDF report / research idea
  -> candidate factors
  -> human review
  -> FactorSpec
  -> quality gates
  -> Python factor code
  -> execution check
  -> archive
```

Initialize a research workspace:

```bash
python docs/skills/factor-research/scripts/init_factor_research_workspace.py \
  workspaces/my-factor-run \
  --target-factor-count 5 \
  --selection-mode top_representative
```

Validate factor metadata:

```bash
python docs/skills/factor-research/scripts/validate_factors_json.py \
  workspaces/my-factor-run/factors.json
```

## Example Run

`workspaces/factor-research-guosen-momentum/` contains one completed momentum-report run:

- `factors.json`
- `approved.json`
- `code/*.py`
- `results/execution_feedback.json`
- `results/factor_library.json`
- `feedback/round_feedback.md`

Generated factors:

- `ret20_0`
- `ret240_20_remove_up_limit`
- `rank_mom120_20`
- `smooth240_1`
- `overnight_mom20`

## Limitations

- Built around local A-share data and `zer0share`.
- `FactorFrame` does not yet expose ST flags, suspension flags, listed-days masks, or exact limit-up metadata.
- Announcement-date factors and benchmark-relative factors need additional provider contracts.
- APIs are experimental.
- Third-party PDFs and extracted full report text are ignored and should not be committed.

## Contributing

Contributions are welcome, especially around provider contracts, factor execution CLI, tests, and
documentation.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

This project is for research and engineering experiments only. It does not provide investment
advice. Any factor, example, or generated result should be independently verified before use.

## License

MIT. See [LICENSE](LICENSE).
