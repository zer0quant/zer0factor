import { useEffect, useState } from "react";
import { Button, Card, Col, Empty, Row, Segmented, Skeleton, Space, Switch, Tag, Typography, message } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useHotkeys } from "../hotkeys";
import { fetchDetail, fetchFactor } from "../api";
import { isNum, pct, runLabel, signColor, withSign } from "../format";
import { MAX_COMPARE, toggleInBasket, useBasket } from "../compareBasket";
import type { BaseCurves, Detail } from "../types";
import { CumulativeChart, DecayChart, GroupBars, IcSeriesChart, adjustIcBlock } from "./charts";
import { GroupTable, KeyMetrics, LatestValues, MetricCards, ParamsSummary } from "./panels";
import { ErrorState, SlowLoading } from "./states";
import { FactorChips } from "./FactorName";
import { useEvaluate } from "./EvaluateDrawer";

/** Notes about the IC decay belong under the decay chart, the rest under the group curves. */
const isDecayNote = (note: string) => note.startsWith("IC 衰减");

/**
 * Rank IC only, two charts: the IC series with its cumulative sum (is the factor stable, when
 * did it weaken?) and the IC decay (how long the signal lasts, i.e. turnover pressure). The IC
 * distribution / autocorrelation and Pearson IC were dropped: the headline numbers (IC mean,
 * std, win rate, HAC t) already summarise them.
 */
function IcCharts({ detail }: { detail: Detail }) {
  const reverse = detail.direction === -1;
  const [adjusted, setAdjusted] = useState(true);
  const adj = reverse && adjusted;
  const block = adj ? adjustIcBlock(detail.rank_ic, -1) : detail.rank_ic;
  const label = `Rank IC${adj ? "（方向调整）" : ""}`;
  const decayNotes = detail.notes.filter(isDecayNote);
  const toggle = reverse && (
    <Space size={6}>
      <Switch size="small" checked={adjusted} onChange={setAdjusted} />
      <Typography.Text style={{ fontSize: 12 }}>按方向调整（× −1）</Typography.Text>
    </Space>
  );
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={15}>
        <Card
          size="small"
          title={`${label} 序列与累计${block.monthly ? "（柱为月度均值）" : ""}`}
          extra={toggle}
          style={{ height: "100%" }}
        >
          <IcSeriesChart block={block} label={label} />
        </Card>
      </Col>
      <Col xs={24} xl={9}>
        <Card size="small" title={`${label} 衰减（因子对 k 日后的 1 日收益）`} style={{ height: "100%" }}>
          <DecayChart block={block} />
          {decayNotes.length > 0 && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {decayNotes.join("；")}
            </Typography.Text>
          )}
        </Card>
      </Col>
    </Row>
  );
}

function Results({ detail, name, runId }: { detail: Detail; name: string; runId: string }) {
  const c = detail.cumulative;
  const s = detail.summary;
  const q = (v: unknown) => (typeof v === "number" ? String(Math.round(v)) : null);
  const [barField, setBarField] = useState<"exc_ann_ret" | "ann_ret">("exc_ann_ret");
  // Bars are gross (no costs); the headline long-group numbers are net of transaction costs.
  const longGroup = q(s["long_quantile"]);
  const grossLong = detail.group_table?.find((r) => r.group === longGroup)?.[barField];
  const asNum = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const netLong = asNum(s[barField === "exc_ann_ret" ? "long_exc_ann_ret" : "long_ann_ret"]);
  const costBps = asNum(s["transaction_cost_bps"]);
  const drag = isNum(grossLong) && isNum(netLong) ? grossLong - netLong : null;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <KeyMetrics detail={detail} />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card
            size="small"
            title={
              <span>
                分组累计收益
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginInlineStart: 6 }}>
                  未扣费
                </Typography.Text>
              </span>
            }
            style={{ height: "100%" }}
          >
            {c ? (
              <>
                <CumulativeChart dates={c.dates} groups={c.groups} />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {detail.notes.filter((n) => !isDecayNote(n)).join("；")}
                </Typography.Text>
              </>
            ) : (
              <Empty description="该 run 缺少原始数据（clean_factor_data），无法绘制收益曲线" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card
            size="small"
            title={
              <span>
                分层收益
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginInlineStart: 6 }}>
                  未扣费
                </Typography.Text>
              </span>
            }
            style={{ height: "100%" }}
            extra={
              <Segmented
                size="small"
                value={barField}
                onChange={(v) => setBarField(v as "exc_ann_ret" | "ann_ret")}
                options={[
                  { value: "exc_ann_ret", label: "超额年化" },
                  { value: "ann_ret", label: "年化收益" },
                ]}
              />
            }
          >
            {detail.group_table ? (
              <>
                <GroupBars rows={detail.group_table} field={barField} height={380} />
                {longGroup && isNum(netLong) && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    多头（组{longGroup}）扣费后{barField === "exc_ann_ret" ? "超额" : "年化"}{" "}
                    <span className="num" style={{ color: signColor(netLong) }}>
                      {withSign(pct(netLong), netLong)}
                    </span>
                    {drag != null && (
                      <>
                        ，交易成本拖累约 <span className="num">{pct(drag, 1)}</span> / 年
                        {costBps != null && `（单边 ${costBps} bp × 换手）`}
                      </>
                    )}
                  </Typography.Text>
                )}
              </>
            ) : (
              <Empty description="无分组收益数据" />
            )}
          </Card>
        </Col>
      </Row>
      <IcCharts detail={detail} />
      <Card size="small" title="更多指标">
        <MetricCards detail={detail} headline={false} />
      </Card>
      {detail.group_table && (
        <Card size="small" title="分组收益明细">
          <GroupTable rows={detail.group_table} longGroup={longGroup} shortGroup={q(s["short_quantile"])} />
        </Card>
      )}
      <Card size="small" title="最新因子值">
        <LatestValues name={name} runId={runId} reverse={detail.direction === -1} />
      </Card>
    </Space>
  );
}

