# Evaluation OOP Refactor Design

## Purpose

Refactor the `zer0factor` evaluation subsystem into a cohesive object-oriented
design that represents the full evaluation business flow:

```text
factor selection -> evaluation execution -> artifacts -> ranked report -> family analysis
```

The project is still under active development, so this refactor does not need to
preserve the current function-based public API. CLI behavior and artifact
semantics should remain recognizable, but internal APIs can be redesigned around
clear domain objects.

## Current Problems

`zer0factor/eval/pipeline.py` has accumulated too many responsibilities:

- selecting run-level dates and output directories
- loading stored factors, prices, benchmark returns, and universe panels
- converting data into Alphalens inputs
- running Alphalens clean-factor logic
- computing IC, quantile returns, turnover, monotonicity, and portfolio metrics
- writing factor artifacts and figures
- coordinating serial and process-pool execution
- notifying progress
- writing run summaries

`report.py` and `analysis.py` are more focused, but they are still outside a
single evaluation domain model. As a result, the business concept of an
"evaluation run" is split across functions, files, paths, and CSV conventions.

## Goals

- Model the complete evaluation business flow with named classes and explicit
  dependencies.
- Separate orchestration from computation, IO, reporting, and analysis.
- Make serial and parallel execution interchangeable strategies.
- Make factor selection explicit, including explicit factor lists and registry
  filters.
- Keep low-level numerical functions testable and mostly functional.
- Make the CLI a thin adapter over application-level workflow objects.
- Preserve the existing artifact layout for this refactor. Any future artifact
  layout change should be handled as a separate migration:

```text
data/evaluations/<run_id>/
  metadata.json
  summary.csv
  summary.parquet
  ranked_summary.csv
  report.md
  factors/<factor_name>/
    clean_factor_data.parquet
    daily_ic.parquet
    quantile_returns.parquet
    figures/*.png
  analysis/
    analysis_report.md
    ranked_factors.csv
    representative_factors.csv
    skipped_factors.csv
    by_<dimension>.csv
```

## Non-Goals

- Replacing Alphalens or rewriting its metric formulas.
- Building a plugin system for every metric in this pass.
- Changing factor storage format.
- Combining compute, preprocess, and evaluation into one super-pipeline.
- Preserving `evaluate_factor()` and `evaluate_factors()` as the primary public
  API. Temporary compatibility wrappers may exist during migration, but they are
  not the target design.

## Recommended Architecture

Use a three-part evaluation domain:

```text
EvaluationWorkflow
  -> EvaluationExecutor
  -> EvaluationReporter
  -> EvaluationAnalysisRunner
```

The workflow is the application-level use case. It coordinates the steps, but it
does not calculate metrics or write individual artifacts itself.

### Package Layout

Target structure:

```text
zer0factor/eval/
  domain.py
  workflow.py
  selection.py
  execution.py
  evaluator.py
  data.py
  metrics.py
  artifacts.py
  reporting.py
  analysis.py
  alphalens_adapter.py
  plots.py
  metrics/
    ic.py
    monotonicity.py
    returns.py
    turnover.py
```

Existing low-level modules such as `alphalens_adapter.py`, `plots.py`, and
`metrics/*` should remain mostly function-oriented. The OO layer composes them
instead of turning every formula into a class.

## Domain Model

### EvaluationRunConfig

Configuration for one run.

Fields:

- `factor_names: tuple[str, ...]`
- `start_date: str`
- `end_date: str | None`
- `periods: tuple[int, ...]`
- `quantiles: int`
- `return_type: Literal["open_t1", "close_t0"]`
- `max_loss: float`
- `universe: str | None`
- `benchmark_index: str | None`
- `transaction_cost_bps: float`
- `output_dir: Path`
- `rolling_ic_window: int`
- `workers: int`
- `report_thresholds: ReportThresholds`
- `analysis_family: str | None`

Validation belongs in `__post_init__`: non-empty factors, positive periods,
valid return type, valid quantile count, non-negative transaction cost, and
valid worker count.

### EvaluationRun

Represents one concrete run.

Fields:

- `run_id: str`
- `run_dir: Path`
- `config: EvaluationRunConfig`
- `started_at: datetime`
- `finished_at: datetime | None`

Responsibilities:

- expose derived paths such as `summary_csv`, `metadata_json`, and
  `factor_dir(factor_name)`
