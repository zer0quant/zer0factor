import { Alert, Card, Empty, List, Skeleton, Space, Table, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchCompare, fetchCorrelation } from "../api";
import { fmtDate, isNum, num, pct, signColor } from "../format";
import type { BoardRow, Num } from "../types";
import { CompareCurves, CorrHeatmap } from "../components/charts";

type Metric = {
  key: keyof BoardRow;
  label: string;
  fmt: (v: Num) => string;
  better: "high" | "low";
  colored?: boolean;
};

// ls_max_dd is stored negative, so "higher" (closer to 0) is better.
const METRICS: Metric[] = [
  { key: "ic_adj", label: "方向调整 IC", fmt: (v) => num(v, 4), better: "high" },
  { key: "icir", label: "ICIR", fmt: (v) => num(v, 3), better: "high" },
  { key: "t_stat", label: "t 值", fmt: (v) => num(v, 2), better: "high" },
  { key: "ic_win_rate", label: "IC 胜率", fmt: (v) => (isNum(v) ? `${v.toFixed(1)}%` : "—"), better: "high" },
  { key: "ls_ann_ret", label: "多空年化", fmt: (v) => pct(v), better: "high", colored: true },
  { key: "ls_max_dd", label: "多空最大回撤", fmt: (v) => pct(v), better: "high" },
  { key: "ls_sharpe", label: "多空夏普", fmt: (v) => num(v, 2), better: "high", colored: true },
  { key: "long_exc_ann_ret", label: "多头超额年化", fmt: (v) => pct(v), better: "high", colored: true },
  { key: "monotonicity", label: "单调性", fmt: (v) => num(v, 2), better: "high" },
  { key: "turnover_long", label: "多头日均换手", fmt: (v) => pct(v, 1), better: "low" },
];

function bestIndex(values: Num[], better: "high" | "low"): number {
  let best = -1;
  values.forEach((v, i) => {
    if (!isNum(v)) return;
    const b = values[best];
    if (best < 0 || (better === "high" ? v > (b as number) : v < (b as number))) best = i;
  });
  return best;
}

export default function Compare() {
  const [params] = useSearchParams();
  const fs = (params.get("f") ?? "").split(",").filter(Boolean);
  const valid = fs.length >= 2 && fs.length <= 8;

  const cmp = useQuery({ queryKey: ["compare", fs], queryFn: () => fetchCompare(fs), enabled: valid });
  const corr = useQuery({
    queryKey: ["corr", fs],
    queryFn: () => fetchCorrelation(fs),
    enabled: valid,
    staleTime: Infinity,
  });

  if (!valid) {
    return (
      <Card>
        <Empty description={<>请回 <Link to="/">因子看板</Link> 勾选 2–8 个因子后点击“开始对比”</>} />
      </Card>
    );
  }

  const data = cmp.data;
  const tableRows = METRICS.map((m) => {
    const values = (data?.rows ?? []).map((r) => r[m.key] as Num);
    return { metric: m, values, best: bestIndex(values, m.better) };
  });

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      {cmp.error && <Alert type="error" message={`加载失败：${(cmp.error as Error).message}`} />}
      {data && data.inconsistent.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={`口径不一致：${data.inconsistent.join("、")} 没有标准设定的评估，使用的是其最新一次评估，数字与其他因子不可直接比较。`}
        />
      )}
      {data && data.unevaluated.length > 0 && (
        <Alert type="info" showIcon message={`${data.unevaluated.join("、")} 还没有任何评估结果。`} />
      )}

      <Card size="small" title="指标对比">
        {cmp.isLoading ? (
          <Skeleton active />
        ) : (
          <Table
            rowKey={(r) => r.metric.key}
            size="small"
            pagination={false}
            scroll={{ x: 200 + fs.length * 170 }}
            dataSource={tableRows}
            columns={[
              { title: "指标", key: "metric", fixed: "left", width: 130, render: (_, r) => r.metric.label },
              ...(data?.factors ?? fs).map((f, i) => ({
                title: <Link to={`/factor/${encodeURIComponent(f)}`}>{f}</Link>,
                key: f,
                align: "right" as const,
                render: (_: unknown, r: (typeof tableRows)[number]) => {
                  const v = r.values[i];
                  return (
                    <span
                      style={{
                        color: r.metric.colored ? signColor(v) : undefined,
                        fontWeight: r.best === i ? 700 : 400,
                        background: r.best === i ? "#fef9c3" : undefined,
                        padding: "2px 6px",
                        borderRadius: 4,
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {r.metric.fmt(v)}
                    </span>
                  );
                },
              })),
            ]}
          />
        )}
      </Card>

      <Card size="small" title="多空累计收益（扣费后）">
        {cmp.isLoading ? (
          <Skeleton active />
        ) : data && Object.keys(data.curves.series).length ? (
          <CompareCurves dates={data.curves.dates} series={data.curves.series} />
        ) : (
          <Empty description="无可用的收益序列" />
        )}
      </Card>

      <Card
        size="small"
        title="因子相关性（截面 Spearman）"
        extra={
          corr.data && (
            <Typography.Text type="secondary">
              {fmtDate(corr.data.start)} → {fmtDate(corr.data.end)} 抽样 {corr.data.dates_used} 个交易日 ·
              univ_trade_base 成分股
            </Typography.Text>
          )
        }
      >
        {corr.isLoading ? (
          <Skeleton active />
        ) : corr.error ? (
          <Alert type="error" message={(corr.error as Error).message} />
        ) : corr.data ? (
          <>
            <CorrHeatmap
              factors={corr.data.factors}
              matrix={corr.data.matrix}
              threshold={corr.data.threshold}
            />
            <List
              size="small"
              header={<b>疑似重复（|ρ| ≥ {corr.data.threshold}）</b>}
              dataSource={corr.data.pairs_over_threshold}
              locale={{ emptyText: "没有高度相关的因子对" }}
              renderItem={(p) => (
                <List.Item extra={<Typography.Text strong>ρ = {p.rho.toFixed(3)}</Typography.Text>}>
                  {p.a} ↔ {p.b}
                </List.Item>
              )}
            />
          </>
        ) : null}
      </Card>
    </Space>
  );
}
