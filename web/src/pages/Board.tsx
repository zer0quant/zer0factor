import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Empty,
  Grid,
  Input,
  Popover,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { SortOrder } from "antd/es/table/interface";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchFactors } from "../api";
import { rememberBoardSearch } from "../boardState";
import { MAX_COMPARE, setBasket, toggleInBasket, useBasket } from "../compareBasket";
import { CompareBar } from "../components/CompareBar";
import {
  baseLabel,
  compareBase,
  comparePrep,
  parseFactorName,
  prepLabel,
  windowLabel,
} from "../factorName";
import { fmtDate, isNum, num, pct, signColor } from "../format";
import type { BoardRow, Num } from "../types";
import { ErrorState } from "../components/states";
import { FactorChips } from "../components/FactorName";
import { FactorMatrix, MATRIX_METRICS } from "../components/FactorMatrix";

const COLS_KEY = "zer0factor.board.hiddenColumns";
const DEFAULT_SORT = "icir:descend";

/** Numeric sorter that keeps unevaluated (null) rows last in both directions. */
function nullsLast(get: (r: BoardRow) => Num) {
  return (a: BoardRow, b: BoardRow, order?: SortOrder) => {
    const x = get(a);
    const y = get(b);
    const xn = !isNum(x);
    const yn = !isNum(y);
    if (xn && yn) return 0;
    if (xn) return order === "descend" ? -1 : 1;
    if (yn) return order === "descend" ? 1 : -1;
    return (x as number) - (y as number);
  };
}

const colored = (fmt: (v: Num) => string) => (v: Num) => (
  <span className="num" style={{ color: signColor(v) }}>{fmt(v)}</span>
);
const plain = (fmt: (v: Num) => string) => (v: Num) => <span className="num">{fmt(v)}</span>;

type Col = ColumnsType<BoardRow>[number] & { key: string };

function metricCol(
  title: string,
  key: keyof BoardRow & string,
  render: (v: Num, r: BoardRow) => React.ReactNode,
  tip?: string,
  extra: Partial<Col> = {},
): Col {
  return {
    title: tip ? <Tooltip title={tip}>{title}</Tooltip> : title,
    dataIndex: key,
    key,
    align: "right",
    width: 104,
    ...extra,
    sorter: nullsLast((r) => r[key] as Num),
    sortDirections: ["descend", "ascend"],
    render,
  };
}

/** Optional columns users can toggle; `name` is always shown. */
const OPTIONAL: { key: string; label: string; defaultHidden?: boolean }[] = [
  { key: "direction", label: "方向" },
  { key: "category", label: "分类 / 标签" },
  { key: "ic_adj", label: "方向调整 IC" },
  { key: "icir", label: "ICIR" },
  { key: "t_stat", label: "t 值", defaultHidden: true },
  { key: "ic_win_rate", label: "IC 胜率" },
  { key: "ls_ann_ret", label: "多空年化" },
  { key: "ls_max_dd", label: "多空回撤" },
  { key: "ls_sharpe", label: "多空夏普" },
  { key: "long_exc_ann_ret", label: "多头超额" },
  { key: "monotonicity", label: "单调性" },
  { key: "turnover_long", label: "多头换手" },
  { key: "range", label: "样本区间", defaultHidden: true },
  { key: "run_id", label: "评估 run", defaultHidden: true },
];

function readHidden(): string[] | null {
  try {
    const v = localStorage.getItem(COLS_KEY);
    const parsed = v ? JSON.parse(v) : null;
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : null;
  } catch {
    return null;
  }
}
function writeHidden(keys: string[] | null) {
  try {
    if (keys) localStorage.setItem(COLS_KEY, JSON.stringify(keys));
    else localStorage.removeItem(COLS_KEY);
  } catch {
    /* storage unavailable: keep the in-memory choice */
  }
}

const list = (v: string | null) => (v ?? "").split(",").filter(Boolean);
const winKey = (w: number | null) => (w == null ? "none" : String(w));

