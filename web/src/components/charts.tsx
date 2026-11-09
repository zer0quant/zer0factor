import { useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { Empty, Grid, Segmented, Space, Typography } from "antd";
import { usePalette, type Palette } from "../theme";
import type { GroupRow, IcBlock, Num } from "../types";

const GROUP_COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
  "#f97316",
  "#6366f1",
];
/**
 * Ordered palette for quantile groups (plasma ramp): group 1 → N reads as a
 * gradient, so monotonicity is visible at a glance. The dark-theme ramp skips
 * the darkest end so lines stay visible on a dark background.
 */
const GROUP_RAMP_LIGHT = [
  "#0d0887",
  "#41049d",
  "#6a00a8",
  "#8f0da4",
  "#b12a90",
  "#cc4778",
  "#e16462",
  "#f1834b",
  "#fca636",
  "#e3a10b",
];
const GROUP_RAMP_DARK = [
  "#7b6cf6",
  "#9a5cf0",
  "#b14fd8",
  "#c44bb8",
  "#d4549a",
  "#e16462",
  "#ec7a52",
  "#f59342",
  "#fbae34",
  "#f9d23c",
];
export function groupColors(n: number, dark: boolean): string[] {
  const ramp = dark ? GROUP_RAMP_DARK : GROUP_RAMP_LIGHT;
  if (n <= 1) return [ramp[0]];
  return Array.from({ length: n }, (_, i) => ramp[Math.round((i * (ramp.length - 1)) / (n - 1))]);
}

/** Flip an IC block's sign for a negative-direction factor (ACF is sign-invariant). */
export function adjustIcBlock(block: IcBlock, direction: number): IcBlock {
  if (direction !== -1) return block;
  const neg = (a: Num[]) => a.map((v) => (typeof v === "number" ? -v : v));
  return {
    ...block,
    series: block.series && {
      dates: block.series.dates,
      values: neg(block.series.values),
      cumulative: neg(block.series.cumulative),
    },
    hist: block.hist && {
      edges: block.hist.edges.map((e) => -e).reverse(),
      density: [...block.hist.density].reverse(),
      normal: [...block.hist.normal].reverse(),
    },
    decay: block.decay && neg(block.decay),
  };
}

