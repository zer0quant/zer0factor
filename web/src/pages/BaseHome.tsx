import { useEffect, useMemo } from "react";
import { Button, Card, Skeleton, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchBase, fetchBases } from "../api";
import { boardHref } from "../boardState";
import { CompareBar } from "../components/CompareBar";
import { DirectionTag, STATUS_LABEL } from "../components/DirectionTag";
import { useEvaluate } from "../components/EvaluateDrawer";
import { ErrorState } from "../components/states";
import { VersionDetail } from "../components/VersionDetail";
import { baseLabel, comparePrep, prepLabel, windowLabel } from "../factorName";
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
 * evaluation is shown below. URL: /base/:base?prep=&win=&run=&period=
 */
export default function BaseHome() {
  const base = useParams().base ?? "";
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const evaluate = useEvaluate();
  const info = useQuery({ queryKey: ["base", base], queryFn: () => fetchBase(base), retry: false });
  const bases = useQuery({ queryKey: ["bases"], queryFn: fetchBases });
  const summary = bases.data?.find((b) => b.base === base);

  const versions = info.data?.versions ?? [];
  const preps = useMemo(
    () => [...new Set(versions.map((v) => v.prep))].sort(comparePrep),
    [versions],
  );
  const wantedPrep = params.get("prep");
  const prep = wantedPrep && preps.includes(wantedPrep) ? wantedPrep : info.data?.default_prep;
  const windows = versions.filter((v) => v.prep === prep);
  const wantedWin = params.get("win");
  const current = windows.find((v) => winParam(v.window) === wantedWin) ?? defaultVersion(windows);

  // Write the resolved selection back, so the URL always names the version on screen.
  useEffect(() => {
    if (!current || !prep) return;
    if (params.get("prep") === prep && params.get("win") === winParam(current.window)) return;
    const next = new URLSearchParams(params);
    next.set("prep", prep);
    next.set("win", winParam(current.window));
    setParams(next, { replace: true });
  }, [current, prep, params, setParams]);

  const select = (nextPrep: string, win: number | null | undefined) => {
    const next = new URLSearchParams(params);
    next.set("prep", nextPrep);
    if (win === undefined) next.delete("win");
    else next.set("win", winParam(win));
    next.delete("run"); // another version has its own runs; the holding period carries over
    setParams(next);
  };
  const hop = (delta: number) => {
    const i = windows.findIndex((v) => v.name === current?.name);
    const next = windows[i + delta];
    if (i >= 0 && next && prep) select(prep, next.window);
  };
  useHotkeys({ h: () => hop(-1), l: () => hop(1), b: () => navigate(boardHref()) });

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

  const unevaluated = windows.filter((v) => !v.evaluated).map((v) => v.name);
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
          </Space>
          {info.isLoading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : (
            <>
              <Tabs
                size="small"
                activeKey={prep}
                onChange={(k) => select(k, undefined)}
                items={preps.map((p) => ({
                  key: p,
                  label: (
                    <span>
                      {p === "z_neu" ? "中性化（旧）" : prepLabel(p)}
                      {p === info.data?.primary_prep && (
                        <Tag bordered={false} color="blue" style={{ marginInlineStart: 6, marginInlineEnd: 0 }}>
                          主版本
                        </Tag>
                      )}
                    </span>
                  ),
                }))}
                style={{ marginBottom: 0 }}
              />
              <div className="zf-sibs" style={{ paddingBottom: 8 }}>
                <Typography.Text type="secondary" style={{ flex: "none" }}>
                  周期
                </Typography.Text>
                {windows.map((v) => {
                  const cur = v.name === current?.name;
                  return (
                    <button
                      type="button"
                      key={v.name}
                      className={`zf-sib${cur ? " zf-sib-cur" : ""}`}
                      title={v.name}
                      aria-current={cur ? "page" : undefined}
                      onClick={() => prep && select(prep, v.window)}
                    >
                      <span>{windowLabel(v.window)}</span>
                      <small className="num">
                        {v.evaluated && isNum(v.icir) ? `ICIR ${num(v.icir, 2)}` : "未评估"}
                      </small>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </Space>
      </Card>
      {current && (
        <VersionDetail
          key={current.name}
          name={current.name}
          extra={
            unevaluated.length > 1 && (
              <Button size="small" onClick={() => evaluate.open(unevaluated, {})}>
                评估全部未评估窗口（{unevaluated.length}）
              </Button>
            )
          }
        />
      )}
      <CompareBar />
    </Space>
  );
}
