import { Alert, Button, Card, Empty, Grid, List, Select, Skeleton, Space, Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { fetchCompare, fetchCorrelation, fetchFactors } from "../api";
import { MAX_COMPARE, compareHref, useBasket } from "../compareBasket";
import { shortName } from "../factorName";
import { FactorChips } from "../components/FactorName";
import { boardHref } from "../boardState";
import { fmtDate, isNum, num, pct, signColor, withSign } from "../format";
import type { BoardRow, Num } from "../types";
import { CompareCurves, CorrHeatmap, factorTag } from "../components/charts";
import { ErrorState, SlowLoading } from "../components/states";

type Metric = {
  key: keyof BoardRow;
  label: string;
  fmt: (v: Num) => string;
  better: "high" | "low";
  colored?: boolean;
};

// long_max_dd is stored negative, so "higher" (closer to 0) is better.
const METRICS: Metric[] = [
  { key: "ic_adj", label: "方向调整 IC", fmt: (v) => num(v, 4), better: "high" },
  { key: "icir", label: "ICIR", fmt: (v) => num(v, 3), better: "high" },
  { key: "t_stat", label: "t 值", fmt: (v) => num(v, 2), better: "high" },
  { key: "ic_win_rate", label: "IC 胜率", fmt: (v) => (isNum(v) ? `${v.toFixed(1)}%` : "—"), better: "high" },
  { key: "long_ann_ret", label: "多头年化", fmt: (v) => pct(v), better: "high", colored: true },
  { key: "long_max_dd", label: "多头最大回撤", fmt: (v) => pct(v), better: "high" },
  { key: "long_sharpe", label: "多头夏普", fmt: (v) => num(v, 2), better: "high", colored: true },
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
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const basket = useBasket();
  const fs = (params.get("f") ?? "").split(",").filter(Boolean);
  const valid = fs.length >= 2 && fs.length <= MAX_COMPARE;
  const all = useQuery({ queryKey: ["factors"], queryFn: fetchFactors });
  const setFactors = (names: string[]) => {
    const next = new URLSearchParams(params);
    if (names.length) next.set("f", names.join(","));
    else next.delete("f");
    setParams(next, { replace: true });
  };
  const picker = (
    <Card size="small" title="对比因子">
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Select
          mode="multiple"
          showSearch
          allowClear
          maxCount={MAX_COMPARE}
          placeholder="搜索并添加因子（2–8 个）"
          style={{ width: "100%" }}
          value={fs}
          onChange={setFactors}
          loading={all.isLoading}
          optionFilterProp="search"
          options={(all.data ?? []).map((r) => ({
            value: r.name,
            search: `${r.name} ${shortName(r.name)}`,
            label: (
              <span title={r.name}>
                {shortName(r.name)}
                {!r.evaluated && <Typography.Text type="secondary">（未评估）</Typography.Text>}
              </span>
            ),
          }))}
          tagRender={({ value, closable, onClose }) => {
            const i = fs.indexOf(String(value));
            return (
              <Tag closable={closable} onClose={onClose} style={{ marginBlock: 2 }} title={String(value)}>
                {i >= 0 ? `${factorTag(i)} ` : ""}
                {shortName(String(value))}
              </Tag>
            );
          }}
        />
        {basket.length >= 2 && basket.join(",") !== fs.join(",") && (
          <Button size="small" onClick={() => navigate(compareHref(basket), { replace: true })}>
            载入对比篮（{basket.length} 个）
          </Button>
        )}
      </Space>
    </Card>
  );
  const screens = Grid.useBreakpoint();
  const compact = screens.md === false;

  const cmp = useQuery({ queryKey: ["compare", fs], queryFn: () => fetchCompare(fs), enabled: valid });
  const corr = useQuery({
    queryKey: ["corr", fs],
    queryFn: () => fetchCorrelation(fs),
    enabled: valid,
    staleTime: Infinity,
  });

  if (!valid) {
    return (
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {picker}
        <Card>
          <Empty
            description={
              <>
                在上方添加 2–8 个因子，或回 <Link to={boardHref()}>因子看板</Link> 勾选后点击“开始对比”
              </>
            }
          />
        </Card>
      </Space>
    );
  }

  const data = cmp.data;
  const tableRows = METRICS.map((m) => {
    const values = (data?.rows ?? []).map((r) => r[m.key] as Num);
    return { metric: m, values, best: bestIndex(values, m.better) };
  });

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      {picker}
      {cmp.error && <ErrorState error={cmp.error} title="对比数据加载失败" onRetry={() => cmp.refetch()} />}
      {data && data.inconsistent.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={`口径不一致：${data.inconsistent.join("、")} 没有统一口径的评估，使用的是其最新一次评估，数字与其他因子不可直接比较。`}
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
                title: (
                  <div className="zf-cmp-head">
                    <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
                      {factorTag(i)}
                    </Typography.Text>
                    <FactorChips name={f} />
                  </div>
                ),
                width: 170,
                key: f,
                align: "right" as const,
                render: (_: unknown, r: (typeof tableRows)[number]) => {
                  const v = r.values[i];
                  return (
                    <span
                      className="num"
                      style={{
                        color: r.metric.colored ? signColor(v) : undefined,
                        fontWeight: r.best === i ? 700 : 400,
                        background: r.best === i ? "var(--zf-best)" : undefined,
                        padding: "2px 6px",
                        borderRadius: 4,
                      }}
                    >
                      {r.best === i && (
                        <span aria-hidden style={{ marginInlineEnd: 2 }}>
                          ★
                        </span>
                      )}
                      {r.metric.colored ? withSign(r.metric.fmt(v), v) : r.metric.fmt(v)}
                      {r.best === i && <span className="zf-sr-only">（最优）</span>}
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
          <>
            {data.missing_curve.length > 0 && (
              <Alert
                type="info"
                style={{ marginBottom: 8 }}
                message={`${data.missing_curve.join("、")} 的收益序列尚未生成：打开其详情页一次，或运行 web-warm 预热后再刷新。`}
              />
            )}
            <CompareCurves
              dates={data.curves.dates}
              series={Object.fromEntries(
                Object.entries(data.curves.series).map(([f, d]) => {
                  const i = data.factors.indexOf(f);
                  return [`${i >= 0 ? `${factorTag(i)} ` : ""}${shortName(f)}`, d];
                }),
              )}
            />
          </>
        ) : (
          <Empty description="无可用的收益序列" />
        )}
      </Card>

      <Card
        size="small"
        title="因子相关性（截面 Spearman）"
      >
        {corr.isLoading ? (
          <SlowLoading
            tip="正在计算截面相关性…"
            hint="需要读取各因子在抽样交易日的截面数据，首次计算可能需要数十秒；结果会缓存。"
          />
        ) : corr.error ? (
          <ErrorState error={corr.error} title="相关性计算失败" onRetry={() => corr.refetch()} />
        ) : corr.data ? (
          <>
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
              {fmtDate(corr.data.start)} → {fmtDate(corr.data.end)} 抽样 {corr.data.dates_used} 个交易日 ·
              univ_trade_base 成分股{compact ? "" : " · 横轴编号对应纵轴因子名，悬停查看完整信息"}
            </Typography.Text>
            <CorrHeatmap
              factors={corr.data.factors}
              labels={corr.data.factors.map(shortName)}
              matrix={corr.data.matrix}
              threshold={corr.data.threshold}
            />
            <List
              size="small"
              header={<b>疑似重复（|ρ| ≥ {corr.data.threshold}）</b>}
              dataSource={corr.data.pairs_over_threshold}
              locale={{ emptyText: "没有高度相关的因子对" }}
              renderItem={(p) => {
                const ia = corr.data!.factors.indexOf(p.a);
                const ib = corr.data!.factors.indexOf(p.b);
                return (
                  <List.Item>
                    <span className="zf-pair">
                      {ia >= 0 && <Tag>{factorTag(ia)}</Tag>}
                      <FactorChips name={p.a} />
                      <Typography.Text type="secondary"> ↔ </Typography.Text>
                      {ib >= 0 && <Tag>{factorTag(ib)}</Tag>}
                      <FactorChips name={p.b} />
                    </span>
                    <Typography.Text strong className="num" style={{ flex: "none", marginInlineStart: 16 }}>
                      ρ = {p.rho.toFixed(3)}
                    </Typography.Text>
                  </List.Item>
                );
              }}
            />
          </>
        ) : null}
      </Card>
    </Space>
  );
}