const pctLabel = (v: number) => `${(v * 100).toFixed(0)}%`;
const pctAxis = { axisLabel: { formatter: pctLabel } };
const pctTip = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(2)}%` : "—");
const numTip = (v: unknown) => (typeof v === "number" ? v.toFixed(4) : "—");

function Chart({ option, height = 300 }: { option: EChartsOption; height?: number }) {
  const pal = usePalette();
  return (
    <ReactECharts
      // Re-create the instance when the theme flips: ECharts themes apply at init time.
      key={pal.dark ? "dark" : "light"}
      theme={pal.dark ? "dark" : undefined}
      option={{ backgroundColor: "transparent", aria: { enabled: true }, ...option }}
      style={{ height }}
      notMerge
      lazyUpdate
    />
  );
}

const barColor = (pal: Palette) => (v: Num) => ((v ?? 0) >= 0 ? pal.up : pal.down);

/** Gross equal-weight cumulative return of each quantile group (net long/short lines live elsewhere). */
export function CumulativeChart({ dates, groups }: { dates: string[]; groups: Record<string, Num[]> }) {
  const pal = usePalette();
  const [scale, setScale] = useState<"linear" | "log">("linear");
  const log = scale === "log";
  // Log scale plots net value (1 + cumulative return); non-positive net values have no log.
  const tf = (d: Num[]) => (log ? d.map((v) => (typeof v === "number" && v > -1 ? 1 + v : null)) : d);
  const keys = Object.keys(groups).sort((a, b) => +a - +b);
  const ramp = groupColors(keys.length, pal.dark);
  const series = keys.map((k, i) => ({
    name: `组${k}`,
    type: "line" as const,
    data: tf(groups[k]),
    showSymbol: false,
    lineStyle: { width: 1.5 },
    color: ramp[i],
  }));
  const toRet = (v: unknown) => (typeof v === "number" && log ? v - 1 : v);
  return (
    <>
      <Space size={8} wrap style={{ marginBottom: 4 }}>
        <Segmented
          size="small"
          value={scale}
          onChange={(v) => setScale(v as "linear" | "log")}
          options={[
            { value: "linear", label: "线性坐标" },
            { value: "log", label: "对数坐标" },
          ]}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          分组颜色由深到浅对应组1→组{keys.length}
        </Typography.Text>
      </Space>
      <Chart
        height={380}
        option={{
          tooltip: { trigger: "axis", valueFormatter: (v) => pctTip(toRet(v)) },
          legend: { type: "scroll", top: 0 },
          grid: { left: 56, right: 24, top: 40, bottom: 56 },
          xAxis: { type: "category", data: dates, boundaryGap: false },
          yAxis: log
            ? {
                type: "log",
                logBase: 2,
                axisLabel: { formatter: (v: number) => pctLabel(v - 1) },
              }
            : { type: "value", scale: true, ...pctAxis },
          dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }],
          series,
        }}
      />
    </>
  );
}

/** Several cumulative-return lines on one chart; `bold` names the highlighted one. */
export function OverlayChart({
  dates,
  lines,
  bold,
  height = 300,
}: {
  dates: string[];
  lines: { key: string; label: string; data: Num[] }[];
  bold?: string;
  height?: number;
}) {
  const pal = usePalette();
  return (
    <Chart
      height={height}
      option={{
        tooltip: { trigger: "axis", valueFormatter: pctTip },
        legend: { type: "scroll", top: 0 },
        grid: { left: 56, right: 24, top: 36, bottom: 56 },
        xAxis: { type: "category", data: dates, boundaryGap: false },
        yAxis: { type: "value", scale: true, ...pctAxis },
        dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }],
        color: pal.dark ? GROUP_RAMP_DARK.filter((_, i) => i % 2 === 0).concat(GROUP_COLORS) : GROUP_COLORS,
        series: lines.map((l) => ({
          name: l.label,
          type: "line" as const,
          data: l.data,
          showSymbol: false,
          lineStyle: { width: l.key === bold ? 3 : 1.3 },
          z: l.key === bold ? 3 : 2,
        })),
      }}
    />
  );
}

/** Per-group annualised return bars (excluding the long-short row): is the factor monotonic? */
export function GroupBars({
  rows,
  field,
  height = 330,
}: {
  rows: GroupRow[];
  field: "exc_ann_ret" | "ann_ret";
  height?: number;
}) {
  const pal = usePalette();
  const groups = rows.filter((r) => r.group !== "多空");
  if (!groups.length) return <Empty description="无分组收益数据" />;
  return (
    <Chart
      height={height}
      option={{
        tooltip: { trigger: "axis", valueFormatter: pctTip },
        grid: { left: 52, right: 16, top: 28, bottom: 30 },
        xAxis: { type: "category", data: groups.map((r) => `组${r.group}`) },
        yAxis: { type: "value", ...pctAxis },
        series: [
          {
            name: field === "exc_ann_ret" ? "超额年化" : "年化收益",
            type: "bar",
            data: groups.map((r) => ({
              value: r[field],
              itemStyle: { color: barColor(pal)(r[field]) },
              label: { position: (r[field] ?? 0) >= 0 ? ("top" as const) : ("bottom" as const) },
            })),
            label: {
              show: true,
              fontSize: 10,
              formatter: (p: { value: unknown }) =>
                typeof p.value === "number" ? `${(p.value * 100).toFixed(1)}%` : "",
            },
          },
        ],
      }}
    />
  );
}

export function IcSeriesChart({ block, label }: { block: IcBlock; label: string }) {
  const pal = usePalette();
  const s = block.series;
  if (!s || !s.values.length) return <Empty description="无 IC 数据" />;
  return (
    <Chart
      option={{
        tooltip: { trigger: "axis", valueFormatter: numTip },
        legend: { top: 0, data: [label, `累计 ${label}`] },
        grid: { left: 52, right: 52, top: 36, bottom: 30 },
        xAxis: { type: "category", data: s.dates },
        yAxis: [
          { type: "value", scale: true },
          { type: "value", scale: true, splitLine: { show: false } },
        ],
        series: [
          {
            name: label,
            type: "bar",
            data: s.values.map((v) => ({ value: v, itemStyle: { color: barColor(pal)(v) } })),
          },
          {
            name: `累计 ${label}`,
            type: "line",
            yAxisIndex: 1,
            data: s.cumulative,
            showSymbol: false,
            color: pal.dark ? "#60a5fa" : "#2563eb",
          },
        ],
      }}
    />
  );
}

export function DecayChart({ block }: { block: IcBlock }) {
  const pal = usePalette();
  const d = block.decay;
  if (!d || !d.length) return <Empty description="缺少原始数据，无法计算衰减" />;
  return (
    <Chart
      option={{
        tooltip: { trigger: "axis", valueFormatter: numTip },
        grid: { left: 52, right: 16, top: 24, bottom: 30 },
        xAxis: { type: "category", data: d.map((_, i) => String(i)), name: "滞后(日)" },
        yAxis: { type: "value", scale: true },
        series: [
          {
            type: "bar",
            name: "IC 均值",
            data: d.map((v) => ({ value: v, itemStyle: { color: barColor(pal)(v) } })),
          },
        ],
      }}
    />
  );
}

export function CompareCurves({ dates, series }: { dates: string[]; series: Record<string, Num[]> }) {
  return (
    <Chart
      height={360}
      option={{
        tooltip: { trigger: "axis", valueFormatter: pctTip },
        legend: { type: "scroll", top: 0, itemGap: 24 },
        grid: { left: 56, right: 24, top: 40, bottom: 56 },
        xAxis: { type: "category", data: dates, boundaryGap: false },
        yAxis: { type: "value", scale: true, ...pctAxis },
        dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }],
        series: Object.entries(series).map(([name, data], i) => ({
          name,
          type: "line",
          data,
          showSymbol: false,
          color: GROUP_COLORS[i % GROUP_COLORS.length],
        })),
      }}
    />
  );
}

/** Short axis label for factor i: "#1", "#2", ... (full names go on the y axis and tooltip). */
export const factorTag = (i: number) => `#${i + 1}`;

