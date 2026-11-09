export type Num = number | null;

export interface StandardSetting {
  start_date: string;
  quantiles: number;
  period: string;
  return_type: string;
  universe: string;
}

export interface RunSummary {
  run_id: string;
  start_date: string | null;
  end_date: string | null;
  universe: string | null;
  quantiles: number | null;
  periods: string[];
  return_type: string | null;
  transaction_cost_bps: Num;
  n_factors: number;
  has_summary: boolean;
  standard: boolean;
}

export interface Meta {
  standard: StandardSetting;
  scanned_at: string;
  n_factors: number;
  runs: RunSummary[];
}

export interface BoardRow {
  name: string;
  category: string | null;
  tags: string[];
  description: string;
  evaluated: boolean;
  direction: Num;
  ic_adj: Num;
  icir: Num;
  t_stat: Num;
  ic_win_rate: Num;
  ls_ann_ret: Num;
  ls_max_dd: Num;
  ls_sharpe: Num;
  long_ann_ret: Num;
  long_max_dd: Num;
  long_sharpe: Num;
  long_exc_ann_ret: Num;
  monotonicity: Num;
  turnover_long: Num;
  start_date: string | null;
  end_date: string | null;
  run_id: string | null;
}

export type BaseMetricKey =
  | "ic_adj"
  | "icir"
  | "t_stat"
  | "ic_win_rate"
  | "long_ann_ret"
  | "long_max_dd"
  | "long_sharpe"
  | "long_exc_ann_ret"
  | "monotonicity"
  | "turnover_long";

export type BaseStatus = "ok" | "mixed" | "unevaluated" | "missing";

export interface BaseWindow {
  name: string;
  window: number | null;
  evaluated: boolean;
  icir: Num;
  direction: Num;
}

/** One board row: a base factor summarised by its primary version (see zer0factor/web/bases.py). */
export interface BaseRow {
  base: string;
  primary_prep: string;
  status: BaseStatus;
  direction: Num;
  icir_median: Num;
  /** Board metrics: median over the primary version's scored windows (all null without a number). */
  metrics: Record<BaseMetricKey, Num>;
  start_date: string | null;
  end_date: string | null;
  run_ids: string[];
  windows: BaseWindow[];
  preps: { prep: string; n_versions: number; n_evaluated: number }[];
}

export interface BaseVersion extends BaseWindow {
  prep: string;
  run_id: string | null;
  /** Latest standard evaluation's board metrics (all null when unevaluated). */
  metrics: Record<BaseMetricKey, Num>;
}

export type CurveKind = "long_excess" | "long" | "ls";

/** Overlay curves of several versions of one base factor (cache only). */
export interface BaseCurves {
  kind: CurveKind;
  dates: string[];
  series: Record<string, Num[]>;
  missing: string[];
}

export interface BaseInfo {
  base: string;
  primary_prep: string;
  default_prep: string;
  versions: BaseVersion[];
}

export interface FactorInfo {
  name: string;
  meta: { category: string | null; tags: string[]; description: string };
  runs: RunSummary[];
  default_run: string | null;
}

export interface IcBlock {
  series: { dates: string[]; values: Num[]; cumulative: Num[] } | null;
  monthly: boolean;
  hist: { edges: number[]; density: Num[]; normal: Num[] } | null;
  acf: { acf: Num[]; ci: Num } | null;
  decay: Num[] | null;
}

export interface GroupRow {
  group: string;
  ann_ret: Num;
  exc_ann_ret: Num;
  max_dd: Num;
  ann_vol: Num;
  sharpe: Num;
}

export interface Detail {
  summary: Record<string, number | string | null>;
  direction: Num;
  period: string;
  notes: string[];
  cumulative: {
    dates: string[];
    groups: Record<string, Num[]>;
    long?: Num[];
    short?: Num[];
    ls?: Num[];
  } | null;
  group_table: GroupRow[] | null;
  rank_ic: IcBlock;
  ic: IcBlock;
}

export interface LatestValues {
  date: string | null;
  total: number;
  items: { ts_code: string; name: string | null; value: Num; quantile: number }[];
}

export interface Compare {
  factors: string[];
  rows: BoardRow[];
  inconsistent: string[];
  unevaluated: string[];
  missing_curve: string[];
  curves: { dates: string[]; series: Record<string, Num[]> };
}

export interface Correlation {
  factors: string[];
  matrix: Num[][];
  dates_used: number;
  start: string;
  end: string;
  threshold: number;
  pairs_over_threshold: { a: string; b: string; rho: number }[];
}

export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "lost";
export type TaskKind = "evaluate" | "build" | "base" | "warm";

export interface Task {
  id: string;
  kind: TaskKind;
  queue: string;
  title: string;
  params: Record<string, unknown>;
  command: string[];
  cwd: string;
  status: TaskStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  pid: number | null;
  exit_code: number | null;
  progress_done: number;
  progress_total: number | null;
  last_line: string | null;
  run_id: string | null;
  parent_id: string | null;
  error: string | null;
  source: string;
}

export interface TaskList {
  tasks: Task[];
  running: number;
  queued: number;
}

export interface TaskLog {
  text: string;
  offset: number;
  size: number;
  done: boolean;
}

export interface EvaluateParams {
  factors: string[];
  start_date: string;
  end_date: string | null;
  periods: number[];
  quantiles: number;
  return_type: string;
  universe: string | null;
  max_loss: number;
  transaction_cost_bps: number;
  benchmark_index: string | null;
  workers: number;
}

export interface EvalOptions {
  standard: StandardSetting;
  defaults: Omit<EvaluateParams, "factors">;
  universes: string[];
  return_types: string[];
}

export interface Family {
  name: string;
  module: string;
  origin: "builtin" | "package" | "explicit";
  error: string | null;
  base_factors: string[];
  windows: number[];
  profiles: string[];
  raw_names: string[];
  outputs: string[];
  uses_data_provider: boolean;
  source: Record<string, string> | null;
  status: "enabled" | "archived";
  note: string;
  first_seen: string | null;
  is_new: boolean;
  stored: number;
  stored_names: string[];
  data_end: string | null;
  last_task: { id: string; status: TaskStatus; created_at: string } | null;
}
