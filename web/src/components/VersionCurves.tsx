import { Card, Empty, Segmented, Skeleton, Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchBaseCurves } from "../api";
import { windowLabel } from "../factorName";
import type { BaseVersion, CurveKind } from "../types";
import { OverlayChart } from "./charts";
import { ErrorState } from "./states";
import { rowTitle } from "./VersionMatrix";

const KINDS: { value: CurveKind; label: string }[] = [
  { value: "long_excess", label: "多头超额" },
  { value: "long", label: "多头" },
];

/**
 * Cumulative curves of several versions on one chart: the current prep across its windows
 * (default), or the current window across preps. `by` and `kind` live in the URL.
 */
export function VersionCurves({
  base,
  current,
  versions,
  preps,
  windows,
}: {
  base: string;
  current: BaseVersion;
  versions: BaseVersion[];
  /** Preps shown in the matrix; comparing across preps draws only these. */
  preps: string[];
  /** Windows shown as matrix columns; versions in hidden columns are not listed as missing. */
  windows: (number | null)[];
}) {
  const [params, setParams] = useSearchParams();
  const by = params.get("by") === "win" ? "win" : "prep";
  // Only long-side curves are offered; old `kind=ls` links fall back to the default.
  const kind: CurveKind = params.get("kind") === "long" ? "long" : "long_excess";
  const patch = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value == null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };
  const q = by === "prep" ? { prep: current.prep, kind } : { win: current.window, kind };
  const curves = useQuery({
    queryKey: ["baseCurves", base, by, by === "prep" ? current.prep : current.window, kind],
    queryFn: () => fetchBaseCurves(base, q),
    staleTime: 5 * 60_000,
  });
  const byName = new Map(versions.map((v) => [v.name, v]));
  const allPreps = [...new Set(versions.map((v) => v.prep))];
  const label = (name: string) => {
    const v = byName.get(name);
    if (!v) return name;
    return by === "prep" ? windowLabel(v.window) : rowTitle(v.prep, allPreps);
  };
  const data = curves.data;
  const shown = (name: string) => {
    const v = byName.get(name);
    return by === "prep" ? !v || windows.includes(v.window) : preps.includes(v?.prep ?? "");
  };
  const missing = data ? data.missing.filter(shown) : [];
  const lines = data
    ? Object.entries(data.series)
        .filter(([name]) => shown(name))
        .map(([name, d]) => ({
          key: name,
          label: name === current.name ? `${label(name)}（当前）` : label(name),
          data: d,
        }))
    : [];
  const title = `${KINDS.find((k) => k.value === kind)!.label}累计收益 · ${
    by === "prep" ? `${rowTitle(current.prep, allPreps)} 各周期` : `${windowLabel(current.window)} 各处理方式`
  }`;

  return (
    <Card
      size="small"
      title={title}
      extra={
        <Space size={8} wrap>
          <Segmented
            size="small"
            value={by}
            onChange={(v) => patch("by", v === "win" ? "win" : null)}
            options={[
              { value: "prep", label: "同处理方式比周期" },
              { value: "win", label: "同周期比处理方式" },
            ]}
          />
          <Segmented
            size="small"
            value={kind}
            onChange={(v) => patch("kind", v === "long" ? "long" : null)}
            options={KINDS}
          />
        </Space>
      }
    >
      {curves.isLoading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : curves.error ? (
        <ErrorState error={curves.error} title="曲线加载失败" onRetry={() => curves.refetch()} />
      ) : !lines.length ? (
        <Empty description="这些版本还没有可用的曲线（未评估或图表缓存未生成）" />
      ) : (
        <OverlayChart dates={data!.dates} lines={lines} bold={current.name} />
      )}
      {missing.length > 0 && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          无曲线（未评估或缓存未生成）：{missing.map(label).join("、")}
        </Typography.Text>
      )}
    </Card>
  );
}
