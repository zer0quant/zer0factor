import { useState } from "react";
import { Space, Table, Tag, Typography, theme } from "antd";
import { useQuery } from "@tanstack/react-query";
import { fetchLatest } from "../api";
import { fmtDate, isNum, num, pct, signColor, withSign } from "../format";
import type { Detail, GroupRow, Num, RunSummary } from "../types";
import { returnTypeLabel } from "../vocab";
import { UniverseTag } from "./UniverseTag";

/** Read-only evaluation parameters as compact inline tags. */
export function ParamsSummary({ run }: { run: RunSummary }) {
  const items: [string, React.ReactNode][] = [
    ["区间", `${fmtDate(run.start_date)} → ${run.end_date ? fmtDate(run.end_date) : "最新"}`],
    ["股票池", <UniverseTag code={run.universe} plain />],
    ["分组", run.quantiles != null ? `${run.quantiles} 组` : "—"],
    ["持有期", run.periods.join(" / ")],
    ["成交价", returnTypeLabel(run.return_type)],
    ["交易成本", run.transaction_cost_bps != null ? `单边 ${run.transaction_cost_bps} bps` : "—"],
  ];
  return (
    <Space size={[12, 4]} wrap>
      {items.map(([k, v]) => (
        <span key={k} style={{ whiteSpace: "nowrap" }}>
          <Typography.Text type="secondary">{k} </Typography.Text>
          <span className="num">{v}</span>
        </span>
      ))}
    </Space>
  );
}

const cell = (text: string, v: Num | undefined, color = false) => (
  <span className="num" style={{ color: color ? signColor(v ?? null) : undefined }}>
    {color ? withSign(text, v) : text}
  </span>
);

const pctText = (v: Num | undefined) => pct(v ?? null);
const rateText = (v: Num | undefined) => (isNum(v) ? `${v.toFixed(1)}%` : "—");
const intText = (v: Num | undefined) => (isNum(v) ? Math.round(v).toLocaleString("en-US") : "—");

type Item = { label: string; text: string; v?: Num; colored?: boolean; tip?: string };

export function MetricCards({ detail }: { detail: Detail }) {
  const { token } = theme.useToken();
  const s = detail.summary as Record<string, Num>;
  const dir = detail.direction;

  const headline: (Item & { sub: string })[] = [
    {
      label: "ICIR（方向调整）",
      text: num(s["adjusted_ICIR"], 3),
      v: s["adjusted_ICIR"],
      colored: true,
      sub: `t = ${num(s["adjusted_t-stat"], 2)} · 胜率 ${rateText(s["directional_IC>0 %"])}`,
    },
    {
      label: "多头年化",
      text: pctText(s["long_ann_ret"]),
      v: s["long_ann_ret"],
      colored: true,
      sub: `最大回撤 ${pctText(s["long_max_dd"])}`,
    },
    {
      label: "多头夏普",
      text: num(s["long_sharpe"], 2),
      v: s["long_sharpe"],
      colored: true,
      sub: `Calmar ${num(s["long_calmar"], 2)}`,
    },
    {
      label: "多头超额年化",
      text: pctText(s["long_exc_ann_ret"]),
      v: s["long_exc_ann_ret"],
      colored: true,
      sub: `超额夏普 ${num(s["long_exc_sharpe"], 2)}`,
    },
  ];

  const groups: [string, Item[]][] = [
    [
      "IC",
      [
        { label: "Rank IC 均值（原始）", text: num(s["IC Mean"]), v: s["IC Mean"], colored: true },
        { label: "IC 标准差", text: num(s["IC Std"]) },
        { label: "t 值（方向调整）", text: num(s["adjusted_t-stat"], 2), tip: "HAC t 统计量" },
        { label: "IC 胜率（日）", text: rateText(s["directional_IC>0 %"]) },
      ],
    ],
    [
      "多头",
      [
        { label: "年化", text: pctText(s["long_ann_ret"]), v: s["long_ann_ret"], colored: true },
        { label: "最大回撤", text: pctText(s["long_max_dd"]) },
        { label: "夏普", text: num(s["long_sharpe"], 2), v: s["long_sharpe"], colored: true },
        { label: "单调性", text: num(s["monotonicity"], 2) },
      ],
    ],
    [
      "空头",
      [
        { label: "空头年化", text: pctText(s["short_ann_ret"]), v: s["short_ann_ret"], colored: true },
        { label: "空头最大回撤", text: pctText(s["short_max_dd"]) },
      ],
    ],
    [
      "换手 / 样本",
      [
        { label: "多头日均换手", text: pct(s["turnover_daily_long"] ?? null, 1) },
        { label: "空头日均换手", text: pct(s["turnover_daily_short"] ?? null, 1) },
        { label: "样本数", text: intText(s["sample_count"]) },
      ],
    ],
  ];

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <div className="zf-kpis">
        {headline.map((h) => (
          <div key={h.label} className="zf-kpi" style={{ borderColor: token.colorBorderSecondary }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {h.label}
            </Typography.Text>
            <div style={{ fontSize: 24, fontWeight: 600, lineHeight: 1.3 }}>
              {cell(h.text, h.v ?? null, !!h.colored)}
            </div>
            <Typography.Text type="secondary" className="num" style={{ fontSize: 12 }}>
              {h.sub}
            </Typography.Text>
          </div>
        ))}
      </div>
      <div className="zf-metric-groups">
        {groups.map(([title, items]) => (
          <div key={title}>
            <Typography.Text strong style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
              {title}
            </Typography.Text>
            {items.map((it) => (
              <div key={it.label} className="zf-metric-row" title={it.tip}>
                <Typography.Text type="secondary">{it.label}</Typography.Text>
                {cell(it.text, it.v ?? null, !!it.colored)}
              </div>
            ))}
          </div>
        ))}
      </div>
      {dir === -1 && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          该因子方向为负（IC 均值 &lt; 0）：多头取低分组，ICIR / t 值 / 胜率已按方向调整。
        </Typography.Text>
      )}
    </Space>
  );
}

