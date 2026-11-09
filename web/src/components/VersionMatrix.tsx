import { Button, Segmented, Tag, Typography } from "antd";
import { useSearchParams } from "react-router-dom";
import { comparePrep, prepLabel, windowLabel } from "../factorName";
import { isNum, num, pct, signColor, withSign } from "../format";
import type { BaseMetricKey, BaseVersion, Num } from "../types";

/** Metrics the matrix can show; the first is the default. */
export const MATRIX_METRICS: {
  key: BaseMetricKey;
  label: string;
  fmt: (v: number) => string;
  signed?: boolean;
}[] = [
  { key: "icir", label: "ICIR", fmt: (v) => num(v, 2) },
  {
    key: "long_exc_ann_ret",
    label: "多头超额",
    fmt: (v) => pct(v, 1),
    signed: true,
  },
  {
    key: "long_ann_ret",
    label: "多头年化",
    fmt: (v) => pct(v, 1),
    signed: true,
  },
  { key: "monotonicity", label: "单调性", fmt: (v) => num(v, 2) },
  { key: "ic_win_rate", label: "IC 胜率", fmt: (v) => `${v.toFixed(1)}%` },
];

export const prepTitle = (p: string) => (p === "z_neu" ? "中性化（旧）" : prepLabel(p));

export type RowGroup = "primary" | "control" | "attribution";
export interface MatrixRow {
  prep: string;
  group: RowGroup;
}

/**
 * Rows of the version matrix, top to bottom: the primary prep (always, even when it is not
 * stored yet), the control (Z when stored, else raw: Z keeps raw's cross-sectional order, so
 * raw is hidden next to it), then the attribution preps (size / industry neutral, legacy,
 * rank) when `attrOpen`. The current prep is always shown, so a selection is never hidden.
 */
export function matrixRows(
  preps: string[],
  primary: string,
  attrOpen: boolean,
  currentPrep: string | undefined,
): { rows: MatrixRow[]; attribution: string[]; attrShown: boolean } {
  const control = preps.includes("z") ? "z" : preps.includes("raw") ? "raw" : null;
  const hiddenRaw = control === "z" && preps.includes("raw") ? "raw" : null;
  const attribution = preps.filter((p) => p !== primary && p !== control && p !== hiddenRaw);
  const attrShown = attrOpen || (!!currentPrep && attribution.includes(currentPrep));
  const rows: MatrixRow[] = [{ prep: primary, group: "primary" }];
  if (control) rows.push({ prep: control, group: "control" });
  if (hiddenRaw && currentPrep === hiddenRaw) rows.push({ prep: hiddenRaw, group: "control" });
  if (attrShown) rows.push(...attribution.map((p) => ({ prep: p, group: "attribution" as const })));
  return { rows, attribution, attrShown };
}

export const rowTitle = (p: string, preps: string[]) =>
  p === "z" ? "原始（Z）" : p === "raw" && preps.includes("z") ? "原始（未标准化）" : prepTitle(p);

/** Whether the attribution rows are expanded (URL `attr=1`). */
export function useAttrOpen(): [boolean, (open: boolean) => void] {
  const [params, setParams] = useSearchParams();
  const open = params.get("attr") === "1";
  const set = (v: boolean) => {
    const next = new URLSearchParams(params);
    if (v) next.set("attr", "1");
    else next.delete("attr");
    setParams(next, { replace: true });
  };
  return [open, set];
}
const winKey = (w: number | null) => (w == null ? -1 : w);

function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Sorted preps and windows (no-window first) present among the versions. */
export function versionAxes(versions: BaseVersion[]) {
  const preps = [...new Set(versions.map((v) => v.prep))].sort(comparePrep);
  const windows = [...new Set(versions.map((v) => v.window))].sort((a, b) => winKey(a) - winKey(b));
  return { preps, windows };
}

/**
 * Windows shown as matrix columns: the no-window column only when a visible row has an
 * evaluated no-window version with an ICIR (judged on ICIR, not the chosen metric, so the column
 * does not flicker), or when the current version is the no-window one.
 */
export function matrixWindows(
  versions: BaseVersion[],
  rowPreps: string[],
  current: BaseVersion | undefined,
): (number | null)[] {
  const { windows } = versionAxes(versions);
  const keepNone =
    (current != null && current.window == null) ||
    versions.some((v) => v.window == null && rowPreps.includes(v.prep) && v.evaluated && isNum(v.icir));
  return keepNone ? windows : windows.filter((w) => w != null);
}

/**
 * Preprocessing × window grid of one base factor's versions. Each cell shows one metric of the
 * version's latest standard evaluation; clicking a cell selects that version. No colour scale on
 * purpose: the grid is for checking robustness, not for picking the best cell.
 */
