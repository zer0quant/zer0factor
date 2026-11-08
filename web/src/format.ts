import { universeLabel } from "./vocab";
import type { Num } from "./types";

/** CSS colour tokens (defined in index.css, switch with the theme). For DOM text only. */
export const RED = "var(--zf-up)";
export const GREEN = "var(--zf-down)";
export const GREY = "var(--zf-muted)";

const isNum = (v: Num | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export function pct(v: Num | undefined, digits = 2): string {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : "—";
}

export function num(v: Num | undefined, digits = 4): string {
  return isNum(v) ? v.toFixed(digits) : "—";
}

/** 涨红跌绿：正值红色、负值绿色，空值灰色。 */
export function signColor(v: Num | undefined): string {
  if (!isNum(v) || v === 0) return GREY;
  return v > 0 ? RED : GREEN;
}

export function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  return d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : d;
}

export function runLabel(r: {
  run_id: string;
  start_date: string | null;
  end_date: string | null;
  universe: string | null;
  quantiles: number | null;
  periods: string[];
}): string {
  const range = `${fmtDate(r.start_date)} → ${r.end_date ? fmtDate(r.end_date) : "最新"}`;
  return `${r.run_id} · ${range} · ${universeLabel(r.universe)} · ${r.quantiles ?? "?"}组 · ${r.periods.join("/")}`;
}

/** Prefix "+" for positive values, so sign is not conveyed by colour alone. */
export function withSign(text: string, v: Num | undefined): string {
  return isNum(v) && v > 0 && !text.startsWith("+") ? `+${text}` : text;
}

export { isNum };
