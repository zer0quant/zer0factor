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
import { heatScale } from "../heat";
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
  { key: "long_ann_ret", label: "多头年化", fmt: (v) => pct(v, 1), center: 0 },
  { key: "long_sharpe", label: "多头夏普", fmt: (v) => num(v, 2), center: 0 },
  { key: "long_max_dd", label: "多头回撤", fmt: (v) => pct(v, 1), center: null, better: "high" },
  { key: "long_exc_ann_ret", label: "多头超额", fmt: (v) => pct(v, 1), center: 0 },
  { key: "monotonicity", label: "单调性", fmt: (v) => num(v, 2), center: 0 },
  { key: "turnover_long", label: "多头换手", fmt: (v) => pct(v, 1), center: null, better: "low" },
];

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

  const scale = useMemo(
    () =>
      heatScale(
        matrixRows.flatMap((mr) => [...mr.cells.values()].map((r) => r[metric.key] as Num)),
        metric,
        pal,
      ),
    [matrixRows, metric, pal],
  );
  const paint = scale.paint;

  if (!matrixRows.length)
    return <Empty description="筛选结果里没有已评估的因子，矩阵视图只显示有评估结果的组合" />;

  const open = (name: string) => navigate(`/factor/${encodeURIComponent(name)}`);
  const onCell = (e: React.MouseEvent | React.KeyboardEvent, name: string) => {
    const toggle = selectMode || e.shiftKey;
    if (toggle) onToggle(name);
    else open(name);
  };

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
                                  ICIR {num(r.icir, 3)} · 多头年化 {pct(r.long_ann_ret)} ·{" "}
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
        颜色：{scale.legend}；色阶按当前可见格子的 5%–95% 分位计算。
        {hiddenRows > 0 && ` 另有 ${hiddenRows} 组没有任何评估结果，未显示（可切回列表查看）。`}
      </Typography.Text>
    </>
  );
}