- carry run identity through executor, reporter, and analyzer
- avoid direct metric calculation and data loading

### FactorEvaluationResult

Result for one factor.

Fields:

- `factor_name: str`
- `summary: pd.DataFrame`
- `output_dir: Path`
- `clean_factor_data: pd.DataFrame | None`
- `daily_ic: pd.DataFrame | None`
- `quantile_returns: pd.DataFrame | None`
- `figure_paths: tuple[Path, ...]`

Parallel execution may return `None` for large frames in the parent process,
because complete artifacts are already written on disk by the worker.

### EvaluationWorkflowResult

Top-level result returned to CLI and programmatic callers.

Fields:

- `run: EvaluationRun`
- `factor_results: tuple[FactorEvaluationResult, ...]`
- `summary: pd.DataFrame`
- `report: EvaluationReportResult | None`
- `analysis: AnalysisRunResult | None`

## Core Classes

### EvaluationWorkflow

Application-level use case.

Constructor dependencies:

- `selector: FactorSelector`
- `run_factory: EvaluationRunFactory`
- `executor: EvaluationExecutor`
- `reporter: EvaluationReporter`
- `analysis_runner: EvaluationAnalysisRunner`
- `notifier: Notifier`
- `logger: EvaluationLogger`

Primary method:

```python
def run(self, request: EvaluationRequest) -> EvaluationWorkflowResult:
    ...
```

Responsibilities:

- resolve factor names from explicit input or registry filters
- build `EvaluationRunConfig`
- create the run directory
- notify start, progress, and completion
- execute factor evaluation
- write run summary and metadata
- generate ranked summary and Markdown report
- optionally run family analysis
- return a complete workflow result

It must not call Alphalens or compute metrics directly.

### FactorSelector

Resolves the factors to evaluate.

Inputs:

- explicit factor names
- batch config
- registry path
- enabled/category/tag filters

Responsibilities:

- return ordered factor names
- fail early when no factors match
- keep registry filtering out of the executor
- expose a single extension point for factor-level evaluation overrides from
  registry metadata

### EvaluationRunFactory

Creates concrete run objects.

Responsibilities:

- generate timestamp run IDs
- create `run_dir`
- detect accidental run ID collisions
- construct `EvaluationRun`

### EvaluationDataLoader

Encapsulates data access for evaluation.

Constructor dependencies:

- factor storage
- market data provider

Methods:

```python
load_factor(factor_name, start_date, end_date) -> pd.DataFrame
load_prices(start_date, end_date, periods, return_type) -> pd.DataFrame
load_universe(universe, start_date, end_date) -> pd.DataFrame | None
load_benchmark_returns(ts_code, start_date, end_date) -> pd.Series | None
max_factor_trade_date(factor_names, start_date) -> str
```

Responsibilities:

- keep storage/provider calls in one place
- normalize universe and benchmark data
- calculate open-ended price windows when `end_date` is not supplied

### FactorEvaluator

Evaluates one factor.

Constructor dependencies:

- `data_loader: EvaluationDataLoader`
- `metric_calculator: MetricsCalculator`
- `artifact_store: EvaluationArtifactStore`
- `figure_writer: FactorFigureWriter`
- `logger: EvaluationLogger`

Primary method:

```python
def evaluate(
    self,
    factor_name: str,
    run: EvaluationRun,
    shared_data: EvaluationSharedData | None = None,
) -> FactorEvaluationResult:
    ...
```

Responsibilities:

- load and validate stored factor data
- convert factor data to Alphalens series
- apply universe filtering
- obtain price matrix
- run clean factor calculation
- calculate per-factor metrics and summary rows
- write factor artifacts and figures

It should not know whether it is running inside serial or parallel execution.

### MetricsCalculator

Facade over metric functions.

Methods:

```python
calculate_daily_ic(clean_factor_data) -> pd.DataFrame
calculate_quantile_returns(clean_factor_data) -> pd.DataFrame
build_factor_summary(...) -> pd.DataFrame
calculate_period_sample_counts(...) -> dict[str, int]
```

Responsibilities:

- centralize metric orchestration
- keep summary column construction in one place
- call existing functions in `eval.metrics.*`

Low-level formulas remain normal functions unless a metric truly needs state.

### EvaluationArtifactStore

Owns evaluation output files.

Methods:

