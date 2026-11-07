import { useEffect, useMemo, useRef, useState } from "react";
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
import type { InputRef } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { SortOrder } from "antd/es/table/interface";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchBoardCurves, fetchDetail, fetchFactor, fetchFactors, fetchMeta } from "../api";
import { rememberBoardSearch } from "../boardState";
import { MAX_COMPARE, compareHref, setBasket, toggleInBasket, useBasket } from "../compareBasket";
import { CompareBar } from "../components/CompareBar";
import {
  baseLabel,
  compareBase,
  comparePrep,
  parseFactorName,
  prepColor,
  prepLabel,
  windowLabel,
} from "../factorName";
import { fmtDate, isNum, num, pct, signColor, withSign } from "../format";
import { heatScale, type HeatSpec } from "../heat";
import { useHotkeys } from "../hotkeys";
import { usePalette } from "../theme";
import type { BoardRow, Num } from "../types";
import { ErrorState } from "../components/states";
import { FactorChips } from "../components/FactorName";
import { FactorMatrix, MATRIX_METRICS } from "../components/FactorMatrix";
import { Sparkline } from "../components/Sparkline";

const COLS_KEY = "zer0factor.board.hiddenColumns";
const HEAT_KEY = "zer0factor.board.heat";
const DEFAULT_SORT = "icir:descend";
/** Above this many rows the list paginates; below it every row is rendered at once. */
const PAGINATE_ABOVE = 500;

/** A table row: a factor, or (grouped mode) a family row holding its windows as children. */
type Row = BoardRow & {
  key: string;
  children?: Row[];
  family?: { base: string; prep: string; count: number; rep: string };
};

/** Numeric comparator that keeps unevaluated (null) rows last in both directions. */
function nullsLast(get: (r: BoardRow) => Num) {
  return (a: BoardRow, b: BoardRow, desc: boolean) => {
    const x = get(a);
    const y = get(b);
    const xn = !isNum(x);
    const yn = !isNum(y);
    if (xn && yn) return 0;
    if (xn) return 1;
    if (yn) return -1;
    return desc ? (y as number) - (x as number) : (x as number) - (y as number);
  };
}

function byName(a: BoardRow, b: BoardRow) {
  const pa = parseFactorName(a.name);
  const pb = parseFactorName(b.name);
  return (
    compareBase(pa.base, pb.base) ||
    comparePrep(pa.prep, pb.prep) ||
    (pa.window ?? Infinity) - (pb.window ?? Infinity)
  );
}

type Col = ColumnsType<Row>[number] & { key: string };

