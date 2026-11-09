import { useEffect, useMemo } from "react";
import { Button, Card, Skeleton, Space, Tag, Tooltip, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchBase, fetchBases } from "../api";
import { boardHref } from "../boardState";
import { CompareBar } from "../components/CompareBar";
import { DirectionTag, STATUS_LABEL } from "../components/DirectionTag";
import { useEvaluate } from "../components/EvaluateDrawer";
import { ErrorState } from "../components/states";
import { VersionCurves } from "../components/VersionCurves";
import { VersionDetail } from "../components/VersionDetail";
import { VersionMatrix, matrixRows, matrixWindows, useAttrOpen, versionAxes } from "../components/VersionMatrix";
import { baseLabel, prepLabel } from "../factorName";
import { isNum, num } from "../format";
import { useHotkeys } from "../hotkeys";
import type { BaseVersion } from "../types";

const winParam = (w: number | null) => (w == null ? "none" : String(w));

/** Shortest evaluated window, else the shortest one: never the best-scoring one. */
function defaultVersion(versions: BaseVersion[]): BaseVersion | undefined {
  return versions.find((v) => v.evaluated) ?? versions[0];
}

/**
 * A base factor's home page: preprocessing tabs × window buttons select one version, whose
 * evaluation is shown below. URL: /base/:base?prep=&win=&period= (always the latest standard run)
 */
export default function BaseHome() {
  const base = useParams().base ?? "";
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const evaluate = useEvaluate();
  const info = useQuery({
    queryKey: ["base", base],
    queryFn: () => fetchBase(base),
    retry: false,
  });
  const bases = useQuery({ queryKey: ["bases"], queryFn: fetchBases });
  const summary = bases.data?.find((b) => b.base === base);

  const versions = info.data?.versions ?? [];
  const { preps } = useMemo(() => versionAxes(versions), [versions]);
  const wantedPrep = params.get("prep");
  const prep = wantedPrep && preps.includes(wantedPrep) ? wantedPrep : info.data?.default_prep;
  const windows = versions.filter((v) => v.prep === prep);
  const primaryPrep = info.data?.primary_prep ?? "";
  const [attrOpen] = useAttrOpen();
  // Preps on screen, in matrix order (j/k and the overlay curves use only these).
  const visiblePreps = matrixRows(preps, primaryPrep, attrOpen, prep)
    .rows.map((r) => r.prep)
    .filter((p) => preps.includes(p));
  const wantedWin = params.get("win");
  const current = windows.find((v) => winParam(v.window) === wantedWin) ?? defaultVersion(windows);
  const visibleWindows = matrixWindows(versions, visiblePreps, current);

  // Write the resolved selection back, so the URL always names the version on screen.
  useEffect(() => {
    if (!current || !prep) return;
    const stale = params.has("run"); // old links carried a run; only the latest standard one is shown
    if (!stale && params.get("prep") === prep && params.get("win") === winParam(current.window)) return;
    const next = new URLSearchParams(params);
    next.delete("run");
    next.set("prep", prep);
    next.set("win", winParam(current.window));
    setParams(next, { replace: true });
  }, [current, prep, params, setParams]);

  const select = (nextPrep: string, win: number | null | undefined) => {
    const next = new URLSearchParams(params);
    next.set("prep", nextPrep);
    if (win === undefined) next.delete("win");
    else next.set("win", winParam(win));
    setParams(next);
  };
  const hop = (delta: number) => {
    const i = windows.findIndex((v) => v.name === current?.name);
    const next = windows[i + delta];
    if (i >= 0 && next && prep) select(prep, next.window);
  };
  // Next prep that exists; keep the window when that prep has it, else its default window.
  const hopPrep = (delta: number) => {
    const i = prep ? visiblePreps.indexOf(prep) : -1;
    const nextPrep = visiblePreps[i + delta];
    if (i < 0 || !nextPrep || !current) return;
    const same = versions.some((v) => v.prep === nextPrep && v.window === current.window);
    select(nextPrep, same ? current.window : undefined);
  };
  useHotkeys({
    h: () => hop(-1),
    l: () => hop(1),
    j: () => hopPrep(1),
    k: () => hopPrep(-1),
    b: () => navigate(boardHref()),
  });

  if (info.error)
    return (
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {String(info.error.message).startsWith("404") ? (
          <ErrorState error={info.error} title={`没有原始因子 ${base}`} />
        ) : (
          <ErrorState error={info.error} title={`原始因子 ${base} 加载失败`} onRetry={() => info.refetch()} />
        )}
        <Link to={boardHref()}>
          <Button>回到因子看板</Button>
        </Link>
      </Space>
    );

  // Primary version only; windows without a number count as unevaluated too (evaluated but
  // ICIR is empty).
  const unevaluated = versions
    .filter((v) => v.prep === primaryPrep && (!v.evaluated || !isNum(v.icir)))
    .map((v) => v.name);
  const label = baseLabel(base);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small" styles={{ body: { paddingBottom: 4 } }}>
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            <Link to={boardHref()}>因子看板</Link> / {label}
          </Typography.Text>
          <Space wrap size={[8, 4]} align="center">
            <Typography.Title level={4} style={{ margin: 0 }}>
              {label}
            </Typography.Title>
            {label !== base && <Typography.Text type="secondary">{base}</Typography.Text>}
            {summary &&
              (summary.status === "missing" || summary.status === "unevaluated" ? (
                <Tag bordered={false}>{STATUS_LABEL[summary.status]}</Tag>
              ) : (
                <DirectionTag direction={summary.direction} status={summary.status} />
              ))}
            {summary && summary.status === "ok" && (
              <Tooltip title={`主版本（${prepLabel(summary.primary_prep)}）各窗口 ICIR 的中位数`}>
                <Typography.Text type="secondary" className="num">
                  ICIR 中位数 {num(summary.icir_median, 3)}
                </Typography.Text>
              </Tooltip>
            )}
            {unevaluated.length > 0 && !(unevaluated.length === 1 && unevaluated[0] === current?.name) && (
              <Button size="small" style={{ marginInlineStart: 8 }} onClick={() => evaluate.open(unevaluated, {})}>
                评估主版本全部未评估窗口（{unevaluated.length}）
              </Button>
            )}
          </Space>
          {info.isLoading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : (
            <VersionMatrix
              versions={versions}
              primaryPrep={primaryPrep}
              current={current}
              onSelect={(v) => select(v.prep, v.window)}
            />
          )}
        </Space>
      </Card>
      {current && versions.some((v) => v.evaluated) && (
        <VersionCurves
          base={base}
          current={current}
          versions={versions}
          preps={visiblePreps}
          windows={visibleWindows}
        />
      )}
      {current && <VersionDetail key={current.name} name={current.name} />}
      <CompareBar />
    </Space>
  );
}