```python
create_run(run: EvaluationRun) -> None
write_factor_artifacts(result: FactorEvaluationResult) -> dict[str, Path]
write_run_summary(run: EvaluationRun, summary: pd.DataFrame) -> RunArtifactPaths
write_metadata(run: EvaluationRun) -> Path
```

Responsibilities:

- isolate path layout and file formats
- make artifact writes testable without running metrics
- prevent path logic from leaking into evaluator and workflow

### FactorFigureWriter

Writes per-factor figures.

Methods:

```python
write(result: FactorEvaluationResult, rolling_ic_window: int) -> tuple[Path, ...]
```

Responsibilities:

- write quantile return figures for every period
- write cumulative IC and rolling IC figures
- keep plotting out of `FactorEvaluator`

### EvaluationExecutor

Coordinates multiple factors.

Interface:

```python
class EvaluationExecutor(Protocol):
    def execute(self, run: EvaluationRun) -> tuple[FactorEvaluationResult, ...]:
        ...
```

Implementations:

- `SerialEvaluationExecutor`
- `ProcessPoolEvaluationExecutor`

Responsibilities:

- choose execution strategy based on `workers`
- preserve factor result order
- share price and universe data where appropriate
- keep process-pool details out of workflow and evaluator

### EvaluationReporter

Builds ranked output for a completed run.

Constructor dependencies:

- `ranker: SummaryRanker`
- `monotonicity_loader: QuantileMonotonicityLoader`
- `renderer: MarkdownReportRenderer`

Method:

```python
def generate(self, run: EvaluationRun, summary: pd.DataFrame) -> EvaluationReportResult:
    ...
```

Responsibilities:

- validate summary columns
- load quantile monotonicity from per-factor artifacts
- build ranked summary
- write `ranked_summary.csv`
- write `report.md`

It does not recompute clean factor data or forward returns.

### SummaryRanker

Applies pass/fail rules and ranking scores.

Responsibilities:

- infer or read factor direction
- compute `adjusted_score`
- apply threshold rules
- sort passed factors first

Thresholds are data, not hard-coded policy.

### QuantileMonotonicityLoader

Reads `quantile_returns.parquet` and calculates period-level monotonicity for
reporting.

Responsibilities:

- handle missing factor artifacts gracefully with `NaN`
- align monotonicity to `(factor_name, period)`
- avoid duplicating summary ranking logic

### MarkdownReportRenderer

Converts ranked results and figure paths into Markdown.

Responsibilities:

- render rules, top factors, passed factors, rejected factors, and figure links
- contain presentation formatting
- avoid business-rule calculations

### EvaluationAnalysisRunner

Runs optional family-specific analysis after report generation.

Constructor dependencies:

- `family_registry: FactorFamilyRegistry`

Method:

```python
def run(
    self,
    run: EvaluationRun,
    family_name: str,
    ranked_summary: pd.DataFrame | None = None,
) -> AnalysisRunResult:
    ...
```

Responsibilities:

- resolve family analysis config
- read summary or ranked summary
- write analysis outputs under `run_dir / "analysis"`
- return analyzed and skipped counts

### FamilyAnalyzer

Generic analyzer for one factor family.

Responsibilities:

- parse factor names into family dimensions
- skip unparseable factors with reasons
- compute composite score
- group by configured dimensions
- select representative factors
- render family analysis report

Existing `EvaluationAnalyzer` is already close to this shape and can be renamed
or adapted.

## Data Flow

### Complete Batch Evaluation

```text
CLI / Python request
  -> EvaluationWorkflow.run(request)
  -> FactorSelector.resolve(request)
  -> EvaluationRunFactory.create(config)
  -> EvaluationExecutor.execute(run)
       -> FactorEvaluator.evaluate(factor)
            -> EvaluationDataLoader.load_factor(...)
            -> alphalens_adapter
            -> MetricsCalculator
            -> EvaluationArtifactStore.write_factor_artifacts(...)
            -> FactorFigureWriter.write(...)
  -> EvaluationArtifactStore.write_run_summary(...)
  -> EvaluationReporter.generate(...)
       -> QuantileMonotonicityLoader
       -> SummaryRanker
       -> MarkdownReportRenderer
  -> EvaluationAnalysisRunner.run(...)  # optional
  -> EvaluationWorkflowResult
```

### Serial vs Parallel Execution

`SerialEvaluationExecutor` directly calls the injected `FactorEvaluator`.

