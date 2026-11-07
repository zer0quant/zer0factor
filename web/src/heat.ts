import { isNum } from "./format";
import type { Palette } from "./theme";
import type { Num } from "./types";

/** How a metric is coloured: diverging around `center`, or sequential (`better` end darker). */
export interface HeatSpec {
  center: number | null;
  better?: "high" | "low";
}

const SEQ = "#3b82f6";

function rgba(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`;
}

export interface HeatScale {
  lo: number;
  hi: number;
  paint: (v: Num) => { bg?: string; strong: boolean };
  /** One-line explanation of the colours for a legend. */
  legend: string;
}

/**
 * Colour scale over a set of values. The range is the 5th–95th percentile, so a
 * single outlier does not wash out the rest. Values on both sides of `center`
 * diverge (red above / green below, matching 涨红跌绿); otherwise sequential.
 */
export function heatScale(values: Num[], spec: HeatSpec, pal: Palette): HeatScale {
  const vals = values.filter(isNum).sort((a, b) => a - b);
  const q = (p: number) =>
    vals[Math.min(vals.length - 1, Math.max(0, Math.round(p * (vals.length - 1))))];
  const lo = vals.length ? q(0.05) : 0;
  const hi = vals.length ? q(0.95) : 0;
  const c = spec.center;
  const diverging = c != null && lo < c && hi > c;
  const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

  const paint = (v: Num) => {
    if (!isNum(v) || !vals.length) return { strong: false };
    let t: number;
    let color: string;
    if (diverging) {
      const dev = Math.max(hi - c!, c! - lo);
      t = clamp01(Math.abs(v - c!) / dev);
      color = v >= c! ? pal.up : pal.down;
    } else {
      const span = hi - lo;
      t = span > 0 ? clamp01((v - lo) / span) : 1;
      if (c != null) {
        const below = hi <= c;
        color = below ? pal.down : pal.up;
        if (below) t = 1 - t; // all below centre: darker = further below
      } else {
        color = SEQ;
        if (spec.better === "low") t = 1 - t;
      }
    }
    const a = 0.06 + 0.74 * t;
    return { bg: rgba(color, a), strong: a > 0.5 };
  };

  const legend =
    c == null
      ? `越深越${spec.better === "low" ? "低" : "高"}（越好）`
      : diverging
        ? `红色高于 ${c}、绿色低于 ${c}，越深偏离越大`
        : `全部${hi <= c ? "低于" : "高于"} ${c}，越深偏离越大`;

  return { lo, hi, paint, legend };
}
