# zer0factor

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Status](https://img.shields.io/badge/status-early--stage-orange)
![License](https://img.shields.io/badge/license-MIT-green)

[简体中文](README.md) | English

AI-assisted factor research workbench for local A-share data. `zer0factor` turns research reports and factor ideas into reviewable, executable, persisted factor code:

```text
report / idea -> FactorSpec -> Python compute() -> Parquet factor values
```

It is built to work with [zer0share](https://github.com/zer0quant/zer0share):

- `zer0share`: local A-share data collection, sync, and query
- `zer0factor`: factor specification, generation, preprocessing, evaluation, and storage

> The project is still early. Treat it as a research workbench, not a production factor platform.

## Features

- Standard factor contract: `FactorSpec + FactorFrame + compute()` with a unified `trade_date, ts_code, value` output
- `zer0share` provider that maps local market data into wide factor panels
- Parquet factor storage with a DuckDB registry
- Factor registry: `config/factors.toml` tracks candidate factors, tags, and default evaluation parameters
- Preprocessing: cross-sectional winsorization, standardization, and industry / market-cap neutralization
- Factor evaluation: IC, quantile returns, turnover, monotonicity, and portfolio metrics via Alphalens / Pyfolio
- `factor-research` skill for report-to-factor workflows, with one completed momentum-report example

## Install

Prerequisites:

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Local A-share data synced with `zer0share`

By default, `zer0factor` expects `zer0share` next to this repo:

```text
work/
├── zer0factor/
└── zer0share/
```

If your `zer0share` checkout lives elsewhere, change the path in `pyproject.toml` first:

```toml
[tool.uv.sources]
zer0share = { path = "../zer0share" }
```

Then:

```bash
git clone https://github.com/zer0quant/zer0factor.git
cd zer0factor
uv sync
```

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

A minimal compute-to-evaluate loop, using the built-in market-cap factor:

```bash
# Check factor storage status
uv run python main.py --config config/settings.toml status

# Compute the built-in market-cap factors and write them to local storage
uv run python main.py compute-market-cap

# Evaluate a stored factor and inspect the results
uv run python main.py evaluate-factor log_total_market_cap
uv run python main.py show-summary
```

Evaluation artifacts are written to `data/evaluations/<run_id>/`. See [docs/evaluation.md](docs/evaluation.md) for metric definitions (Chinese).

## CLI

| Command | Description |
|---|---|
| `status` | List computed factors in the configured storage |
| `factor-list` | Compare registry entries against local storage |
| `factor-info <name>` | Show registry and storage status for one factor |
| `compute-returns` | Compute built-in return factors and write them to local storage |
| `compute-market-cap` | Compute built-in market-cap factors and write them to local storage |
| `build-factors --family <name>` | Build a registered factor family |
| `standardize-factor <name>` | Winsorize, impute, and standardize a stored factor cross-sectionally |
| `neutralize-factor <name>` | Neutralize a standardized factor by industry / market cap |
| `evaluate-factor <name>` | Evaluate a single stored factor |
| `evaluate-factors <name...>` | Evaluate multiple stored factors |
| `evaluate-batch --file <file>` | Batch-evaluate factors from a config file |
| `evaluate-summary` | Summarize an evaluation run |
| `analyze-evaluation` | Analyze an evaluation summary and write grouped diagnostics |
| `show-summary` | Show the full summary of the latest evaluation run |

Run every command as `uv run python main.py <command>`; add `--help` for full options.

## Factor Contract

```python
import pandas as pd

from zer0factor.core import Factor, FactorFrame, FactorSpec, to_factor_output


class Ret20_0(Factor):
    spec = FactorSpec(
        name="ret20_0",
        inputs=["close"],
        min_window=20,
        frequency="1d",
        adjust="hfq",
    )

    def compute(self, data: FactorFrame) -> pd.DataFrame:
        value = data.close / data.close.shift(20) - 1
        return to_factor_output(value, self.spec.name)
```

Factor code should only read data from `FactorFrame`. It should not read files, query DuckDB, or call `zer0share` directly. See [docs/factor-contract.md](docs/factor-contract.md) for field mappings and storage layout (Chinese).

## Layout

```text
zer0factor/
├── main.py                # CLI entry point
├── zer0factor/
│   ├── core/              # FactorSpec / FactorFrame / Factor contract
│   ├── factors/           # built-in factors (returns, market cap, ...)
│   ├── cli/               # CLI command implementations
│   ├── preprocess/        # winsorization, standardization, neutralization
│   ├── eval/              # factor evaluation, summary, and report
│   ├── registry.py        # factor registry
│   └── storage.py         # Parquet + DuckDB factor storage
├── config/                # settings.example.toml, factors.toml
├── docs/skills/factor-research/   # report-to-factor skill
├── workspaces/            # research run artifacts
├── notebooks/
└── tests/
```

## Documentation

- [Factor contract](docs/factor-contract.md): standard fields, output schema, and storage layout (Chinese)
- [Factor evaluation](docs/evaluation.md): registry, evaluation commands, artifacts, and metric definitions (Chinese)
- [factor-research skill](docs/skills/factor-research/): the full report-to-factor workflow
- [Devlog](docs/devlog.md): index of articles documenting the design process (Chinese)
- Example: `workspaces/factor-research-guosen-momentum/` contains one completed momentum-report run

## Limitations

- Built around local A-share data and `zer0share`.
- `FactorFrame` does not yet expose ST flags, suspension flags, listed-days masks, or exact limit-up metadata.
- Announcement-date factors and benchmark-relative factors need additional provider contracts.
- APIs are experimental.

## Community

The design process and lessons learned are documented (in Chinese) on Zhihu and the WeChat official account 极客投研笔记. See the [devlog](docs/devlog.md) for the full article index.

## Contributing

Contributions are welcome, especially around provider contracts, factor execution CLI, tests, and documentation.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

This project is for research and engineering experiments only. It does not provide investment advice. Any factor, example, or generated result should be independently verified before use.

## License

MIT. See [LICENSE](LICENSE).
