import type { Num } from "../types";

/** Tiny inline line chart of a cumulative return, with a dashed zero line. */
export function Sparkline({
  values,
  width = 96,
  height = 24,
  label,
}: {
  values: Num[];
  width?: number;
  height?: number;
  label?: string;
}) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is [number, number] => typeof p[1] === "number");
  if (pts.length < 2) return null;
  const ys = pts.map(([, v]) => v);
  const lo = Math.min(0, ...ys);
  const hi = Math.max(0, ...ys);
  const span = hi - lo || 1;
  const n = values.length - 1 || 1;
  const pad = 2;
  const x = (i: number) => pad + (i / n) * (width - 2 * pad);
  const y = (v: number) => pad + (1 - (v - lo) / span) * (height - 2 * pad);
  const last = ys[ys.length - 1];
  const color = last >= 0 ? "var(--zf-up)" : "var(--zf-down)";
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label ?? `累计 ${(last * 100).toFixed(1)}%`}
      style={{ display: "block" }}
    >
      <line x1={pad} x2={width - pad} y1={y(0)} y2={y(0)} stroke="var(--zf-muted)" strokeDasharray="2 2" strokeWidth={0.6} />
      <polyline
        points={pts.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.3}
        strokeLinejoin="round"
      />
    </svg>
  );
}
