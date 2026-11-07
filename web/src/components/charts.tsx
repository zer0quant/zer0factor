import { useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { Empty, Grid, Segmented, Space, Typography } from "antd";
import { usePalette, type Palette } from "../theme";
import type { IcBlock, Num } from "../types";

const GROUP_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];
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
      option={{ backgroundColor: "transparent", ...option }}
      style={{ height }}
      notMerge
      lazyUpdate
    />
  );
}

const barColor = (pal: Palette) => (v: Num) => ((v ?? 0) >= 0 ? pal.up : pal.down);

export function CumulativeChart({
  dates,
  groups,
  long,
  short,
  ls,
}: {
  dates: string[];
  groups: Record<string, Num[]>;
  long?: Num[];
  short?: Num[];
  ls?: Num[];
}) {
  const pal = usePalette();
  const [scale, setScale] = useState<"linear" | "log">("linear");
  const log = scale === "log";
  // Log scale plots net value (1 + cumulative return); non-positive net values have no log.
  const tf = (d: Num[]) => (log ? d.map((v) => (typeof v === "number" && v > -1 ? 1 + v : null)) : d);
  const keys = Object.keys(groups).sort((a, b) => +a - +b);
  const series = [
    ...keys.map((k, i) => ({
      name: `组${k}`,
      type: "line" as const,
      data: tf(groups[k]),
      showSymbol: false,
      lineStyle: { width: 1.2 },
      color: GROUP_COLORS[i % GROUP_COLORS.length],
    })),
    ...([
      ["多空", ls, pal.ink],
      ["多头", long, pal.up],
      ["空头", short, pal.down],
    ] as const)
      .filter(([, d]) => d)
      .map(([name, data, color]) => ({
        name,
        type: "line" as const,
        data: tf(data as Num[]),
        showSymbol: false,
        color,
        lineStyle: { width: 2.2, type: name === "多空" ? ("solid" as const) : ("dashed" as const) },
      })),
  ];
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
          空头默认隐藏，点击图例可显示
        </Typography.Text>
      </Space>
      <Chart
        height={380}
        option={{
          tooltip: { trigger: "axis", valueFormatter: (v) => pctTip(toRet(v)) },
          legend: { type: "scroll", top: 0, selected: { 空头: false } },
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

export function IcHistChart({ block }: { block: IcBlock }) {
  const h = block.hist;
  if (!h || !h.density.length) return <Empty description="无 IC 数据" />;
  const centers = h.edges.slice(0, -1).map((e, i) => ((e + h.edges[i + 1]) / 2).toFixed(3));
  return (
    <Chart
      option={{
        tooltip: { trigger: "axis", valueFormatter: numTip },
        legend: { top: 0, data: ["密度", "正态拟合"] },
        grid: { left: 48, right: 16, top: 36, bottom: 30 },
        xAxis: { type: "category", data: centers },
        yAxis: { type: "value" },
        series: [
          { name: "密度", type: "bar", data: h.density, color: "#60a5fa", barCategoryGap: "5%" },
          { name: "正态拟合", type: "line", data: h.normal, showSymbol: false, smooth: true, color: "#10b981" },
        ],
      }}
    />
  );
}

export function AcfChart({ block }: { block: IcBlock }) {
  const pal = usePalette();
  const a = block.acf;
  if (!a || !a.acf.length) return <Empty description="无 IC 数据" />;
  const lags = a.acf.map((_, i) => String(i));
  const ci = a.ci ?? 0;
  return (
    <Chart
      option={{
        tooltip: { trigger: "axis", valueFormatter: numTip },
        legend: { top: 0, data: ["自相关系数", "95% 置信区间"] },
        grid: { left: 48, right: 16, top: 36, bottom: 30 },
        xAxis: { type: "category", data: lags, name: "滞后" },
        yAxis: { type: "value", min: -1, max: 1 },
        series: [
          { name: "自相关系数", type: "line", data: a.acf, color: "#3b82f6" },
          {
            name: "95% 置信区间",
            type: "line",
            data: lags.map(() => ci),
            showSymbol: false,
            lineStyle: { type: "dashed" },
            color: pal.muted,
          },
          {
            name: "95% 置信区间",
            type: "line",
            data: lags.map(() => -ci),
            showSymbol: false,
            lineStyle: { type: "dashed" },
            color: pal.muted,
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
  matrix,
  threshold,
}: {
  factors: string[];
  matrix: Num[][];
  threshold: number;
}) {
  const pal = usePalette();
  const screens = Grid.useBreakpoint();
  const compact = screens.md === false;
  const data = matrix.flatMap((row, i) => row.map((v, j) => [j, i, v]));
  const cell = compact ? 44 : 56;
  const longest = Math.max(...factors.map((f, i) => `${factorTag(i)}  ${f}`.length));
  const labelWidth = Math.min(compact ? 120 : 300, longest * 7 + 8);
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
          data: factors.map((f, i) => `${factorTag(i)}  ${f}`),
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
