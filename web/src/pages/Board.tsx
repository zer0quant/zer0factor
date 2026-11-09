import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Checkbox, Empty, Grid, Input, Popover, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { InputRef } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchBases } from "../api";
import { rememberBoardSearch } from "../boardState";
import { CompareBar } from "../components/CompareBar";
import { DirectionTag, STATUS_LABEL } from "../components/DirectionTag";
import { ErrorState } from "../components/states";
import { baseHref, baseLabel, compareBase, prepLabel, windowLabel } from "../factorName";
import { fmtDate, isNum, num, pct, signColor, withSign } from "../format";
import { useHotkeys } from "../hotkeys";
import type { BaseMetricKey, BaseRow, Num } from "../types";

const COLS_KEY = "zer0factor.board.hiddenColumns";

/** Metric columns, same set and formats as the per-version board had. Values are window medians. */
const METRIC_COLS: {
  key: BaseMetricKey;
  title: string;
  fmt: (v: Num) => string;
  signed?: boolean;
  tip?: string;
  width?: number;
  defaultHidden?: boolean;
}[] = [
  { key: "ic_adj", title: "方向调整 IC", fmt: (v) => num(v, 4), tip: "Rank IC 均值 × 因子方向", width: 124 },
  { key: "icir", title: "ICIR", fmt: (v) => num(v, 3), tip: "方向调整后的 ICIR；悬停数字查看各窗口", width: 96 },
  {
    key: "t_stat",
    title: "t 值",
    fmt: (v) => num(v, 2),
    tip: "方向调整后的 HAC t 统计量；样本长度相近时与 ICIR 几乎完全相关",
    defaultHidden: true,
  },
  { key: "ic_win_rate", title: "IC 胜率", fmt: (v) => (isNum(v) ? `${v.toFixed(1)}%` : "—") },
  { key: "long_ann_ret", title: "多头年化", fmt: (v) => pct(v), signed: true, tip: "扣费后多头组合年化收益" },
  { key: "long_max_dd", title: "多头回撤", fmt: (v) => pct(v), tip: "多头组合最大回撤" },
  { key: "long_sharpe", title: "多头夏普", fmt: (v) => num(v, 2), signed: true },
  {
    key: "long_exc_ann_ret",
    title: "多头超额",
    fmt: (v) => pct(v),
    signed: true,
    tip: "多头相对全市场等权的年化超额（扣费后）",
  },
  { key: "monotonicity", title: "单调性", fmt: (v) => num(v, 2) },
  { key: "turnover_long", title: "多头换手", fmt: (v) => pct(v, 1), tip: "多头组日均换手" },
];

/** Columns users can hide; the factor name is always shown. */
const OPTIONAL: { key: string; label: string; defaultHidden?: boolean }[] = [
  { key: "direction", label: "方向" },
  ...METRIC_COLS.map((m) => ({ key: m.key, label: m.title, defaultHidden: m.defaultHidden })),
  { key: "range", label: "样本区间", defaultHidden: true },
  { key: "run_id", label: "评估 run", defaultHidden: true },
];
const DEFAULT_HIDDEN = OPTIONAL.filter((c) => c.defaultHidden).map((c) => c.key);

function readHidden(): string[] | null {
  try {
    const v = JSON.parse(localStorage.getItem(COLS_KEY) ?? "null");
    return Array.isArray(v) && v.every((x) => typeof x === "string") ? v : null;
  } catch {
    return null;
  }
}
function writeHidden(v: string[] | null) {
  try {
    if (v == null) localStorage.removeItem(COLS_KEY);
    else localStorage.setItem(COLS_KEY, JSON.stringify(v));
  } catch {
    /* storage unavailable: keep the in-memory choice */
  }
}

const metricOf = (r: BaseRow, key: BaseMetricKey): number | null => {
  const v = r.status === "ok" ? r.metrics?.[key] : null;
  return isNum(v) ? v : null;
};

/** By a metric, descending by default; rows without a number always sort last. */
function byMetric(key: BaseMetricKey) {
  return (a: BaseRow, b: BaseRow, desc: boolean) => {
    const x = metricOf(a, key);
    const y = metricOf(b, key);
    if (x == null && y == null) return compareBase(a.base, b.base);
    if (x == null) return 1;
    if (y == null) return -1;
    return desc ? y - x : x - y;
  };
}