export function CorrHeatmap({
  factors,
  labels = factors,
  matrix,
  threshold,
}: {
  factors: string[];
  /** Display labels for the y axis (defaults to the full names). */
  labels?: string[];
  matrix: Num[][];
  threshold: number;
}) {
  const pal = usePalette();
  const screens = Grid.useBreakpoint();
  const compact = screens.md === false;
  const data = matrix.flatMap((row, i) => row.map((v, j) => [j, i, v]));
  const cell = compact ? 44 : 56;
  const longest = Math.max(...labels.map((f, i) => `${factorTag(i)}  ${f}`.length));
  const labelWidth = Math.min(compact ? 120 : 300, longest * 12 + 8);
  const height = Math.max(260, factors.length * cell + 110);
  return (
    <Chart
      height={height}
      option={{
        tooltip: {
          formatter: (p: unknown) => {
            const [j, i, v] = (p as { value: [number, number, Num] }).value;
            return `${factorTag(i)} ${factors[i]}<br/>${factorTag(j)} ${factors[j]}<br/>ρ = ${
              typeof v === "number" ? v.toFixed(3) : "—"
            }`;
          },
        },
        grid: { left: labelWidth + 16, right: 16, top: 8, bottom: 88 },
        xAxis: {
          type: "category",
          data: factors.map((_, i) => factorTag(i)),
          axisLabel: { interval: 0 },
          splitArea: { show: false },
        },
        yAxis: {
          type: "category",
          data: labels.map((f, i) => `${factorTag(i)}  ${f}`),
          inverse: true,
          axisLabel: { interval: 0, width: labelWidth, overflow: "truncate" },
        },
        visualMap: {
          min: -1,
          max: 1,
          calculable: true,
          orient: "horizontal",
          left: "center",
          bottom: 0,
          itemHeight: compact ? 140 : 200,
          itemWidth: 12,
          inRange: { color: [pal.down, pal.surface, pal.up] },
        },
        series: [
          {
            type: "heatmap",
            data: data.map(([x, y, v]) => ({
              value: [x, y, v],
              // Strong colours get white text; pale cells keep the theme's ink colour.
              label: typeof v === "number" && Math.abs(v) >= 0.6 ? { color: "#fff" } : undefined,
              itemStyle:
                x !== y && typeof v === "number" && Math.abs(v) >= threshold
                  ? { borderColor: pal.border, borderWidth: 2 }
                  : undefined,
            })),
            label: {
              show: true,
              color: pal.ink,
              formatter: (p: unknown) => {
                const v = (p as { value: [number, number, Num] }).value[2];
                return typeof v === "number" ? v.toFixed(2) : "";
              },
            },
          },
        ],
      }}
    />
  );
}
