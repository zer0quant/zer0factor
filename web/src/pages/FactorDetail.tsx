import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Row,
  Segmented,
  Select,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useHotkeys } from "../hotkeys";
import { fetchDetail, fetchFactor } from "../api";
import { runLabel } from "../format";
import { boardHref } from "../boardState";
import { MAX_COMPARE, toggleInBasket, useBasket } from "../compareBasket";
import type { Detail, IcBlock } from "../types";
import {
  AcfChart,
  CumulativeChart,
  DecayChart,
  IcHistChart,
  IcSeriesChart,
  adjustIcBlock,
} from "../components/charts";
import { GroupTable, LatestValues, MetricCards, ParamsSummary } from "../components/panels";
import { ErrorState, SlowLoading } from "../components/states";
import { FactorChips } from "../components/FactorName";
import { Siblings } from "../components/Siblings";
import { CompareBar } from "../components/CompareBar";

function IcSection({ block, label }: { block: IcBlock; label: string }) {
  const cards: [string, React.ReactNode][] = [
    [`${label} 序列${block.monthly ? "（月度均值）" : ""}`, <IcSeriesChart block={block} label={label} />],
    [`${label} 分布`, <IcHistChart block={block} />],
    [`${label} 自相关`, <AcfChart block={block} />],
    [`${label} 衰减（因子对 k 日后的 1 日收益）`, <DecayChart block={block} />],
  ];
  return (
    <Row gutter={[16, 16]}>
      {cards.map(([title, chart]) => (
        <Col key={title} xs={24} xl={12}>
          <Card size="small" title={title}>
            {chart}
          </Card>
        </Col>
      ))}
    </Row>
  );
}

function IcCharts({ detail }: { detail: Detail }) {
  const reverse = detail.direction === -1;
  const [adjusted, setAdjusted] = useState(true);
  const adj = reverse && adjusted;
  const block = (b: IcBlock) => (adj ? adjustIcBlock(b, -1) : b);
  const suffix = adj ? "（方向调整）" : "";
  return (
    <Card
      size="small"
      title="IC 分析"
      extra={
        reverse && (
          <Space size={6}>
            <Switch size="small" checked={adjusted} onChange={setAdjusted} />
            <Typography.Text style={{ fontSize: 12 }}>按方向调整（× −1）</Typography.Text>
          </Space>
        )
      }
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <IcSection block={block(detail.rank_ic)} label={`Rank IC${suffix}`} />
        <Collapse
          size="small"
          items={[
            {
              key: "pearson",
              label: "IC（Pearson）图表",
              children: <IcSection block={block(detail.ic)} label={`IC${suffix}`} />,
            },
          ]}
        />
      </Space>
    </Card>
  );
}

function Results({ detail, name, runId }: { detail: Detail; name: string; runId: string }) {
  const c = detail.cumulative;
  const s = detail.summary;
  const q = (v: unknown) => (typeof v === "number" ? String(Math.round(v)) : null);
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small" title="核心指标">
        <MetricCards detail={detail} />
      </Card>
      <Card size="small" title="分组累计收益">
        {c ? (
          <>
            <CumulativeChart {...c} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {detail.notes.join("；")}
            </Typography.Text>
          </>
        ) : (
          <Empty description="该 run 缺少原始数据（clean_factor_data），无法绘制收益曲线" />
        )}
      </Card>
      {detail.group_table && (
        <Card size="small" title="分组收益">
          <GroupTable
            rows={detail.group_table}
            longGroup={q(s["long_quantile"])}
            shortGroup={q(s["short_quantile"])}
          />
        </Card>
      )}
      <IcCharts detail={detail} />
      <Card size="small" title="最新因子值">
        <LatestValues name={name} runId={runId} />
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

export default function FactorDetail() {
  const name = useParams().name ?? "";
  const [params, setParams] = useSearchParams();
  const info = useQuery({ queryKey: ["factor", name], queryFn: () => fetchFactor(name) });
  const navigate = useNavigate();
  useHotkeys({
    a: () => {
      if (!toggleInBasket(name)) message.warning(`对比篮最多 ${MAX_COMPARE} 个因子`);
    },
    b: () => navigate(boardHref()),
  });

  const runs = info.data?.runs ?? [];
  const runId = params.get("run") ?? info.data?.default_run ?? undefined;
  const run = runs.find((r) => r.run_id === runId);
  const wanted = params.get("period");
  const period =
    wanted && run?.periods.includes(wanted)
      ? wanted
      : run?.periods.includes("1D")
        ? "1D"
        : run?.periods[0];

  useEffect(() => {
    if (info.data && !params.get("run") && info.data.default_run) {
      const next = new URLSearchParams(params);
      next.set("run", info.data.default_run);
      setParams(next, { replace: true });
    }
  }, [info.data, params, setParams]);

  const detail = useQuery({
    queryKey: ["detail", name, runId, period],
    queryFn: () => fetchDetail(name, runId!, period!),
    enabled: !!run && !!period,
    staleTime: Infinity,
  });

  const setQuery = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    if (key === "run") next.delete("period");
    setParams(next);
  };

  if (info.error)
    return (
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <ErrorState error={info.error} title={`因子 ${name} 加载失败`} onRetry={() => info.refetch()} />
        <Link to={boardHref()}>
          <Button>回到因子看板</Button>
        </Link>
      </Space>
    );
  const meta = info.data?.meta;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            <Link to={boardHref()}>因子看板</Link> / {name}
          </Typography.Text>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}>
            <Space wrap style={{ flex: 1, minWidth: 0 }}>
              <Typography.Title level={4} style={{ margin: 0, overflowWrap: "anywhere" }}>
                {name}
              </Typography.Title>
              {meta?.category && <Tag color="blue">{meta.category}</Tag>}
              {meta?.tags.map((t) => <Tag key={t}>{t}</Tag>)}
              {detail.data?.direction === -1 && <Tag color="orange">反向因子</Tag>}
            </Space>
            <CompareToggle name={name} />
          </div>
          <FactorChips name={name} link={false} copyable />
          {meta?.description && <Typography.Text type="secondary">{meta.description}</Typography.Text>}
          <Siblings name={name} />
          {runs.length > 0 && (
            <div className="zf-run-bar">
              <Select
                style={{ width: 260, maxWidth: "100%" }}
                value={runId}
                onChange={(v) => setQuery("run", v)}
                options={runs.map((r) => ({
                  value: r.run_id,
                  label: (
                    <span title={runLabel(r)}>
                      {r.standard && <Tag color="green">标准</Tag>}
                      {r.run_id}
                    </span>
                  ),
                }))}
              />
              {run && run.periods.length > 1 && (
                <Segmented
                  options={run.periods}
                  value={period}
                  onChange={(v) => setQuery("period", String(v))}
                />
              )}
              {run && <ParamsSummary run={run} />}
            </div>
          )}
        </Space>
      </Card>

      {info.isLoading ? (
        <Card>
          <Skeleton active />
        </Card>
      ) : runs.length === 0 ? (
        <Card>
          <Empty description="该因子还没有任何评估结果，请先用 evaluate-factor / evaluate-batch 评估" />
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
      <CompareBar />
    </Space>
  );
}