export function VersionMatrix({
  versions,
  primaryPrep,
  current,
  onSelect,
}: {
  versions: BaseVersion[];
  primaryPrep: string;
  current: BaseVersion | undefined;
  onSelect: (v: BaseVersion) => void;
}) {
  const [params, setParams] = useSearchParams();
  const [attrOpen, setAttrOpen] = useAttrOpen();
  const metric = MATRIX_METRICS.find((m) => m.key === params.get("m")) ?? MATRIX_METRICS[0];
  const setMetric = (key: string) => {
    const next = new URLSearchParams(params);
    if (key === MATRIX_METRICS[0].key) next.delete("m");
    else next.set("m", key);
    setParams(next, { replace: true });
  };
  const { preps } = versionAxes(versions);
  const { rows, attribution, attrShown } = matrixRows(preps, primaryPrep, attrOpen, current?.prep);
  const windows = matrixWindows(
    versions,
    rows.map((r) => r.prep),
    current,
  );
  const primaryMissing = !preps.includes(primaryPrep);
  const byCell = new Map(versions.map((v) => [`${v.prep}|${winKey(v.window)}`, v]));
  const value = (v: BaseVersion): Num => (v.evaluated ? (v.metrics?.[metric.key] ?? null) : null);
  const show = (v: number) => (
    <span style={{ color: metric.signed ? signColor(v) : undefined }}>
      {metric.signed ? withSign(metric.fmt(v), v) : metric.fmt(v)}
    </span>
  );

  return (
    <div>
      <div className="zf-vm-head">
        <Segmented
          size="small"
          value={metric.key}
          onChange={(k) => setMetric(String(k))}
          options={MATRIX_METRICS.map((m) => ({
            value: m.key,
            label: m.label,
          }))}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          每格为该版本最新一次统一口径评估；点击格子查看详情 · h/l 切换周期，j/k 切换处理方式
        </Typography.Text>
      </div>
      <div className="zf-vm-wrap">
        <table className="zf-vm">
          <thead>
            <tr>
              <th className="zf-vm-prep" />
              {windows.map((w) => (
                <th key={winKey(w)}>{windowLabel(w)}</th>
              ))}
              <th className="zf-vm-median">中位数</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ prep: p, group }, i) => {
              const nums: number[] = [];
              const firstAttr = group === "attribution" && rows[i - 1]?.group !== "attribution";
              return (
                <tr
                  key={p}
                  className={
                    [group === "primary" && "zf-vm-primary", firstAttr && "zf-vm-attr-first"]
                      .filter(Boolean)
                      .join(" ") || undefined
                  }
                >
                  <th className="zf-vm-prep">
                    {rowTitle(p, preps)}
                    {group === "primary" && (
                      <Tag bordered={false} color="blue" style={{ marginInlineStart: 6, marginInlineEnd: 0 }}>
                        {primaryMissing ? "主版本 · 待中性化" : "主版本"}
                      </Tag>
                    )}
                    {group === "control" && (
                      <Typography.Text type="secondary" style={{ fontSize: 12, marginInlineStart: 6 }}>
                        对照
                      </Typography.Text>
                    )}
                    {firstAttr && (
                      <Typography.Text type="secondary" style={{ fontSize: 12, marginInlineStart: 6 }}>
                        归因
                      </Typography.Text>
                    )}
                  </th>
                  {windows.map((w) => {
                    const v = byCell.get(`${p}|${winKey(w)}`);
                    if (!v)
                      return (
                        <td key={winKey(w)} className="zf-vm-none">
                          —
                        </td>
                      );
                    const x = value(v);
                    if (isNum(x)) nums.push(x);
                    const cur = v.name === current?.name;
                    return (
                      <td key={winKey(w)} className={cur ? "zf-vm-cur" : undefined}>
                        <button
                          type="button"
                          title={v.name}
                          aria-current={cur ? "true" : undefined}
                          onClick={() => onSelect(v)}
                        >
                          {!v.evaluated ? (
                            <span className="zf-vm-muted">未评估</span>
                          ) : isNum(x) ? (
                            show(x)
                          ) : (
                            <span className="zf-vm-muted">无数字</span>
                          )}
                        </button>
                      </td>
                    );
                  })}
                  <td className="zf-vm-median">
                    {(() => {
                      const m = median(nums);
                      return m == null ? <span className="zf-vm-muted">—</span> : show(m);
                    })()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {attribution.length > 0 && (
        <Button
          type="link"
          size="small"
          style={{ paddingInline: 0 }}
          disabled={attrShown && !attrOpen}
          onClick={() => setAttrOpen(!attrOpen)}
        >
          {attrShown ? "收起归因" : `展开归因（${attribution.length}）`}
          <Typography.Text type="secondary" style={{ fontSize: 12, marginInlineStart: 8 }}>
            {attrShown && !attrOpen ? "当前版本在归因组里" : "市值中性 / 行业中性等，只用来拆解效果来源，不用来挑版本"}
          </Typography.Text>
        </Button>
      )}
    </div>
  );
}