function CompareToggle({ name }: { name: string }) {
  const basket = useBasket();
  const inBasket = basket.includes(name);
  return (
    <Button
      size="small"
      type={inBasket ? "default" : "primary"}
      ghost={!inBasket}
      onClick={() => {
        if (!toggleInBasket(name)) message.warning(`对比篮最多 ${MAX_COMPARE} 个因子`);
      }}
    >
      {inBasket ? "移出对比" : "加入对比"}
    </Button>
  );
}

/**
 * One factor version's evaluation: always its latest standard run (the one the board, matrix
 * and curves use; older or non-standard runs are deliberately not selectable). `period` lives
 * in the URL query.
 */
export function VersionDetail({ name }: { name: string }) {
  const [params, setParams] = useSearchParams();
  const info = useQuery({ queryKey: ["factor", name], queryFn: () => fetchFactor(name) });
  const evaluate = useEvaluate();
  useHotkeys({
    a: () => {
      if (!toggleInBasket(name)) message.warning(`对比篮最多 ${MAX_COMPARE} 个因子`);
    },
  });

  const runs = info.data?.runs ?? [];
  // default_run is the latest standard run when there is one; never fall back to others.
  const run = runs.find((r) => r.run_id === info.data?.default_run && r.standard);
  const runId = run?.run_id;
  const wanted = params.get("period");
  const period =
    wanted && run?.periods.includes(wanted) ? wanted : run?.periods.includes("1D") ? "1D" : run?.periods[0];

  const detail = useQuery({
    queryKey: ["detail", name, runId, period],
    queryFn: () => fetchDetail(name, runId!, period!),
    enabled: !!run && !!period,
    staleTime: Infinity,
  });

  // Opening an uncached version derives its chart cache: refresh overlays that listed it missing.
  const qc = useQueryClient();
  useEffect(() => {
    if (!detail.isSuccess) return;
    const stale = qc
      .getQueriesData<BaseCurves>({ queryKey: ["baseCurves"] })
      .some(([, d]) => d?.missing.includes(name));
    if (stale) qc.invalidateQueries({ queryKey: ["baseCurves"] });
  }, [detail.isSuccess, name, qc]);

  const setPeriod = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("period", value);
    setParams(next, { replace: true });
  };

  if (info.error)
    return <ErrorState error={info.error} title={`因子 ${name} 加载失败`} onRetry={() => info.refetch()} />;

  const actions = (
    <Space size={8} wrap>
      <Button
        size="small"
        onClick={() =>
          evaluate.open(
            [name],
            run
              ? {
                  start_date: run.start_date ?? undefined,
                  end_date: run.end_date,
                  quantiles: run.quantiles ?? undefined,
                  periods: run.periods.map((p) => Number.parseInt(p, 10)).filter((n) => n > 0),
                  return_type: run.return_type ?? undefined,
                  universe: run.universe,
                  transaction_cost_bps: run.transaction_cost_bps ?? undefined,
                }
              : {},
          )
        }
      >
        {run ? "重新评估此版本" : "评估此版本"}
      </Button>
      <CompareToggle name={name} />
    </Space>
  );

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <div className="zf-run-bar" style={{ borderTop: 0, paddingTop: 0 }}>
          <FactorChips name={name} link={false} copyable />
          {run && (
            <span title={runLabel(run)}>
              <Tag color="green" bordered={false}>
                统一口径
              </Tag>
              <Typography.Text type="secondary" className="num">
                评估 {run.run_id}
              </Typography.Text>
            </span>
          )}
          {run && run.periods.length > 1 && (
            <Segmented options={run.periods} value={period} onChange={(v) => setPeriod(String(v))} />
          )}
          {run && <ParamsSummary run={run} />}
          <div style={{ marginInlineStart: "auto" }}>{actions}</div>
        </div>
      </Card>

      {info.isLoading ? (
        <Card>
          <Skeleton active />
        </Card>
      ) : !run ? (
        <Card>
          <Empty description="这个版本还没有统一口径的评估结果" />
        </Card>
      ) : detail.isLoading ? (
        <Card>
          <SlowLoading
            tip="正在加载图表数据…"
            hint="首次打开某个 run 的因子需要从原始数据计算图表（约 1–2 分钟），之后会直接读缓存。"
          />
        </Card>
      ) : detail.error ? (
        <ErrorState error={detail.error} title="图表数据加载失败" onRetry={() => detail.refetch()} />
      ) : detail.data && runId ? (
        <Results detail={detail.data} name={name} runId={runId} />
      ) : null}
    </Space>
  );
}