function IcirCell({ r }: { r: BaseRow }) {
  if (r.status !== "ok")
    return (
      <Tooltip
        title={
          r.status === "missing"
            ? `存储里还没有${prepLabel(r.primary_prep)}版本`
            : r.status === "unevaluated"
              ? `${prepLabel(r.primary_prep)}版本还没有标准评估`
              : "主版本各窗口的评估方向不一致，不给数字"
        }
      >
        <Tag bordered={false} style={{ marginInlineEnd: 0 }}>
          {STATUS_LABEL[r.status]}
        </Tag>
      </Tooltip>
    );
  const evaluated = r.windows.filter((w) => w.evaluated && isNum(w.icir));
  return (
    <Tooltip
      title={
        <div>
          <div>
            {prepLabel(r.primary_prep)} · 已评估 {evaluated.length} / {r.windows.length} 个窗口
          </div>
          {r.windows.map((w) => (
            <div key={w.name} className="num">
              {windowLabel(w.window)}：{w.evaluated && isNum(w.icir) ? num(w.icir, 3) : "未评估"}
            </div>
          ))}
        </div>
      }
    >
      <span className="num" style={{ fontWeight: 600 }}>
        {num(r.icir_median, 3)}
      </span>
    </Tooltip>
  );
}

export default function Board() {
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ["bases"],
    queryFn: fetchBases,
  });
  const navigate = useNavigate();
  const screens = Grid.useBreakpoint();
  const compact = screens.md === false;
  const [params, setParams] = useSearchParams();
  const searchRef = useRef<InputRef>(null);
  const [active, setActive] = useState<string | null>(null);

  const patch = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v == null || v === "") next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };
  const search = params.get("q") ?? "";
  const [searchText, setSearchText] = useState(search);
  useEffect(() => {
    setSearchText((t) => (t === search ? t : search));
  }, [search]);
  const [sortKey, sortOrder] = (() => {
    const [k, o] = (params.get("sort") ?? "icir:descend").split(":");
    const key = k === "name" || METRIC_COLS.some((m) => m.key === k) ? k : "icir";
    return [key, o === "ascend" ? "ascend" : "descend"] as const;
  })();
  const [storedHidden, setStoredHidden] = useState<string[] | null>(readHidden);
  const hidden = new Set(storedHidden ?? DEFAULT_HIDDEN);
  const setHidden = (keys: string[] | null) => {
    setStoredHidden(keys);
    writeHidden(keys);
  };

  useEffect(() => rememberBoardSearch(params.toString()), [params]);

  // The board lists only base factors with a number; the rest (待中性化 / 待评估 / 方向不一致)
  // sit behind the "另有 N 个待处理" popover in the title.
  const listed = useMemo(() => (data ?? []).filter((r) => r.status === "ok"), [data]);
  const pending = useMemo(
    () => (data ?? []).filter((r) => r.status !== "ok").sort((a, b) => compareBase(a.base, b.base)),
    [data],
  );
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const hit = listed.filter(
      (r) => !q || r.base.toLowerCase().includes(q) || baseLabel(r.base).toLowerCase().includes(q),
    );
    const desc = sortOrder === "descend";
    return [...hit].sort((a, b) =>
      sortKey === "name"
        ? (desc ? -1 : 1) * compareBase(a.base, b.base)
        : byMetric(sortKey as BaseMetricKey)(a, b, desc),
    );
  }, [listed, search, sortKey, sortOrder]);

  const open = (base: string) => navigate(baseHref(base));
  const move = (delta: number) => {
    if (!rows.length) return;
    const i = active ? rows.findIndex((r) => r.base === active) : -1;
    const next = rows[Math.min(rows.length - 1, Math.max(0, i + delta))];
    setActive(next.base);
    document
      .querySelector(`[data-row-key="${CSS.escape(next.base)}"]`)
      ?.scrollIntoView({ block: "nearest" });
  };
  useHotkeys({
    "/": () => searchRef.current?.focus(),
    j: () => move(1),
    k: () => move(-1),
    Enter: () => active && open(active),
    o: () => active && open(active),
  });

  const metricColumns: ColumnsType<BaseRow> = METRIC_COLS.map((m) => ({
    key: m.key,
    title: m.tip ? <Tooltip title={m.tip}>{m.title}</Tooltip> : m.title,
    align: "right" as const,
    width: m.width ?? 104,
    sorter: true,
    sortDirections: ["descend" as const, "ascend" as const],
    sortOrder: sortKey === m.key ? sortOrder : null,
    render: (_: unknown, r: BaseRow) => {
      if (r.status !== "ok") return m.key === "icir" ? <IcirCell r={r} /> : <span className="num">—</span>;
      if (m.key === "icir") return <IcirCell r={r} />;
      const v = metricOf(r, m.key);
      return (
        <span className="num" style={{ color: m.signed ? signColor(v) : undefined }}>
          {m.signed ? withSign(m.fmt(v), v) : m.fmt(v)}
        </span>
      );
    },
  }));

  const allColumns: ColumnsType<BaseRow> = [
    {
      key: "direction",
      title: "方向",
      width: 110,
      render: (_, r) => <DirectionTag direction={r.direction} status={r.status} />,
    },
    ...metricColumns,
    {
      key: "range",
      title: "样本区间",
      width: 190,
      render: (_, r) =>
        r.start_date ? (
          <Typography.Text type="secondary">
            {fmtDate(r.start_date)} → {fmtDate(r.end_date)}
          </Typography.Text>
        ) : (
          "—"
        ),
    },
    {
      key: "run_id",
      title: "评估 run",
      width: 150,
      render: (_, r) => <Typography.Text type="secondary">{r.run_ids.join("、") || "—"}</Typography.Text>,
    },
  ];

  const columns: ColumnsType<BaseRow> = [
    {
      key: "name",
      title: "因子",
      fixed: "left",
      width: compact ? 150 : 220,
      sorter: true,
      sortDirections: ["ascend", "descend"],
      sortOrder: sortKey === "name" ? sortOrder : null,
      render: (_, r) => (
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.35 }}>
          <span style={{ fontWeight: 500 }}>{baseLabel(r.base)}</span>
          {baseLabel(r.base) !== r.base && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {r.base}
            </Typography.Text>
          )}
        </div>
      ),
    },
    ...allColumns.filter((c) => !hidden.has(String(c.key))),
  ];
  const scrollX = columns.reduce((w, c) => w + (Number(c.width) || 104), 0);

  const columnSettings = (
    <Space direction="vertical" size={8} style={{ width: 180 }}>
      <Checkbox.Group
        style={{ display: "flex", flexDirection: "column", gap: 6 }}
        value={OPTIONAL.filter((c) => !hidden.has(c.key)).map((c) => c.key)}
        options={OPTIONAL.map((c) => ({ value: c.key, label: c.label }))}
        onChange={(shown) => setHidden(OPTIONAL.map((c) => c.key).filter((k) => !(shown as string[]).includes(k)))}
      />
      <Button size="small" block onClick={() => setHidden(null)}>
        恢复默认
      </Button>
    </Space>
  );

  if (error) return <ErrorState error={error} title="因子列表加载失败" onRetry={() => refetch()} />;

  return (
    <Card
      title={
        <span>
          因子看板
          <Typography.Text type="secondary" style={{ fontWeight: 400, marginInlineStart: 8 }}>
            共 {listed.length} 个原始因子
          </Typography.Text>
          {pending.length > 0 && (
            <Popover
              trigger="click"
              placement="bottomLeft"
              title="待处理的原始因子（不在看板上排名）"
              content={
                <Space direction="vertical" size={6} style={{ minWidth: 260 }}>
                  {pending.map((r) => (
                    <div
                      key={r.base}
                      style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}
                    >
                      <Typography.Link onClick={() => open(r.base)}>
                        {baseLabel(r.base)}
                        {baseLabel(r.base) !== r.base && (
                          <Typography.Text type="secondary" style={{ fontSize: 12, marginInlineStart: 6 }}>
                            {r.base}
                          </Typography.Text>
                        )}
                      </Typography.Link>
                      <Tag bordered={false} color={r.status === "mixed" ? "warning" : undefined} style={{ marginInlineEnd: 0 }}>
                        {STATUS_LABEL[r.status]}
                      </Tag>
                    </div>
                  ))}
                </Space>
              }
            >
              <Button type="link" size="small" style={{ fontWeight: 400 }}>
                另有 {pending.length} 个待处理
              </Button>
            </Popover>
          )}
        </span>
      }
      extra={
        <Popover trigger="click" placement="bottomRight" title="显示的列" content={columnSettings}>
          <Button size={compact ? "small" : "middle"}>列设置</Button>
        </Popover>
      }
      styles={{ body: compact ? { padding: 12 } : { paddingTop: 12 } }}
    >
      <Input.Search
        ref={searchRef}
        allowClear
        placeholder="搜索因子（/）"
        style={{ width: compact ? "100%" : 260, marginBottom: 12 }}
        value={searchText}
        onChange={(e) => {
          setSearchText(e.target.value);
          patch({ q: e.target.value || null });
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
      <Table<BaseRow>
        rowKey="base"
        size="middle"
        loading={isLoading || isRefetching}
        columns={columns}
        dataSource={rows}
        pagination={false}
        scroll={{ x: scrollX }}
        sticky={{ offsetHeader: 56 }}
        rowClassName={(r) => (r.base === active ? "zf-row-active" : "")}
        onRow={(r) => ({
          onClick: () => open(r.base),
          onMouseEnter: () => setActive(r.base),
          style: { cursor: "pointer" },
        })}
        onChange={(_pg, _f, sorter, extra) => {
          if (extra.action !== "sort") return;
          const s = Array.isArray(sorter) ? sorter[0] : sorter;
          const value = s?.order ? `${String(s.columnKey)}:${s.order}` : null;
          patch({ sort: value === "icir:descend" ? null : value });
        }}
        locale={{
          emptyText: isLoading ? " " : <Empty description={search ? "没有匹配的因子" : "还没有因子"} />,
        }}
        footer={
          compact
            ? undefined
            : () => (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  每行一个原始因子，只看主版本（默认行业+市值中性）；指标均为主版本各窗口的中位数；点击进入因子主页查看全部处理方式和窗口 · 快捷键：j/k 移动，Enter 打开
                </Typography.Text>
              )
        }
      />
      <CompareBar />
    </Card>
  );
}
