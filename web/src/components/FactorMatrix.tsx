import { useMemo } from "react";
import { Empty, Tag, Tooltip, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import {
  baseLabel,
  compareBase,
  comparePrep,
  parseFactorName,
  prepColor,
  prepLabel,
  windowLabel,
} from "../factorName";
import { isNum, num, pct } from "../format";
import { usePalette } from "../theme";
import type { BoardRow, Num } from "../types";

export interface MatrixMetric {
  key: keyof BoardRow;
  label: string;
  fmt: (v: Num) => string;
  /** Diverging colour around this value (red above, green below); null = sequential. */
  center: number | null;
  /** For sequential metrics: which end is better (darker). */
  better?: "high" | "low";
}

export const MATRIX_METRICS: MatrixMetric[] = [
  { key: "icir", label: "ICIR", fmt: (v) => num(v, 3), center: 0 },
  { key: "ic_adj", label: "方向调整 IC", fmt: (v) => num(v, 4), center: 0 },
  { key: "ic_win_rate", label: "IC 胜率", fmt: (v) => (isNum(v) ? `${v.toFixed(1)}%` : "—"), center: 50 },
  { key: "ls_ann_ret", label: "多空年化", fmt: (v) => pct(v, 1), center: 0 },
  { key: "ls_sharpe", label: "多空夏普", fmt: (v) => num(v, 2), center: 0 },
  { key: "ls_max_dd", label: "多空回撤", fmt: (v) => pct(v, 1), center: null, better: "high" },
  { key: "long_exc_ann_ret", label: "多头超额", fmt: (v) => pct(v, 1), center: 0 },
  { key: "monotonicity", label: "单调性", fmt: (v) => num(v, 2), center: 0 },
  { key: "turnover_long", label: "多头换手", fmt: (v) => pct(v, 1), center: null, better: "low" },
];

const SEQ = "#3b82f6";

function rgba(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`;
}

interface MatrixRow {
  key: string;
  base: string;
  prep: string;
  cells: Map<number | null, BoardRow>;
}

export function FactorMatrix({
  rows,
  metric,
  selected,
  selectMode,
  onToggle,
}: {
  rows: BoardRow[];
  metric: MatrixMetric;
  selected: string[];
  /** true: a plain click toggles compare selection instead of opening the detail page. */
  selectMode: boolean;
  onToggle: (name: string) => void;
}) {
  const pal = usePalette();
  const navigate = useNavigate();

  const { matrixRows, windows, hiddenRows } = useMemo(() => {
    const byKey = new Map<string, MatrixRow>();
    const wins = new Set<number | null>();
    for (const r of rows) {
      const p = parseFactorName(r.name);
      const key = `${p.base}|${p.prep}`;
      let mr = byKey.get(key);
      if (!mr) {
        mr = { key, base: p.base, prep: p.prep, cells: new Map() };
        byKey.set(key, mr);
      }
      mr.cells.set(p.window, r);
      wins.add(p.window);
    }
    const all = [...byKey.values()].sort(
      (a, b) => compareBase(a.base, b.base) || comparePrep(a.prep, b.prep),
    );
    const shown = all.filter((mr) => [...mr.cells.values()].some((r) => r.evaluated));
    const usedWins = new Set<number | null>();
    shown.forEach((mr) => mr.cells.forEach((_, w) => usedWins.add(w)));
    const windows = [...wins]
      .filter((w) => usedWins.has(w))
      .sort((a, b) => (a == null ? 1 : b == null ? -1 : a - b));
    return { matrixRows: shown, windows, hiddenRows: all.length - shown.length };
  }, [rows]);

  // Robust colour range: 5th–95th percentile, so one outlier does not wash out the rest.
  const scale = useMemo(() => {
    const vals = matrixRows
      .flatMap((mr) => [...mr.cells.values()].map((r) => r[metric.key] as Num))
      .filter(isNum)
      .sort((a, b) => a - b);
    if (!vals.length) return { lo: 0, hi: 0 };
    const q = (p: number) => vals[Math.min(vals.length - 1, Math.max(0, Math.round(p * (vals.length - 1))))];
    return { lo: q(0.05), hi: q(0.95) };
  }, [matrixRows, metric]);

  const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

  /** Background colour for a value; `strong` means white text is needed. */
  const paint = (v: Num): { bg?: string; strong: boolean } => {
    if (!isNum(v)) return { strong: false };
    const { lo, hi } = scale;
    const c = metric.center;
    let t: number;
    let color: string;
    if (c != null && lo < c && hi > c) {
      // Values on both sides of the centre: diverging, red above / green below.
      const dev = Math.max(hi - c, c - lo);
      t = clamp01(Math.abs(v - c) / dev);
      color = v >= c ? pal.up : pal.down;
    } else {
      // One-sided (or no centre): sequential over the visible range.
      const span = hi - lo;
      t = span > 0 ? clamp01((v - lo) / span) : 1;
      if (c != null) {
        color = hi <= c ? pal.down : pal.up;
        if (hi <= c) t = 1 - t; // all below centre: darker = further below
      } else {
        color = SEQ;
        if (metric.better === "low") t = 1 - t;
      }
    }
    const a = 0.06 + 0.74 * t;
    return { bg: rgba(color, a), strong: a > 0.5 };
  };

  if (!matrixRows.length)
    return <Empty description="筛选结果里没有已评估的因子，矩阵视图只显示有评估结果的组合" />;

  const open = (name: string) => navigate(`/factor/${encodeURIComponent(name)}`);
  const onCell = (e: React.MouseEvent | React.KeyboardEvent, name: string) => {
    const toggle = selectMode || e.shiftKey;
    if (toggle) onToggle(name);
    else open(name);
  };

  const c = metric.center;
  const legend =
    c == null
      ? `颜色：越深越${metric.better === "low" ? "低" : "高"}（越好）`
      : scale.lo < c && scale.hi > c
        ? `颜色：红色高于 ${c}、绿色低于 ${c}，越深偏离越大`
        : `颜色：全部${scale.hi <= c ? "低于" : "高于"} ${c}，越深偏离越大`;

  return (
    <>
      <div className="zf-matrix-wrap">
        <table className="zf-matrix">
          <thead>
            <tr>
              <th className="zf-matrix-rowhead">收益类型</th>
              <th className="zf-matrix-rowhead">预处理</th>
              {windows.map((w) => (
                <th key={String(w)} className="num">
                  {windowLabel(w)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrixRows.map((mr, i) => {
              const first = i === 0 || matrixRows[i - 1].base !== mr.base;
              const span = matrixRows.filter((x) => x.base === mr.base).length;
              return (
                <tr key={mr.key} className={first ? "zf-matrix-groupstart" : undefined}>
                  {first && (
                    <th rowSpan={span} className="zf-matrix-rowhead zf-matrix-base" title={mr.base}>
                      {baseLabel(mr.base)}
                    </th>
                  )}
                  <th className="zf-matrix-rowhead">
                    <Tag color={prepColor(mr.prep)} bordered={false} style={{ marginInlineEnd: 0 }}>
                      {prepLabel(mr.prep)}
                    </Tag>
                  </th>
                  {windows.map((w) => {
                    const r = mr.cells.get(w);
                    if (!r) return <td key={String(w)} className="zf-matrix-empty" />;
                    const v = r[metric.key] as Num;
                    const { bg, strong } = paint(v);
                    const isSel = selected.includes(r.name);
                    return (
                        <Tooltip
                          key={String(w)}
                          mouseEnterDelay={0.3}
                          title={
                            <>
                              <div style={{ overflowWrap: "anywhere" }}>{r.name}</div>
                              {r.evaluated ? (
                                <div className="num">
                                  ICIR {num(r.icir, 3)} · 多空年化 {pct(r.ls_ann_ret)} ·{" "}
                                  {r.direction === -1 ? "反向" : "正向"}
                                </div>
                              ) : (
                                <div>未评估</div>
                              )}
                              <div style={{ opacity: 0.7, fontSize: 12 }}>
                                {selectMode ? "点击勾选/取消对比" : "点击打开详情，Shift+点击勾选对比"}
                              </div>
                            </>
                          }
                        >
                          <td
                            tabIndex={0}
                            role="button"
                            aria-label={`${r.name} ${metric.label} ${metric.fmt(v)}`}
                            aria-pressed={isSel}
                            className={`num zf-matrix-cell${isSel ? " zf-matrix-sel" : ""}`}
                            style={{ background: bg, color: strong ? "#fff" : undefined }}
                            onClick={(e) => onCell(e, r.name)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                onCell(e, r.name);
                              }
                            }}
                          >
                            {r.evaluated ? metric.fmt(v) : "—"}
                          </td>
                        </Tooltip>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
        {legend}；色阶按当前可见格子的 5%–95% 分位计算。
        {hiddenRows > 0 && ` 另有 ${hiddenRows} 组没有任何评估结果，未显示（可切回列表查看）。`}
      </Typography.Text>
    </>
  );
}