/** Optional columns users can toggle; `name` is always shown. */
const OPTIONAL: { key: string; label: string; defaultHidden?: boolean }[] = [
  { key: "direction", label: "方向" },
  { key: "category", label: "分类 / 标签" },
  { key: "spark", label: "多空曲线" },
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

/** Metric columns: format, whether the text is sign-coloured, and how the heat scale paints it. */
const METRIC_COLS: {
  key: keyof BoardRow & string;
  title: string;
  fmt: (v: Num) => string;
  signed?: boolean;
  tip?: string;
  width?: number;
}[] = [
  { key: "ic_adj", title: "方向调整 IC", fmt: (v) => num(v, 4), tip: "Rank IC 均值 × 因子方向", width: 124 },
  { key: "icir", title: "ICIR", fmt: (v) => num(v, 3), tip: "方向调整后的 ICIR" },
  {
    key: "t_stat",
    title: "t 值",
    fmt: (v) => num(v, 2),
    tip: "方向调整后的 HAC t 统计量；样本长度相近时与 ICIR 几乎完全相关",
  },
  { key: "ic_win_rate", title: "IC 胜率", fmt: (v) => (isNum(v) ? `${v.toFixed(1)}%` : "—") },
  { key: "ls_ann_ret", title: "多空年化", fmt: (v) => pct(v), signed: true, tip: "扣费后多空组合年化收益" },
  { key: "ls_max_dd", title: "多空回撤", fmt: (v) => pct(v) },
  { key: "ls_sharpe", title: "多空夏普", fmt: (v) => num(v, 2), signed: true },
  {
    key: "long_exc_ann_ret",
    title: "多头超额",
    fmt: (v) => pct(v),
    signed: true,
    tip: "多头相对全市场等权的年化超额",
  },
  { key: "monotonicity", title: "单调性", fmt: (v) => num(v, 2) },
  { key: "turnover_long", title: "多头换手", fmt: (v) => pct(v, 1), tip: "多头组日均换手" },
];

const HEAT_SPECS: Record<string, HeatSpec> = {
  ...Object.fromEntries(MATRIX_METRICS.map((m) => [m.key, m])),
  t_stat: { center: 0 },
};

function readJson<T>(key: string, fallback: T, valid: (v: unknown) => v is T): T {
  try {
    const raw = localStorage.getItem(key);
    const v = raw ? JSON.parse(raw) : null;
    return valid(v) ? v : fallback;
  } catch {
    return fallback;
  }
}
function writeJson(key: string, v: unknown) {
  try {
    if (v == null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* storage unavailable: keep the in-memory choice */
  }
}
const isStringArray = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");
const isBool = (v: unknown): v is boolean => typeof v === "boolean";

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
  // Sparklines + cache status; optional (an older server has no such endpoint).
  const curves = useQuery({ queryKey: ["board-curves"], queryFn: fetchBoardCurves, retry: false });
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const client = useQueryClient();
  const pal = usePalette();
  const navigate = useNavigate();
  const screens = Grid.useBreakpoint();
  const compact = screens.md === false;
  const [params, setParams] = useSearchParams();
  const [storedHidden, setStoredHidden] = useState<string[] | null>(() =>
    readJson<string[] | null>(COLS_KEY, null, (v): v is string[] | null => v === null || isStringArray(v)),
  );
  const [heat, setHeatState] = useState<boolean>(() => readJson(HEAT_KEY, false, isBool));
  const setHeat = (v: boolean) => {
    setHeatState(v);
    writeJson(HEAT_KEY, v || null);
  };
  const [selectMode, setSelectMode] = useState(false);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const searchRef = useRef<InputRef>(null);

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
  // The search box keeps its own state so fast typing is never overwritten by a URL round-trip.
  const [searchText, setSearchText] = useState(search);
  useEffect(() => {
    setSearchText((t) => (t === search ? t : search));
  }, [search]);
  const preps = list(params.get("prep"));
  const bases = list(params.get("base"));
  const wins = list(params.get("win"));
  const dir = params.get("dir") ?? "";
  const evaluatedOnly = params.get("ev") === "1";
  const categories = list(params.get("cat"));
  const tags = list(params.get("tag"));
  const view = params.get("view") === "matrix" ? "matrix" : "list";
  const grouped = params.get("group") === "1";
  const matrixMetric =
    MATRIX_METRICS.find((m) => m.key === params.get("mm")) ?? MATRIX_METRICS[0];
  const [sortKey, sortOrder] = (() => {
    const s = params.get("sort") ?? DEFAULT_SORT;
    if (s === "none") return [null, null] as const;
    const [k, o] = s.split(":");
    return [k, o === "ascend" ? "ascend" : "descend"] as const;
  })();
  const page = Math.max(1, Number(params.get("page")) || 1);

  useEffect(() => rememberBoardSearch(params.toString()), [params]);

  const selected = useBasket();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, params]);

  // ---- sorting (done here so keyboard navigation knows the visible order) ----
  const compareRows = useMemo(() => {
    if (!sortKey) return byName;
    if (sortKey === "name") return (a: BoardRow, b: BoardRow) => byName(a, b) * (sortOrder === "descend" ? -1 : 1);
    const cmp = nullsLast((r) => r[sortKey as keyof BoardRow] as Num);
    return (a: BoardRow, b: BoardRow) => cmp(a, b, sortOrder === "descend") || byName(a, b);
  }, [sortKey, sortOrder]);

  const tableRows: Row[] = useMemo(() => {
    const flat = [...filtered].sort(compareRows).map((r) => ({ ...r, key: r.name }));
    if (!grouped) return flat;
    // Group by (base, preprocessing); the family row shows its best member under the current sort.
    const fams = new Map<string, Row[]>();
    for (const r of flat) {
      const p = parseFactorName(r.name);
      const k = `${p.base}|${p.prep}`;
      (fams.get(k) ?? fams.set(k, []).get(k)!).push(r);
    }
    const out: Row[] = [];
    for (const [k, members] of fams) {
      if (members.length === 1) {
        out.push(members[0]);
        continue;
      }
      const rep = members.find((m) => m.evaluated) ?? members[0];
      const p = parseFactorName(rep.name);
      out.push({
        ...rep,
        key: `family:${k}`,
        children: [...members].sort((a, b) => (parseFactorName(a.name).window ?? Infinity) - (parseFactorName(b.name).window ?? Infinity)),
        family: { base: p.base, prep: p.prep, count: members.length, rep: rep.name },
      });
    }
    return out.sort(compareRows);
  }, [filtered, compareRows, grouped]);

  // Rows in on-screen order (family children only when expanded).
  const visible: Row[] = useMemo(
    () =>
      tableRows.flatMap((r) => (r.children && expanded.includes(r.key) ? [r, ...r.children] : [r])),
    [tableRows, expanded],
  );

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

  // ---- prefetch on hover: only cached factors, whose detail is a cheap disk read ----
  const hoverTimer = useRef<number>();
  const prefetch = (r: Row) => {
    window.clearTimeout(hoverTimer.current);
    const status = curves.data?.items[r.name];
    const period = meta.data?.standard.period;
    if (r.family || !r.run_id || !status?.cached || period !== "1D") return;
    hoverTimer.current = window.setTimeout(() => {
      client.prefetchQuery({ queryKey: ["factor", r.name], queryFn: () => fetchFactor(r.name) });
      client.prefetchQuery({
        queryKey: ["detail", r.name, r.run_id, period],
        queryFn: () => fetchDetail(r.name, r.run_id!, period),
        staleTime: Infinity,
      });
    }, 150);
  };

  const open = (name: string) => navigate(`/factor/${encodeURIComponent(name)}`);
  const toggleFamily = (key: string) =>
    setExpanded((e) => (e.includes(key) ? e.filter((k) => k !== key) : [...e, key]));

  // ---- keyboard ----
  const move = (delta: number) => {
    if (!visible.length) return;
    const i = active ? visible.findIndex((r) => r.key === active) : -1;
    const next = visible[Math.min(visible.length - 1, Math.max(0, i < 0 ? 0 : i + delta))];
    setActive(next.key);
    document
      .querySelector(`tr[data-row-key="${CSS.escape(next.key)}"]`)
      ?.scrollIntoView({ block: "nearest" });
  };
  const activeRow = visible.find((r) => r.key === active);
  const activate = () => {
    if (!activeRow) return;
    if (activeRow.family) toggleFamily(activeRow.key);
    else open(activeRow.name);
  };
  const listView = view === "list";
  useHotkeys({
    "/": () => searchRef.current?.focus(),
    j: () => listView && move(1),
    k: () => listView && move(-1),
    Enter: () => listView && activate(),
    o: () => listView && activate(),
    x: () => listView && activeRow && !activeRow.family && toggleSelected(activeRow.name),
    c: () => (selected.length >= 2 ? navigate(compareHref(selected)) : message.info("对比篮至少需要 2 个因子")),
    v: () => patch({ view: listView ? "matrix" : null }, false),
    g: () => listView && patch({ group: grouped ? null : "1" }, false),
  });

  // ---- columns ----
  const defaultHidden = OPTIONAL.filter(
    (c) => c.defaultHidden || (c.key === "category" && labelled < rows.length * 0.1),
  ).map((c) => c.key);
  const hidden = new Set(storedHidden ?? defaultHidden);
  const toggleable = OPTIONAL.filter((c) => c.key !== "category" || hasLabels);
  const setHidden = (keys: string[] | null) => {
    setStoredHidden(keys);
    writeJson(COLS_KEY, keys);
  };

  const scales = useMemo(
    () =>
      heat
        ? Object.fromEntries(
            METRIC_COLS.map((m) => [m.key, heatScale(filtered.map((r) => r[m.key] as Num), HEAT_SPECS[m.key], pal)]),
          )
        : null,
    [heat, filtered, pal],
  );

  const metricColumns: Col[] = METRIC_COLS.map((m) => ({
    title: m.tip ? <Tooltip title={m.tip}>{m.title}</Tooltip> : m.title,
    dataIndex: m.key,
    key: m.key,
    align: "right",
    width: m.width ?? 104,
    sorter: true,
    sortDirections: ["descend", "ascend"],
    onCell: (r: Row) => {
      const paint = scales?.[m.key]?.paint(r[m.key] as Num);
      return paint?.bg ? { style: { background: paint.bg, color: paint.strong ? "#fff" : undefined } } : {};
    },
    render: (v: Num, r: Row) => {
      const text = m.signed ? withSign(m.fmt(v), v) : m.fmt(v);
      const title =
        m.key === "icir" && hidden.has("t_stat") && isNum(r.t_stat) ? `HAC t 值 ${r.t_stat.toFixed(2)}` : undefined;
      return (
        <span
          className="num"
          title={title}
          style={{ color: m.signed && !heat ? signColor(v) : undefined, opacity: r.family ? 0.85 : undefined }}
        >
          {text}
        </span>
      );
    },
  }));

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
            <span className="zf-dir zf-dir-neg" role="img" aria-label="反向">
              ↓
            </span>
          </Tooltip>
        ) : (
          <Tooltip title="正向因子：IC 为正，多头取高分组">
            <span className="zf-dir" role="img" aria-label="正向">
              ↑
            </span>
          </Tooltip>
        ),
    },
    {
      title: "分类 / 标签",
      key: "category",
      width: 150,
      render: (_: unknown, r: Row) => {
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
    {
      title: <Tooltip title="扣费后多空组合累计收益（全样本，降采样）">多空曲线</Tooltip>,
      key: "spark",
      width: 116,
      render: (_: unknown, r: Row) => {
        const ls = curves.data?.items[r.name]?.ls;
        return ls ? <Sparkline values={ls} label={`${r.name} 多空累计收益`} /> : null;
      },
    },
    ...metricColumns,
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
    width: compact ? 210 : grouped ? 340 : 300,
    sorter: true,
    sortDirections: ["ascend", "descend"],
    render: (name: string, r) => {
      if (r.family) {
        const w = parseFactorName(r.family.rep).window;
        return (
          <div className={compact ? "zf-name-cell zf-wrap" : "zf-name-cell"}>
            <span className="zf-chips">
              <Tag color={prepColor(r.family.prep)} bordered={false}>
                {prepLabel(r.family.prep)}
              </Tag>
              <Typography.Link onClick={() => toggleFamily(r.key)} title={`${r.family.count} 个窗口`}>
                {baseLabel(r.family.base)}
              </Typography.Link>
            </span>
            <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
              {r.family.count} 个 · 最佳 {windowLabel(w)}
            </Typography.Text>
          </div>
        );
      }
      const status = curves.data?.items[name];
      return (
        <div className={compact ? "zf-name-cell zf-wrap" : "zf-name-cell"}>
          <FactorChips name={name} />
          {!r.evaluated && <Tag bordered={false}>未评估</Tag>}
          {r.evaluated && status && !status.cached && (
            <Tooltip title="该因子的详情图表尚未缓存，首次打开需从原始数据计算（约 1–2 分钟）">
              <Tag bordered={false} color="warning">
                需计算
              </Tag>
            </Tooltip>
          )}
        </div>
      );
    },
  };

  const columns: Col[] = [
    nameCol,
    ...allColumns.filter(
      (c) =>
        !hidden.has(c.key) &&
        (c.key !== "category" || hasLabels) &&
        (c.key !== "spark" || curves.isSuccess),
    ),
  ].map((c) => ({
    ...c,
    sortOrder: c.sorter ? (c.key === sortKey ? (sortOrder as SortOrder) : null) : undefined,
  }));

  const scrollX = columns.reduce((w, c) => w + (Number(c.width) || 104), 48);
  const paginate = filtered.length > PAGINATE_ABOVE;

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
    <Space size={8} wrap>
      <Segmented
        size={compact ? "small" : "middle"}
        value={view}
        onChange={(v) => patch({ view: v === "matrix" ? "matrix" : null }, false)}
        options={[
          { value: "list", label: "列表" },
          { value: "matrix", label: "矩阵" },
        ]}
      />
      {listView && (
        <>
          <Tooltip title="按收益类型 × 预处理折叠成族，族行显示当前排序下的最佳成员（快捷键 g）">
            <Space size={4}>
              <Switch
                size="small"
                id="zf-group"
                checked={grouped}
                onChange={(v) => patch({ group: v ? "1" : null }, false)}
              />
              <label htmlFor="zf-group" style={{ cursor: "pointer" }}>
                分组
              </label>
            </Space>
          </Tooltip>
          <Tooltip title="按列着色：每列按可见行的 5%–95% 分位着色">
            <Space size={4}>
              <Switch size="small" id="zf-heat" checked={heat} onChange={setHeat} />
              <label htmlFor="zf-heat" style={{ cursor: "pointer" }}>
                色阶
              </label>
            </Space>
          </Tooltip>
          <Popover trigger="click" placement="bottomRight" title="显示的列" content={columnSettings}>
            <Button size={compact ? "small" : "middle"}>列设置</Button>
          </Popover>
        </>
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
          ref={searchRef}
          allowClear
          placeholder="搜索因子名或描述（/）"
          style={{ width: compact ? "calc(100vw - 48px)" : 220 }}
          value={searchText}
          onChange={(e) => {
            setSearchText(e.target.value);
            patch({ q: e.target.value || null });
          }}
          onKeyDown={(e) => {
            // Esc leaves the box (keeping the query) so j/k work; the native search input would clear it.
            if (e.key === "Escape") {
              e.preventDefault();
              (e.target as HTMLInputElement).blur();
            }
          }}
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
            id="zf-ev"
            checked={evaluatedOnly}
            onChange={(v) => patch({ ev: v ? "1" : null })}
          />
          <label htmlFor="zf-ev" style={{ cursor: "pointer" }}>
            只看已评估
          </label>
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
        <>
          {grouped && (
            <Space size={8} style={{ marginBottom: 8 }}>
              <Button size="small" onClick={() => setExpanded(tableRows.filter((r) => r.children).map((r) => r.key))}>
                全部展开
              </Button>
              <Button size="small" onClick={() => setExpanded([])}>
                全部收起
              </Button>
            </Space>
          )}
          <Table<Row>
            rowKey="key"
            size="middle"
            loading={isLoading || isRefetching}
            columns={columns}
            dataSource={tableRows}
            scroll={{ x: scrollX }}
            sticky={{ offsetHeader: 56 }}
            rowClassName={(r) => [r.key === active ? "zf-row-active" : "", r.family ? "zf-row-family" : ""].join(" ")}
            onRow={(r) => ({
              onMouseEnter: () => prefetch(r),
              onClick: () => setActive(r.key),
            })}
            expandable={{
              expandedRowKeys: expanded,
              onExpandedRowsChange: (keys) => setExpanded(keys as string[]),
              indentSize: 16,
            }}
            onChange={(pg, _filters, sorter, extra) => {
              if (extra.action === "sort") {
                const s = Array.isArray(sorter) ? sorter[0] : sorter;
                const key = s?.order ? String(s.columnKey) : null;
                const value = key ? `${key}:${s.order}` : "none";
                patch({ sort: value === DEFAULT_SORT ? null : value });
              } else if (extra.action === "paginate") {
                patch({ page: pg.current && pg.current > 1 ? String(pg.current) : null }, false);
              }
            }}
            locale={{
              emptyText: isLoading ? (
                " "
              ) : (
                <Empty description={filtersActive ? "没有符合筛选条件的因子" : "还没有注册任何因子"}>
                  {filtersActive && (
                    <Button size="small" onClick={resetFilters}>
                      清除筛选
                    </Button>
                  )}
                </Empty>
              ),
            }}
            pagination={
              paginate
                ? {
                    current: page,
                    pageSize: 200,
                    showSizeChanger: false,
                    showTotal: (n) => `共 ${n} 个`,
                    size: compact ? "small" : undefined,
                  }
                : false
            }
            footer={
              paginate || compact
                ? undefined
                : () => (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      共 {filtered.length} 个 · 快捷键：j/k 移动，Enter 打开，x 勾选对比，? 查看全部
                    </Typography.Text>
                  )
            }
            rowSelection={{
              selectedRowKeys: selected,
              preserveSelectedRowKeys: true,
              hideSelectAll: true,
              checkStrictly: true,
              onChange: (keys) => {
                const names = (keys as string[]).filter((k) => !k.startsWith("family:"));
                if (names.length > MAX_COMPARE) {
                  message.warning(`最多对比 ${MAX_COMPARE} 个因子`);
                  return;
                }
                setBasket(names);
              },
              getCheckboxProps: (r) => ({
                disabled: !!r.family || (selected.length >= MAX_COMPARE && !selected.includes(r.name)),
                style: r.family ? { display: "none" } : undefined,
              }),
            }}
          />
        </>
      )}
      <CompareBar />
    </Card>
  );
}
