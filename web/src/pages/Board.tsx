import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Input,
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
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { fetchFactors } from "../api";
import { fmtDate, isNum, num, pct, signColor } from "../format";
import type { BoardRow, Num } from "../types";

const MAX_COMPARE = 8;

/** Preprocessing family from the name: 原始, z_, or z_<...>_neu_ (e.g. z_size_industry_neu_). */
function prefixOf(name: string): string {
  if (!name.startsWith("z_")) return "原始";
  const neu = name.indexOf("_neu_");
  return neu > 0 ? name.slice(0, neu + 5) : "z_";
}

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
  <span style={{ color: signColor(v), fontVariantNumeric: "tabular-nums" }}>{fmt(v)}</span>
);
const plain = (fmt: (v: Num) => string) => (v: Num) => (
  <span style={{ fontVariantNumeric: "tabular-nums" }}>{fmt(v)}</span>
);

function metricCol(
  title: string,
  key: keyof BoardRow,
  render: (v: Num) => React.ReactNode,
  tip?: string,
  extra: Partial<ColumnsType<BoardRow>[number]> = {},
): ColumnsType<BoardRow>[number] {
  return {
    title: tip ? <Tooltip title={tip}>{title}</Tooltip> : title,
    dataIndex: key,
    key,
    align: "right",
    width: 110,
    ...extra,
    sorter: nullsLast((r) => r[key] as Num),
    sortDirections: ["descend", "ascend"],
    render,
  };
}

export default function Board() {
  const { data, isLoading, error } = useQuery({ queryKey: ["factors"], queryFn: fetchFactors });
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [evaluatedOnly, setEvaluatedOnly] = useState(false);
  const [prefix, setPrefix] = useState<string>("全部");

  const selected = useMemo(
    () => (params.get("sel") ?? "").split(",").filter(Boolean),
    [params],
  );
  const setSelected = (keys: string[]) => {
    const next = new URLSearchParams(params);
    if (keys.length) next.set("sel", keys.join(","));
    else next.delete("sel");
    setParams(next, { replace: true });
  };

  const rows = data ?? [];
  const allCategories = useMemo(
    () => [...new Set(rows.map((r) => r.category).filter((c): c is string => !!c))].sort(),
    [rows],
  );
  const allTags = useMemo(() => [...new Set(rows.flatMap((r) => r.tags))].sort(), [rows]);
  const allPrefixes = useMemo(() => {
    const found = [...new Set(rows.map((r) => prefixOf(r.name)))];
    const rest = found.filter((p) => p !== "原始").sort((a, b) => a.length - b.length);
    return ["全部", ...(found.includes("原始") ? ["原始"] : []), ...rest];
  }, [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (!q || r.name.toLowerCase().includes(q) || r.description.toLowerCase().includes(q)) &&
        (!categories.length || (r.category && categories.includes(r.category))) &&
        (!tags.length || tags.every((t) => r.tags.includes(t))) &&
        (!evaluatedOnly || r.evaluated) &&
        (prefix === "全部" || prefixOf(r.name) === prefix),
    );
  }, [rows, search, categories, tags, evaluatedOnly, prefix]);

  const evaluatedCount = rows.filter((r) => r.evaluated).length;

  const columns: ColumnsType<BoardRow> = [
    {
      title: "因子",
      dataIndex: "name",
      key: "name",
      fixed: "left",
      width: 260,
      sorter: (a, b) => a.name.localeCompare(b.name),
      render: (name: string, r) => (
        <Space size={4} wrap>
          <Link to={`/factor/${encodeURIComponent(name)}`}>{name}</Link>
          {r.direction === -1 && (
            <Tooltip title="IC 为负，多头取低分组">
              <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                反向
              </Tag>
            </Tooltip>
          )}
          {!r.evaluated && <Tag style={{ marginInlineEnd: 0 }}>未评估</Tag>}
        </Space>
      ),
    },
    {
      title: "分类 / 标签",
      key: "category",
      width: 160,
      render: (_, r) => (
        <Space size={2} wrap>
          {r.category && <Tag color="blue">{r.category}</Tag>}
          {r.tags.map((t) => (
            <Tag key={t}>{t}</Tag>
          ))}
        </Space>
      ),
    },
    metricCol("方向调整 IC", "ic_adj", plain((v) => num(v, 4)), "Rank IC 均值 × 因子方向", {
      width: 130,
    }),
    metricCol("ICIR", "icir", plain((v) => num(v, 3)), "方向调整后的 ICIR", {
      defaultSortOrder: "descend",
    }),
    metricCol("t 值", "t_stat", plain((v) => num(v, 2)), "方向调整后的 HAC t 统计量"),
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

  if (error) return <Alert type="error" message={`加载失败：${(error as Error).message}`} />;

  return (
    <Card
      title={
        <Space>
          因子看板
          <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
            共 {rows.length} 个因子，{evaluatedCount} 个有标准评估
          </Typography.Text>
        </Space>
      }
      styles={{ body: { paddingTop: 12 } }}
    >
      <Space wrap style={{ marginBottom: 12 }} size="middle">
        <Input.Search
          allowClear
          placeholder="搜索因子名或描述"
          style={{ width: 240 }}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Segmented<string>
          options={allPrefixes}
          value={prefix}
          onChange={setPrefix}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="分类"
          style={{ minWidth: 140 }}
          options={allCategories.map((c) => ({ value: c, label: c }))}
          value={categories}
          onChange={setCategories}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="标签"
          style={{ minWidth: 140 }}
          options={allTags.map((t) => ({ value: t, label: t }))}
          value={tags}
          onChange={setTags}
        />
        <Space size={6}>
          <Switch size="small" checked={evaluatedOnly} onChange={setEvaluatedOnly} />
          <span>只看已评估</span>
        </Space>
      </Space>
      <Table<BoardRow>
        rowKey="name"
        size="middle"
        loading={isLoading}
        columns={columns}
        dataSource={filtered}
        scroll={{ x: 1900 }}
        pagination={{ defaultPageSize: 50, showSizeChanger: true, pageSizeOptions: [20, 50, 100, 200] }}
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
      {selected.length > 0 && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            background: "#1f2937",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: 12,
            boxShadow: "0 8px 24px rgba(0,0,0,.18)",
            zIndex: 10,
            display: "flex",
            gap: 12,
            alignItems: "center",
            maxWidth: "calc(100vw - 32px)",
          }}
        >
          <span>
            已选 {selected.length} 个
            {selected.length < 2 ? "（至少 2 个）" : ""}
          </span>
          <Button size="small" ghost onClick={() => setSelected([])}>
            清空
          </Button>
          <Button
            size="small"
            type="primary"
            disabled={selected.length < 2}
            style={{ background: "#fff", color: "#1f2937" }}
            onClick={() => navigate(`/compare?f=${encodeURIComponent(selected.join(","))}`)}
          >
            开始对比
          </Button>
        </div>
      )}
    </Card>
  );
}
