import { Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchFactors } from "../api";
import { comparePrep, parseFactorName, prepLabel, windowLabel } from "../factorName";
import { num } from "../format";
import type { BoardRow } from "../types";

function Chip({ row, label, current }: { row: BoardRow; label: string; current: boolean }) {
  const [params] = useSearchParams();
  // Keep the chosen period when hopping between siblings; the run may differ, so drop it.
  const period = params.get("period");
  const to = `/factor/${encodeURIComponent(row.name)}${period ? `?period=${encodeURIComponent(period)}` : ""}`;
  return (
    <Link
      to={to}
      className={`zf-sib${current ? " zf-sib-cur" : ""}`}
      title={row.name}
      aria-current={current ? "page" : undefined}
    >
      <span>{label}</span>
      <small className="num">{row.evaluated ? `ICIR ${num(row.icir, 2)}` : "未评估"}</small>
    </Link>
  );
}

/** Same-family navigation: other windows (same preprocessing) and other preprocessings (same window). */
export function Siblings({ name }: { name: string }) {
  const { data } = useQuery({ queryKey: ["factors"], queryFn: fetchFactors });
  if (!data) return null;
  const me = parseFactorName(name);
  const parsed = data.map((r) => ({ r, p: parseFactorName(r.name) }));
  const windows = parsed
    .filter(({ p }) => p.base === me.base && p.prep === me.prep)
    .sort((a, b) => (a.p.window ?? Infinity) - (b.p.window ?? Infinity));
  const preps = parsed
    .filter(({ p }) => p.base === me.base && p.window === me.window)
    .sort((a, b) => comparePrep(a.p.prep, b.p.prep));
  const rows: [string, typeof windows, (x: (typeof windows)[number]) => string][] = [
    ["窗口", windows, (x) => windowLabel(x.p.window)],
    ["预处理", preps, (x) => prepLabel(x.p.prep)],
  ];
  const shown = rows.filter(([, xs]) => xs.length > 1);
  if (!shown.length) return null;
  return (
    <Space direction="vertical" size={6} style={{ width: "100%" }}>
      {shown.map(([label, xs, fmt]) => (
        <div key={label} className="zf-sibs">
          <Typography.Text type="secondary" style={{ width: 48, flex: "none" }}>
            {label}
          </Typography.Text>
          {xs.map((x) => (
            <Chip key={x.r.name} row={x.r} label={fmt(x)} current={x.r.name === name} />
          ))}
        </div>
      ))}
    </Space>
  );
}
