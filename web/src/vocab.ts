/**
 * Display names for evaluation-setting codes. Universe names and rules follow zer0share's
 * docs/guides/universe.md; unknown codes fall back to the code itself.
 */

const RESEARCH_BASE_RULES = [
  "A 股普通股票，当日已上市、未退市",
  "非 ST / 非 *ST",
  "上市满 6 个月",
  "过去 20 个交易日日均成交额 ≥ 1000 万元",
  "总市值排名不在全市场最后 2%",
];

const TRADE_BASE_EXTRA = [
  "当日非停牌",
  "当日非一字涨停 / 一字跌停",
  "总市值排名不在全市场最后 5%",
];

interface UniverseInfo {
  label: string;
  /** Rule groups shown in the definition tooltip: [heading, rules]. */
  rules: [string, string[]][];
}

const UNIVERSES: Record<string, UniverseInfo> = {
  univ_research_base: {
    label: "基础研究池",
    rules: [["", RESEARCH_BASE_RULES]],
  },
  univ_trade_base: {
    label: "基础交易池",
    rules: [
      ["满足基础研究池：", RESEARCH_BASE_RULES],
      ["并且：", TRADE_BASE_EXTRA],
    ],
  },
  univ_trade_hs300: {
    label: "沪深300交易池",
    rules: [["沪深300成分股中满足基础交易池条件的股票", []]],
  },
  univ_trade_zz500: {
    label: "中证500交易池",
    rules: [["中证500成分股中满足基础交易池条件的股票", []]],
  },
  univ_trade_zz1000: {
    label: "中证1000交易池",
    rules: [["中证1000成分股中满足基础交易池条件的股票", []]],
  },
  univ_trade_smallcap: {
    label: "小市值交易池",
    rules: [["基础交易池中总市值倒数 20% 的股票", []]],
  },
};

export const universeLabel = (code: string | null | undefined): string =>
  code ? (UNIVERSES[code]?.label ?? code) : "全部";

export const universeRules = (code: string | null | undefined): [string, string[]][] | null =>
  (code && UNIVERSES[code]?.rules) || null;

const RETURN_TYPES: Record<string, string> = {
  open_t1: "次日开盘成交",
  close_t0: "当日收盘成交",
};

export const returnTypeLabel = (code: string | null | undefined): string =>
  code ? (RETURN_TYPES[code] ?? code) : "—";

/** "1D" -> "1 日"; other formats pass through. */
export const periodLabel = (p: string): string => {
  const m = /^(\d+)D$/.exec(p);
  return m ? `${m[1]} 日` : p;
};