/** Facet options with counts, e.g. "日内收益 (41)". */
function facet<T>(
  rows: BoardRow[],
  get: (name: string) => T,
  key: (t: T) => string,
  label: (t: T) => string,
  cmp: (a: T, b: T) => number,
) {
  const counts = new Map<string, { t: T; n: number }>();
  for (const r of rows) {
    const t = get(r.name);
    const k = key(t);
    const e = counts.get(k);
    if (e) e.n += 1;
    else counts.set(k, { t, n: 1 });
  }
  return [...counts.values()]
    .sort((a, b) => cmp(a.t, b.t))
    .map(({ t, n }) => ({ value: key(t), label: `${label(t)} (${n})` }));
}

export default function Board() {
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ["factors"],
    queryFn: fetchFactors,
  });
  const screens = Grid.useBreakpoint();
  const compact = screens.md === false;
  const [params, setParams] = useSearchParams();
  const [storedHidden, setStoredHidden] = useState<string[] | null>(readHidden);
  const [selectMode, setSelectMode] = useState(false);

  // ---- URL-backed view state (survives navigating to a detail page and back) ----
  const patch = (changes: Record<string, string | null>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v == null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  };
  const search = params.get("q") ?? "";
  const preps = list(params.get("prep"));
  const bases = list(params.get("base"));
  const wins = list(params.get("win"));
  const dir = params.get("dir") ?? "";
  const evaluatedOnly = params.get("ev") === "1";
  const categories = list(params.get("cat"));
  const tags = list(params.get("tag"));
  const view = params.get("view") === "matrix" ? "matrix" : "list";
  const matrixMetric =
    MATRIX_METRICS.find((m) => m.key === params.get("mm")) ?? MATRIX_METRICS[0];
  const [sortKey, sortOrder] = (() => {
    const s = params.get("sort") ?? DEFAULT_SORT;
    if (s === "none") return [null, null] as const;
    const [k, o] = s.split(":");
    return [k, o === "ascend" ? "ascend" : "descend"] as const;
  })();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [20, 50, 100, 200].includes(Number(params.get("size")))
    ? Number(params.get("size"))
    : 50;

  useEffect(() => rememberBoardSearch(params.toString()), [params]);

  const selected = useBasket();
  const setSelected = setBasket;
  const toggleSelected = (name: string) => {
    if (!toggleInBasket(name)) message.warning(`最多对比 ${MAX_COMPARE} 个因子`);
  };
  // Legacy links carried the selection as ?sel=: move it into the basket once.
  useEffect(() => {
    const legacy = params.get("sel");
    if (legacy) {
      setBasket(list(legacy));
      patch({ sel: null }, false);
    }
  }, []);

  const rows = data ?? [];
  const allCategories = useMemo(
    () => [...new Set(rows.map((r) => r.category).filter((c): c is string => !!c))].sort(),
    [rows],
  );
  const allTags = useMemo(() => [...new Set(rows.flatMap((r) => r.tags))].sort(), [rows]);
  const labelled = rows.filter((r) => r.category || r.tags.length).length;
  const hasLabels = labelled > 0;
  // Category / tag filters only earn their space once a meaningful share of factors is labelled.
  const showLabelFilters = labelled >= rows.length * 0.1;

  const prepOptions = useMemo(
    () => facet(rows, (n) => parseFactorName(n).prep, (p) => p, prepLabel, comparePrep),
    [rows],
  );
  const baseOptions = useMemo(
    () => facet(rows, (n) => parseFactorName(n).base, (b) => b, baseLabel, compareBase),
    [rows],
  );
  const winOptions = useMemo(
    () =>
      facet(
        rows,
        (n) => parseFactorName(n).window,
        winKey,
        windowLabel,
        (a, b) => (a == null ? 1 : b == null ? -1 : a - b),
      ),
    [rows],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      const p = parseFactorName(r.name);
      return (
        (!q || r.name.toLowerCase().includes(q) || r.description.toLowerCase().includes(q)) &&
        (!preps.length || preps.includes(p.prep)) &&
        (!bases.length || bases.includes(p.base)) &&
        (!wins.length || wins.includes(winKey(p.window))) &&
        (!dir || (r.evaluated && String(r.direction) === dir)) &&
        (!categories.length || (r.category && categories.includes(r.category))) &&
        (!tags.length || tags.every((t) => r.tags.includes(t))) &&
        (!evaluatedOnly || r.evaluated)
      );
    });
  }, [rows, params]);

  const evaluated = rows.filter((r) => r.evaluated);
  const runIds = [...new Set(evaluated.map((r) => r.run_id))];
  const singleRun = runIds.length === 1 ? runIds[0] : null;

  const filtersActive =
    !!search.trim() ||
    preps.length + bases.length + wins.length + categories.length + tags.length > 0 ||
    !!dir ||
    evaluatedOnly;
  const resetFilters = () =>
    patch({ q: null, prep: null, base: null, win: null, dir: null, ev: null, cat: null, tag: null });

  // ---- columns ----
  const defaultHidden = OPTIONAL.filter(
    (c) => c.defaultHidden || (c.key === "category" && labelled < rows.length * 0.1),
  ).map((c) => c.key);
  const hidden = new Set(storedHidden ?? defaultHidden);
  const toggleable = OPTIONAL.filter((c) => c.key !== "category" || hasLabels);
  const setHidden = (keys: string[] | null) => {
    setStoredHidden(keys);
    writeHidden(keys);
  };

  const allColumns: Col[] = [
    {
      title: "方向",
      key: "direction",
      width: 64,
      align: "center",
      render: (_, r) =>
        !r.evaluated || !isNum(r.direction) ? (
          <Typography.Text type="secondary">—</Typography.Text>
        ) : r.direction === -1 ? (
          <Tooltip title="反向因子：IC 为负，多头取低分组">
            <span className="zf-dir zf-dir-neg" aria-label="反向">↓</span>
          </Tooltip>
        ) : (
          <Tooltip title="正向因子：IC 为正，多头取高分组">
            <span className="zf-dir" aria-label="正向">↑</span>
          </Tooltip>
        ),
    },
    {
      title: "分类 / 标签",
      key: "category",
      width: 150,
      render: (_: unknown, r: BoardRow) => {
        const labels = [...(r.category ? [r.category] : []), ...r.tags];
        if (!labels.length) return null;
        return (
          <Tooltip title={labels.join(" · ")}>
            <div className="zf-tags-cell">
              {r.category && <Tag color="blue">{r.category}</Tag>}
              {r.tags.map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </div>
          </Tooltip>
        );
      },
    },
    metricCol("方向调整 IC", "ic_adj", plain((v) => num(v, 4)), "Rank IC 均值 × 因子方向", {
      width: 124,
    }),
    metricCol(
      "ICIR",
      "icir",
      (v, r) => (
        <span className="num" title={isNum(r.t_stat) ? `HAC t 值 ${r.t_stat.toFixed(2)}` : undefined}>
          {num(v, 3)}
        </span>
      ),
      hidden.has("t_stat") ? "方向调整后的 ICIR（悬停数值可看 t 值）" : "方向调整后的 ICIR",
    ),
    metricCol(
      "t 值",
      "t_stat",
      plain((v) => num(v, 2)),
      "方向调整后的 HAC t 统计量；样本长度相近时与 ICIR 几乎完全相关",
    ),
    metricCol("IC 胜率", "ic_win_rate", plain((v) => (isNum(v) ? `${v.toFixed(1)}%` : "—"))),
    metricCol("多空年化", "ls_ann_ret", colored((v) => pct(v)), "扣费后多空组合年化收益"),
    metricCol("多空回撤", "ls_max_dd", plain((v) => pct(v))),
    metricCol("多空夏普", "ls_sharpe", colored((v) => num(v, 2))),
    metricCol("多头超额", "long_exc_ann_ret", colored((v) => pct(v)), "多头相对全市场等权的年化超额"),
    metricCol("单调性", "monotonicity", plain((v) => num(v, 2))),
    metricCol("多头换手", "turnover_long", plain((v) => pct(v, 1)), "多头组日均换手"),
    {
      title: "样本区间",
      key: "range",
      width: 190,
      render: (_, r) =>
        r.evaluated ? (
          <Typography.Text type="secondary">
            {fmtDate(r.start_date)} → {fmtDate(r.end_date)}
          </Typography.Text>
        ) : (
          "—"
        ),
    },
    {
      title: "评估 run",
      dataIndex: "run_id",
      key: "run_id",
      width: 150,
      render: (v: string | null) => <Typography.Text type="secondary">{v ?? "—"}</Typography.Text>,
    },
  ];

  const nameCol: Col = {
    title: "因子",
    dataIndex: "name",
    key: "name",
    fixed: "left",
    width: compact ? 210 : 300,
    sorter: (a, b) => {
      const pa = parseFactorName(a.name);
      const pb = parseFactorName(b.name);
      return (
        compareBase(pa.base, pb.base) ||
        comparePrep(pa.prep, pb.prep) ||
        (pa.window ?? Infinity) - (pb.window ?? Infinity)
      );
    },
    sortDirections: ["ascend", "descend"],
    render: (name: string, r) => (
      <div className={compact ? "zf-name-cell zf-wrap" : "zf-name-cell"}>
        <FactorChips name={name} />
        {!r.evaluated && <Tag bordered={false}>未评估</Tag>}
      </div>
    ),
  };

  const columns: Col[] = [
    nameCol,
    ...allColumns.filter((c) => !hidden.has(c.key) && (c.key !== "category" || hasLabels)),
  ].map((c) => ({
    ...c,
    sortOrder: c.sorter ? (c.key === sortKey ? (sortOrder as SortOrder) : null) : undefined,
  }));

  const scrollX = columns.reduce((w, c) => w + (Number(c.width) || 104), 48);

  if (error && !data)
    return <ErrorState error={error} title="因子列表加载失败" onRetry={() => refetch()} />;

  const columnSettings = (
    <Space direction="vertical" size={8} style={{ width: 180 }}>
      <Checkbox.Group
        style={{ display: "flex", flexDirection: "column", gap: 6 }}
        value={toggleable.filter((c) => !hidden.has(c.key)).map((c) => c.key)}
        options={toggleable.map((c) => ({ value: c.key, label: c.label }))}
        onChange={(shown) =>
          setHidden(OPTIONAL.map((c) => c.key).filter((k) => !(shown as string[]).includes(k)))
        }
      />
      <Button size="small" block onClick={() => setHidden(null)}>
        恢复默认
      </Button>
    </Space>
  );

  const viewControls = (
    <Space size={8}>
      <Segmented
        size={compact ? "small" : "middle"}
        value={view}
        onChange={(v) => patch({ view: v === "matrix" ? "matrix" : null }, false)}
        options={[
          { value: "list", label: "列表" },
          { value: "matrix", label: "矩阵" },
        ]}
      />
      {view === "list" && (
        <Popover trigger="click" placement="bottomRight" title="显示的列" content={columnSettings}>
          <Button size={compact ? "small" : "middle"}>列设置</Button>
        </Popover>
      )}
    </Space>
  );

  const selectWidth = compact ? "calc(50vw - 30px)" : 170;

  return (
    <Card
      title={
        <Space wrap size={[8, 0]}>
          因子看板
          <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
            共 {rows.length} 个因子，{evaluated.length} 个有标准评估
            {singleRun && !compact && ` · 评估 run ${singleRun}`}
          </Typography.Text>
        </Space>
      }
      extra={compact ? undefined : viewControls}
      styles={{ body: compact ? { padding: 12 } : { paddingTop: 12 } }}
    >
      {compact && <div style={{ marginBottom: 8 }}>{viewControls}</div>}
      <Space wrap style={{ marginBottom: 12, width: "100%" }} size={compact ? 8 : [12, 8]}>
        <Input.Search
          allowClear
          placeholder="搜索因子名或描述"
          style={{ width: compact ? "calc(100vw - 48px)" : 220 }}
          value={search}
          onChange={(e) => patch({ q: e.target.value || null })}
        />
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          placeholder="预处理"
          style={{ width: selectWidth }}
          options={prepOptions}
          value={preps}
          onChange={(v) => patch({ prep: v.join(",") || null })}
        />
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          placeholder="收益类型"
          style={{ width: selectWidth }}
          options={baseOptions}
          value={bases}
          onChange={(v) => patch({ base: v.join(",") || null })}
          popupMatchSelectWidth={false}
        />
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          placeholder="窗口"
          style={{ width: selectWidth }}
          options={winOptions}
          value={wins}
          onChange={(v) => patch({ win: v.join(",") || null })}
        />
        <Select
          allowClear
          placeholder="方向"
          style={{ width: compact ? selectWidth : 96 }}
          value={dir || undefined}
          onChange={(v) => patch({ dir: v ?? null })}
          options={[
            { value: "1", label: "正向 ↑" },
            { value: "-1", label: "反向 ↓" },
          ]}
        />
        {(showLabelFilters || categories.length > 0) && allCategories.length > 0 && (
          <Select
            mode="multiple"
            allowClear
            maxTagCount="responsive"
            placeholder="分类"
            style={{ width: selectWidth }}
            options={allCategories.map((c) => ({ value: c, label: c }))}
            value={categories}
            onChange={(v) => patch({ cat: v.join(",") || null })}
          />
        )}
        {(showLabelFilters || tags.length > 0) && allTags.length > 0 && (
          <Select
            mode="multiple"
            allowClear
            maxTagCount="responsive"
            placeholder="标签"
            style={{ width: selectWidth }}
            options={allTags.map((t) => ({ value: t, label: t }))}
            value={tags}
            onChange={(v) => patch({ tag: v.join(",") || null })}
          />
        )}
        <Space size={6}>
          <Switch
            size="small"
            checked={evaluatedOnly}
            onChange={(v) => patch({ ev: v ? "1" : null })}
          />
          <span>只看已评估</span>
        </Space>
        {filtersActive && (
          <Button size="small" type="link" onClick={resetFilters} style={{ paddingInline: 0 }}>
            清除筛选（{filtered.length} / {rows.length}）
          </Button>
        )}
      </Space>

      {view === "matrix" ? (
        <>
          <Space wrap size={[12, 8]} style={{ marginBottom: 12 }}>
            <span>
              <Typography.Text type="secondary">指标 </Typography.Text>
              <Select
                style={{ width: 132 }}
                value={matrixMetric.key}
                onChange={(v) => patch({ mm: v === MATRIX_METRICS[0].key ? null : v }, false)}
                options={MATRIX_METRICS.map((m) => ({ value: m.key, label: m.label }))}
              />
            </span>
            <span>
              <Typography.Text type="secondary">点击格子 </Typography.Text>
              <Segmented
                value={selectMode ? "select" : "open"}
                onChange={(v) => setSelectMode(v === "select")}
                options={[
                  { value: "open", label: "打开详情" },
                  { value: "select", label: "勾选对比" },
                ]}
              />
            </span>
          </Space>
          {isLoading ? null : (
            <FactorMatrix
              rows={filtered}
              metric={matrixMetric}
              selected={selected}
              selectMode={selectMode}
              onToggle={toggleSelected}
            />
          )}
        </>
      ) : (
        <Table<BoardRow>
          rowKey="name"
          size="middle"
          loading={isLoading || isRefetching}
          columns={columns}
          dataSource={filtered}
          scroll={{ x: scrollX }}
          sticky={{ offsetHeader: 56 }}
          onChange={(pg, _filters, sorter, extra) => {
            if (extra.action === "sort") {
              const s = Array.isArray(sorter) ? sorter[0] : sorter;
              const key = s?.order ? String(s.columnKey) : null;
              const value = key ? `${key}:${s.order}` : "none";
              patch({ sort: value === DEFAULT_SORT ? null : value });
            } else if (extra.action === "paginate") {
              patch(
                {
                  page: pg.current && pg.current > 1 ? String(pg.current) : null,
                  size: pg.pageSize && pg.pageSize !== 50 ? String(pg.pageSize) : null,
                },
                false,
              );
            }
          }}
          locale={{
            emptyText: isLoading ? (
              " "
            ) : (
              <Empty
                description={filtersActive ? "没有符合筛选条件的因子" : "还没有注册任何因子"}
              >
                {filtersActive && (
                  <Button size="small" onClick={resetFilters}>
                    清除筛选
                  </Button>
                )}
              </Empty>
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100, 200],
            showTotal: compact ? undefined : (n) => `共 ${n} 个`,
            size: compact ? "small" : undefined,
          }}
          rowSelection={{
            selectedRowKeys: selected,
            preserveSelectedRowKeys: true,
            hideSelectAll: true,
            onChange: (keys) => {
              if (keys.length > MAX_COMPARE) {
                message.warning(`最多对比 ${MAX_COMPARE} 个因子`);
                return;
              }
              setSelected(keys as string[]);
            },
            getCheckboxProps: (r) => ({
              disabled: selected.length >= MAX_COMPARE && !selected.includes(r.name),
            }),
          }}
        />
      )}
      <CompareBar />
    </Card>
  );
}
