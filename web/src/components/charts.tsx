import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { Empty } from "antd";
import { GREEN, RED } from "../format";
import type { IcBlock, Num } from "../types";

const GROUP_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];
const pctAxis = { axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } };
const pctTip = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(2)}%` : "—");
const numTip = (v: unknown) => (typeof v === "number" ? v.toFixed(4) : "—");

function Chart({ option, height = 300 }: { option: EChartsOption; height?: number }) {
  return <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />;
}

const barColor = (v: Num) => ((v ?? 0) >= 0 ? RED : GREEN);

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
  const keys = Object.keys(groups).sort((a, b) => +a - +b);
  const series = [
    ...keys.map((k, i) => ({
      name: `组${k}`,
      type: "line" as const,
      data: groups[k],
      showSymbol: false,
      lineStyle: { width: 1.2 },
      color: GROUP_COLORS[i % GROUP_COLORS.length],
    })),
    ...([
      ["多空", ls, "#111827"],
      ["多头", long, RED],
      ["空头", short, GREEN],
    ] as const)
      .filter(([, d]) => d)
      .map(([name, data, color]) => ({
        name,
        type: "line" as const,
        data: data as Num[],
        showSymbol: false,
        color,
        lineStyle: { width: 2.2, type: name === "多空" ? ("solid" as const) : ("dashed" as const) },
      })),
  ];
  return (
    <Chart
      height={380}
      option={{
        tooltip: { trigger: "axis", valueFormatter: pctTip },
        legend: { type: "scroll", top: 0 },
        grid: { left: 56, right: 24, top: 40, bottom: 56 },
        xAxis: { type: "category", data: dates, boundaryGap: false },
        yAxis: { type: "value", scale: true, ...pctAxis },
        dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }],
        series,
      }}
    />
  );
}

export function IcSeriesChart({ block, label }: { block: IcBlock; label: string }) {
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
            data: s.values.map((v) => ({ value: v, itemStyle: { color: barColor(v) } })),
          },
          {
            name: `累计 ${label}`,
            type: "line",
            yAxisIndex: 1,
            data: s.cumulative,
            showSymbol: false,
            color: "#2563eb",
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
            color: "#9ca3af",
          },
          {
            name: "95% 置信区间",
            type: "line",
            data: lags.map(() => -ci),
            showSymbol: false,
            lineStyle: { type: "dashed" },
            color: "#9ca3af",
          },
        ],
      }}
    />
  );
}

export function DecayChart({ block }: { block: IcBlock }) {
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
            data: d.map((v) => ({ value: v, itemStyle: { color: barColor(v) } })),
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
        legend: { type: "scroll", top: 0 },
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

export function CorrHeatmap({
  factors,
  matrix,
  threshold,
}: {
  factors: string[];
  matrix: Num[][];
  threshold: number;
}) {
  const data = matrix.flatMap((row, i) => row.map((v, j) => [j, i, v]));
  const size = Math.max(320, factors.length * 64 + 160);
  return (
    <Chart
      height={size}
      option={{
        tooltip: {
          formatter: (p: unknown) => {
            const [j, i, v] = (p as { value: [number, number, Num] }).value;
            return `${factors[i]}<br/>${factors[j]}<br/>ρ = ${typeof v === "number" ? v.toFixed(3) : "—"}`;
          },
        },
        grid: { left: 200, right: 40, top: 20, bottom: 140 },
        xAxis: { type: "category", data: factors, axisLabel: { rotate: 35, interval: 0 } },
        yAxis: { type: "category", data: factors, inverse: true, axisLabel: { interval: 0 } },
        visualMap: {
          min: -1,
          max: 1,
          calculable: true,
          orient: "horizontal",
          left: "center",
          bottom: 0,
          inRange: { color: [GREEN, "#f8fafc", RED] },
        },
        series: [
          {
            type: "heatmap",
            data: data.map(([x, y, v]) => ({
              value: [x, y, v],
              itemStyle:
                x !== y && typeof v === "number" && Math.abs(v) >= threshold
                  ? { borderColor: "#111827", borderWidth: 2 }
                  : undefined,
            })),
            label: {
              show: true,
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
