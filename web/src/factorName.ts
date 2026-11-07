/**
 * Parse systematic factor names into (preprocessing, base factor, window).
 *
 * Names follow zer0factor/preprocess_profile.py + rolling families:
 *   [<z|rank>_[<size|industry|size_industry>_neu_]]<base>[_ma<N>]
 * plus the legacy `z_neu_` prefix. Anything that does not match keeps its raw
 * text as the base, so unknown names still display sensibly.
 */

export interface ParsedName {
  name: string;
  /** Preprocessing key: "raw", "z", "z_size_neu", "rank_industry_neu", "z_neu", ... */
  prep: string;
  base: string;
  window: number | null;
}

const PREP_RE = /^(z|rank)_(?:(size_industry|size|industry)_neu_|(neu)_)?/;
const WINDOW_RE = /_ma(\d+)$/;

export function parseFactorName(name: string): ParsedName {
  let rest = name;
  let prep = "raw";
  const m = PREP_RE.exec(name);
  if (m && m[0].length < name.length) {
    prep = m[2] ? `${m[1]}_${m[2]}_neu` : m[3] ? `${m[1]}_neu` : m[1];
    rest = name.slice(m[0].length);
  }
  let window: number | null = null;
  const w = WINDOW_RE.exec(rest);
  if (w && w.index > 0) {
    window = Number(w[1]);
    rest = rest.slice(0, w.index);
  }
  return { name, prep, base: rest, window };
}

const NEU_LABEL: Record<string, string> = {
  size_neu: "市值中性",
  industry_neu: "行业中性",
  size_industry_neu: "行业+市值中性",
  neu: "中性化",
};

/** Human label for a preprocessing key. */
export function prepLabel(prep: string): string {
  if (prep === "raw") return "原始";
  const [std, ...neu] = prep.split("_");
  const stdLabel = std === "rank" ? "Rank" : "Z";
  if (!neu.length) return `${stdLabel} 标准化`;
  const n = NEU_LABEL[neu.join("_")] ?? neu.join("_");
  return std === "rank" ? `Rank·${n}` : n;
}

/** Fixed display order of preprocessing keys (unknown keys go last, alphabetically). */
const PREP_ORDER = [
  "raw",
  "z",
  "z_size_neu",
  "z_industry_neu",
  "z_size_industry_neu",
  "z_neu",
  "rank",
  "rank_size_neu",
  "rank_industry_neu",
  "rank_size_industry_neu",
];
export function comparePrep(a: string, b: string): number {
  const ia = PREP_ORDER.indexOf(a);
  const ib = PREP_ORDER.indexOf(b);
  if (ia < 0 && ib < 0) return a.localeCompare(b);
  if (ia < 0) return 1;
  if (ib < 0) return -1;
  return ia - ib;
}

/** antd preset Tag colour per preprocessing key. */
const PREP_COLOR: Record<string, string> = {
  raw: "default",
  z: "blue",
  z_size_neu: "cyan",
  z_industry_neu: "purple",
  z_size_industry_neu: "geekblue",
  z_neu: "gold",
  rank: "blue",
  rank_size_neu: "cyan",
  rank_industry_neu: "purple",
  rank_size_industry_neu: "geekblue",
};
export const prepColor = (prep: string) => PREP_COLOR[prep] ?? "default";

/** Short labels only for base factors whose meaning is unambiguous; others show as-is. */
const BASE_LABEL: Record<string, string> = {
  daily_return: "全日收益",
  intraday_return: "日内收益",
  open_return: "开盘收益",
  overnight_return: "隔夜收益",
  log_total_market_cap: "对数总市值",
  log_circulating_market_cap: "对数流通市值",
};
export const baseLabel = (base: string) => BASE_LABEL[base] ?? base;

/** Base factors in a stable order: known labels first (in BASE_LABEL order), then alphabetical. */
const BASE_ORDER = Object.keys(BASE_LABEL);
export function compareBase(a: string, b: string): number {
  const ia = BASE_ORDER.indexOf(a);
  const ib = BASE_ORDER.indexOf(b);
  if (ia >= 0 && ib >= 0) return ia - ib;
  if (ia >= 0) return -1;
  if (ib >= 0) return 1;
  return a.localeCompare(b);
}

export const windowLabel = (w: number | null) => (w == null ? "无窗口" : `MA${w}`);

/** Compact one-line label, e.g. "行业+市值中性 · 日内收益 · MA5". */
export function shortName(name: string): string {
  const p = parseFactorName(name);
  return [prepLabel(p.prep), baseLabel(p.base), ...(p.window != null ? [`MA${p.window}`] : [])].join(" · ");
}
