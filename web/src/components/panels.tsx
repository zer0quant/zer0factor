import { useState } from "react";
import { Descriptions, Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { fetchLatest } from "../api";
import { fmtDate, num, pct, signColor } from "../format";
import type { Detail, GroupRow, Num, RunSummary } from "../types";

/** Read-only evaluation parameters. v2 replaces this with an editable panel. */
export function ParamsPanel({ run }: { run: RunSummary }) {
  return (
    <Descriptions
      column={1}
      size="small"
      labelStyle={{ width: 96 }}
      items={[
        { label: "评估 run", children: run.run_id },
        {
          label: "区间",
          children: `${fmtDate(run.start_date)} → ${run.end_date ? fmtDate(run.end_date) : "最新"}`,
        },
        { label: "股票池", children: run.universe ?? "全部" },
        { label: "分组数", children: run.quantiles ?? "—" },
        { label: "持有期", children: run.periods.join(" / ") },
        { label: "收益口径", children: run.return_type ?? "—" },
        {
          label: "交易成本",
          children: run.transaction_cost_bps != null ? `单边 ${run.transaction_cost_bps} bps` : "—",
        },
        {
          label: "标准设定",
          children: run.standard ? <Tag color="green">是</Tag> : <Tag>否</Tag>,
        },
      ]}
    />
  );
}

const cell = (text: string, v: Num | undefined, color = false) => (
  <span style={{ color: color ? signColor(v ?? null) : undefined, fontVariantNumeric: "tabular-nums" }}>
    {text}
  </span>
);

export function MetricCards({ detail }: { detail: Detail }) {
  const s = detail.summary as Record<string, Num>;
  const dir = detail.direction;
  const items: [string, string, Num, boolean][] = [
    ["Rank IC 均值（原始）", num(s["IC Mean"]), s["IC Mean"], true],
    ["IC 标准差", num(s["IC Std"]), s["IC Std"], false],
    ["ICIR（方向调整）", num(s["adjusted_ICIR"], 3), s["adjusted_ICIR"], true],
    ["t 值（方向调整）", num(s["adjusted_t-stat"], 2), s["adjusted_t-stat"], true],
    ["IC 胜率", s["directional_IC>0 %"] != null ? `${(s["directional_IC>0 %"] as number).toFixed(1)}%` : "—", null, false],
    ["单调性", num(s["monotonicity"], 2), s["monotonicity"], false],
    ["多空年化", pct(s["ls_ann_ret"]), s["ls_ann_ret"], true],
    ["多空最大回撤", pct(s["ls_max_dd"]), null, false],
    ["多空夏普", num(s["ls_sharpe"], 2), s["ls_sharpe"], true],
    ["多头年化", pct(s["long_ann_ret"]), s["long_ann_ret"], true],
    ["多头超额年化", pct(s["long_exc_ann_ret"]), s["long_exc_ann_ret"], true],
    ["多头最大回撤", pct(s["long_max_dd"]), null, false],
    ["空头年化", pct(s["short_ann_ret"]), s["short_ann_ret"], true],
    ["多头日均换手", pct(s["turnover_daily_long"], 1), null, false],
    ["空头日均换手", pct(s["turnover_daily_short"], 1), null, false],
    ["样本数", s["sample_count"] != null ? String(s["sample_count"]) : "—", null, false],
  ];
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
        gap: 10,
      }}
    >
      {items.map(([label, text, v, colored]) => (
        <div
          key={label}
          style={{
            border: "1px solid #f0f0f0",
            borderRadius: 8,
            padding: "8px 12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 8,
          }}
        >
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {label}
          </Typography.Text>
          <span style={{ fontSize: 16, fontWeight: 600 }}>{cell(text, v, colored)}</span>
        </div>
      ))}
      {dir === -1 && (
        <Typography.Text type="secondary" style={{ gridColumn: "1 / -1", fontSize: 12 }}>
          该因子方向为负（IC 均值 &lt; 0）：多头取低分组，ICIR / t 值 / 胜率已按方向调整。
        </Typography.Text>
      )}
    </div>
  );
}

export function GroupTable({ rows }: { rows: GroupRow[] }) {
  const p = (v: Num) => cell(pct(v), v, true);
  return (
    <Table<GroupRow>
      rowKey="group"
      size="small"
      pagination={false}
      dataSource={rows}
      scroll={{ x: 640 }}
      columns={[
        { title: "分组", dataIndex: "group", render: (g: string) => (g === "多空" ? g : `组${g}`) },
        { title: "年化收益", dataIndex: "ann_ret", align: "right", render: p },
        { title: "超额年化", dataIndex: "exc_ann_ret", align: "right", render: p },
        { title: "最大回撤", dataIndex: "max_dd", align: "right", render: (v: Num) => cell(pct(v), v) },
        { title: "年化波动", dataIndex: "ann_vol", align: "right", render: (v: Num) => cell(pct(v), v) },
        { title: "夏普", dataIndex: "sharpe", align: "right", render: (v: Num) => cell(num(v, 2), v, true) },
      ]}
    />
  );
}

export function LatestValues({ name, runId }: { name: string; runId: string }) {
  const [page, setPage] = useState(1);
  const size = 10;
  const q = useQuery({
    queryKey: ["latest", name, runId, page],
    queryFn: () => fetchLatest(name, runId, page, size),
  });
  return (
    <Table
      rowKey="ts_code"
      size="small"
      loading={q.isLoading}
      dataSource={q.data?.items ?? []}
      title={() => (q.data?.date ? `日期：${q.data.date}（按因子值从高到低）` : undefined)}
      pagination={{
        current: page,
        pageSize: size,
        total: q.data?.total ?? 0,
        onChange: setPage,
        showSizeChanger: false,
      }}
      columns={[
        { title: "股票代码", dataIndex: "ts_code" },
        { title: "名称", dataIndex: "name", render: (v: string | null) => v ?? "—" },
        { title: "因子值", dataIndex: "value", align: "right", render: (v: Num) => num(v) },
        { title: "所在分组", dataIndex: "quantile", align: "right" },
      ]}
    />
  );
}