`ProcessPoolEvaluationExecutor` creates worker-local evaluator dependencies via
a worker factory. Workers write complete factor artifacts to disk and return only
small summary frames to the parent. The parent reassembles ordered
`FactorEvaluationResult` objects.

The evaluator itself does not branch on worker count.

## CLI Design

CLI commands become adapters:

- parse options
- build `EvaluationRequest`
- call `EvaluationWorkflow`
- print output paths and previews

Commands:

- `evaluate-factor`
- `evaluate-factors`
- `evaluate-batch`
- `evaluate-summary`
- `analyze-evaluation`

`evaluate-batch` should be the primary full-flow command:

```text
load batch config
-> select factors
-> execute evaluation
-> generate report
-> optionally run family analysis
```

`evaluate-summary` and `analyze-evaluation` can remain as utility commands that
instantiate only `EvaluationReporter` or `EvaluationAnalysisRunner` for an
existing run.

## Migration Strategy

Use incremental migration with tests at every step.

1. Introduce `domain.py` with new config and result dataclasses.
2. Extract `EvaluationDataLoader` from `loaders.py` and date helper logic in
   `pipeline.py`.
3. Extract `MetricsCalculator` around current metric functions.
4. Extract `EvaluationArtifactStore` and `FactorFigureWriter`.
5. Move single-factor logic into `FactorEvaluator`.
6. Move serial multi-factor logic into `SerialEvaluationExecutor`.
7. Move process-pool logic into `ProcessPoolEvaluationExecutor`.
8. Introduce `EvaluationReporter` by splitting `report.py` into ranker,
   monotonicity loader, and renderer classes.
9. Introduce `EvaluationAnalysisRunner` and adapt existing `EvaluationAnalyzer`
   into `FamilyAnalyzer`.
10. Introduce `EvaluationWorkflow` and update CLI commands to use it.
11. Remove or demote old `evaluate_factor()` and `evaluate_factors()` function
    API after CLI and tests target the workflow.

Each step should move behavior, not rewrite formulas.

## Testing Strategy

### Unit Tests

- `EvaluationRunConfig` validation.
- `FactorSelector` explicit and registry modes.
- `EvaluationDataLoader` price-window extension, universe normalization, and
  benchmark return loading.
- `MetricsCalculator` delegates and summary column behavior.
- `EvaluationArtifactStore` writes expected paths.
- `SummaryRanker` pass/fail and score logic.
- `QuantileMonotonicityLoader` handles missing artifacts and reverse factors.
- `FamilyAnalyzer` enrichment, skipped factors, grouping, representative
  selection, and composite scoring.

### Integration Tests

- one-factor workflow writes factor artifacts, run summary, ranked summary, and
  report
- batch workflow resolves registry factors and writes full outputs
- optional family analysis writes `analysis/` outputs
- parallel executor matches serial summary and artifact contents
- CLI commands call workflow with expected request fields

### Regression Checks

Keep existing metric-specific tests around IC, returns, turnover, monotonicity,
and Alphalens adapter behavior. Those functions are the numerical core and
should not change during the OO refactor.

## Error Handling

- Empty factor selection raises `ValueError` before creating a run.
- Missing stored factor data raises a factor-scoped `ValueError`.
- Empty clean factor data raises a factor-scoped `ValueError`.
- Missing report `summary.csv` raises `FileNotFoundError`.
- Missing per-factor monotonicity artifacts produce `NaN`, not a failed report.
- Parallel worker exceptions propagate and fail the run, matching serial
  behavior.

## Design Constraints

- The workflow owns orchestration only.
- The executor owns concurrency only.
- The evaluator owns single-factor evaluation only.
- The reporter owns interpretation of completed evaluation artifacts only.
- The analyzer owns family-level comparisons only.
- Low-level numerical formulas remain simple functions unless state is required.
- Artifact paths are centralized in `EvaluationRun` and
  `EvaluationArtifactStore`.

## Success Criteria

- `pipeline.py` no longer contains the full evaluation workflow.
- There is no new god class with mixed responsibilities.
- CLI evaluation commands are thin adapters over `EvaluationWorkflow`.
- The full evaluation business flow can be tested without invoking the CLI.
- Serial and parallel execution share the same `FactorEvaluator` behavior.
- Report generation and family analysis are first-class parts of the evaluation
  domain.
