import { useEffect } from "react";
import {
  Button,
  Card,
  Col,
  Empty,
  Row,
  Segmented,
  Select,
  Skeleton,
  Space,
  Tag,
  Tabs,
  Typography,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { fetchDetail, fetchFactor } from "../api";
import { runLabel } from "../format";
import type { Detail, IcBlock } from "../types";
import {
  AcfChart,
  CumulativeChart,
  DecayChart,
  IcHistChart,
  IcSeriesChart,
} from "../components/charts";
import { GroupTable, LatestValues, MetricCards, ParamsPanel } from "../components/panels";
import { ErrorState, SlowLoading } from "../components/states";

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

function Results({ detail, name, runId }: { detail: Detail; name: string; runId: string }) {
  const c = detail.cumulative;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
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
      <Card size="small" title="核心指标">
        <MetricCards detail={detail} />
      </Card>
      {detail.group_table && (
        <Card size="small" title="分组收益">
          <GroupTable rows={detail.group_table} />
        </Card>
      )}
      <Card size="small" styles={{ body: { paddingTop: 0 } }}>
        <Tabs
          items={[
            { key: "rank", label: "Rank IC", children: <IcSection block={detail.rank_ic} label="Rank IC" /> },
            { key: "ic", label: "IC（Pearson）", children: <IcSection block={detail.ic} label="IC" /> },
          ]}
        />
      </Card>
      <Card size="small" title="最新因子值">
        <LatestValues name={name} runId={runId} />
      </Card>
    </Space>
  );
}

export default function FactorDetail() {
  const name = useParams().name ?? "";
  const [params, setParams] = useSearchParams();
  const info = useQuery({ queryKey: ["factor", name], queryFn: () => fetchFactor(name) });

  const runs = info.data?.runs ?? [];
  const runId = params.get("run") ?? info.data?.default_run ?? undefined;
  const run = runs.find((r) => r.run_id === runId);
  const period = params.get("period") ?? (run?.periods.includes("1D") ? "1D" : run?.periods[0]);

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
        <Link to="/">
          <Button>回到因子看板</Button>
        </Link>
      </Space>
    );
  const meta = info.data?.meta;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            <Link to="/">因子看板</Link> / {name}
          </Typography.Text>
          <Space wrap>
            <Typography.Title level={4} style={{ margin: 0, overflowWrap: "anywhere" }}>
              {name}
            </Typography.Title>
            {meta?.category && <Tag color="blue">{meta.category}</Tag>}
            {meta?.tags.map((t) => <Tag key={t}>{t}</Tag>)}
            {detail.data?.direction === -1 && <Tag color="orange">反向因子</Tag>}
          </Space>
          {meta?.description && <Typography.Text type="secondary">{meta.description}</Typography.Text>}
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
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={6}>
            <Card size="small" title="评估参数" style={{ position: "sticky", top: 56 + 16 }}>
              <Space direction="vertical" style={{ width: "100%" }} size={12}>
                <Select
                  style={{ width: "100%" }}
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
                    block
                    options={run.periods}
                    value={period}
                    onChange={(v) => setQuery("period", String(v))}
                  />
                )}
                {run && <ParamsPanel run={run} />}
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={18}>
            {detail.isLoading ? (
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
          </Col>
        </Row>
      )}
    </Space>
  );
}