/** Inline bar behind a percentage: share of the largest |value| in the column. */
function barCell(v: Num, max: number) {
  const w = isNum(v) && max > 0 ? (Math.abs(v) / max) * 100 : 0;
  return (
    <div className="zf-databar">
      <span
        className="zf-databar-fill"
        style={{
          width: `${w}%`,
          background: isNum(v) && v < 0 ? "var(--zf-down)" : "var(--zf-up)",
        }}
      />
      {cell(pct(v), v, true)}
    </div>
  );
}

export function GroupTable({
  rows,
  longGroup,
  shortGroup,
}: {
  rows: GroupRow[];
  longGroup?: string | null;
  shortGroup?: string | null;
}) {
  const p = (v: Num) => cell(pct(v), v, true);
  const groupRows = rows.filter((r) => r.group !== "多空");
  const maxAbs = (k: "ann_ret" | "exc_ann_ret") =>
    Math.max(0, ...groupRows.map((r) => r[k]).filter(isNum).map((v) => Math.abs(v)));
  const maxRet = maxAbs("ann_ret");
  const maxExc = maxAbs("exc_ann_ret");
  return (
    <Table<GroupRow>
      rowKey="group"
      size="small"
      pagination={false}
      dataSource={rows}
      scroll={{ x: 720 }}
      rowClassName={(r) => (r.group === "多空" ? "zf-row-total" : "")}
      columns={[
        {
          title: "分组",
          dataIndex: "group",
          width: 120,
          render: (g: string) =>
            g === "多空" ? (
              <b>多空</b>
            ) : (
              <span>
                组{g}
                {g === longGroup && (
                  <Tag color="red" bordered={false} style={{ marginInlineStart: 6 }}>
                    多头
                  </Tag>
                )}
                {g === shortGroup && (
                  <Tag color="green" bordered={false} style={{ marginInlineStart: 6 }}>
                    空头
                  </Tag>
                )}
              </span>
            ),
        },
        {
          title: "年化收益",
          dataIndex: "ann_ret",
          align: "right",
          render: (v: Num, r) => (r.group === "多空" ? p(v) : barCell(v, maxRet)),
        },
        {
          title: "超额年化",
          dataIndex: "exc_ann_ret",
          align: "right",
          render: (v: Num, r) => (r.group === "多空" ? p(v) : barCell(v, maxExc)),
        },
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
        // The backend has no stock-name source yet: drop the column while every name is empty.
        ...((q.data?.items ?? []).some((it) => it.name)
          ? [{ title: "名称", dataIndex: "name", render: (v: string | null) => v ?? "—" }]
          : []),
        { title: "因子值", dataIndex: "value", align: "right", render: (v: Num) => <span className="num">{num(v)}</span> },
        { title: "所在分组", dataIndex: "quantile", align: "right" },
      ]}
    />
  );
}
