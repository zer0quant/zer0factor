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
