# Contributing

Thanks for your interest in `zer0factor`.

This project is still early. The most useful contributions right now are:

- provider contracts for more data fields
- factor execution CLI improvements
- tests for `FactorSpec`, `FactorFrame`, and `FactorStorage`
- examples that do not include copyrighted third-party reports
- documentation improvements

## Development

```bash
uv sync
uv run pytest tests/test_config.py tests/test_storage.py tests/test_factor_standard.py tests/test_factor_research_skill_scripts.py
uv run ruff check zer0factor/factor/__init__.py docs/skills/factor-research tests/test_factor_standard.py tests/test_factor_research_skill_scripts.py
```

## Pull Requests

Please keep PRs focused. If a change touches both runtime behavior and research artifacts, split it
when practical.

Do not commit local data, generated databases, logs, third-party PDFs, API keys, or private research
notes.

## Research Disclaimer

Factors and examples in this repository are for research and engineering experiments only. They are
not investment advice.
